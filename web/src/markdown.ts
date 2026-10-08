/**
 * 受限 Markdown 块解析：把回答正文解析成 Vue 可渲染的块结构。
 *
 * **为什么手写而不引 `marked` + `dompurify`**：聊天回答只需要一个极小子集
 * （标题/列表/引用块/分隔线/代码块/粗体/行内代码），为一个聊天气泡引入两个依赖
 * 不成比例；更关键的是第三方 md→HTML 路径必然落到 `v-html`，而这里的输出
 * 是「固定标签 + 文本」的结构，模板里走 `{{ }}` 插值，**没有 XSS 面**。
 *
 * **与 `citation.ts` 的分工**：引用标记的权威切分在 `citationSegments`，
 * 本模块在每个文本 run 上调用它——所以不另写一套 `[C数字]` 正则，两语言口径不打架。
 * 切分在**任何** run（普通文本/粗体/行内代码/代码块）上一视同仁：chat 回答里
 * 引用几乎总在正文，出现 `**[C7]**` 这种包进格式的写法也应该照样能点。
 * 「只用于扫描与渲染，不是净化」：解析不删除任何字符，违规写法原样保留。
 *
 * 支持的块（按行判定，顺序即优先级）：
 * - fenced code（``` / ~~~ 围栏）：块内**不解析任何行内格式**，只切引用；
 *   开栏与闭栏都按**去掉首尾空白后**的行判定，闭栏要求同字符、不短于开栏、
 *   整行只有围栏字符（``` 开头的普通行是内容不是闭栏）
 * - 分隔线：单独成行的 `---` / `***` / `___`
 * - 标题：`#`–`######`，一律夹到 h2/h3 两级（气泡里不出现页面级 H1）
 * - 引用块 `> `：连续行合并，内部按段落处理，不嵌套其它块
 * - 无序列表 `- ` / `* `、有序列表 `1. `：连续行合并；空行结束列表；
 *   列表项内不支持嵌套列表（聊天回答用不上，省掉一层缩进状态机）
 * - 段落：其余一切，空行分段
 *
 * **行首空白按块型分叉，这是刻意的、也是容易踩的**：围栏与分隔线看去掉空白后的行，
 * 标题、列表、引用看原始行。所以 `  ---` 是分隔线，`  - 甲` 却是普通段落。
 *
 * 行内只认 `**粗体**` 与 `` `代码` ``。粗体里的代码段保持代码、其余归入粗体；
 * 但 run 是**扁平单标签**，表达不了嵌套——整段都是代码时（`**`x`**`）只产出 code、
 * 不产生 strong，即写法上加了粗而渲染里没有加粗。行内代码内部不再解析任何格式。
 * 斜体不解析——中文回答里几乎不出现，认了反而会在 `*` 收尾的句子处吃字。
 *
 * 流式期间可反复调用：未闭合的 `**` 视为普通文本，闭合那一帧自动变成粗体，
 * 无状态、不会闪烁。
 */
import { citationSegments } from './citation'
import type { CitationSegment } from './citation'

/** run 的包裹标签。`span` 表示不额外包裹。 */
export type MdRunTag = 'strong' | 'code' | 'span'

export interface MdRun {
  tag: MdRunTag
  /** 已切好的引用片段：普通文本 / 规范引用交替，模板据此插角标 */
  segments: CitationSegment[]
}

/**
 * 视图块。
 *
 * `ul` / `ol` 必须是**两个独立成员**而不是 `tag: 'ul' | 'ol'` 合在一起：
 * 合在一起时模板里的 `v-if="block.tag === 'ul'"` 排不掉这个成员，
 * `vue-tsc` 会在 `<component :is="block.tag">` 上报 `.runs` 不存在。
 */
export type MdViewBlock =
  | { tag: 'p' | 'h2' | 'h3' | 'blockquote' | 'pre'; runs: MdRun[] }
  | { tag: 'ul'; items: MdRun[][] }
  /** `numbers` 与 `items` 对齐：`<ol>` 默认从 1 重排，源编号靠 li 的 `value` 还原 */
  | { tag: 'ol'; items: MdRun[][]; numbers: number[] }
  | { tag: 'hr' }

type MdSpan =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'code'; text: string }

/** 无序列表行。`*` 必须跟空格，避免吃掉 `**粗体**` 的开头 */
const UL_RE = /^[-*] (.*)$/
/** 有序列表行。编号捕获下来原样还原——`<ol>` 默认从 1 重排，会改掉「3.」这种起始号 */
const OL_RE = /^(\d{1,3})\. (.*)$/
const H_RE = /^(#{1,6}) (.+)$/
const HR_RE = /^(-{3,}|\*{3,}|_{3,})$/
/** 围栏开栏：捕获完整的一串围栏字符（用于长度比较），info string（```js）被忽略 */
const FENCE_RE = /^(`{3,}|~{3,})/
/**
 * 行内 token 扫描：谁先出现谁占，认 `` `代码` `` 与 `**粗体**`。
 *
 * 用单次扫描而不是「先切代码再切粗体」两遍：两遍会在
 * `**`[C8]`**`（粗体包代码，模型常见写法）上把 `**` 拆出孤儿，
 * 渲染出两头飘着的星号。单次扫描时粗体整个被认走，内容再递归解析。
 */
const INLINE_RE = /(`[^`\n]+`|\*\*[^*\n]+?\*\*)/g

/** 行内解析：递归支持「粗体内嵌代码」，代码内部不解析任何格式。保留全部原文 */
function parseInline(text: string): MdSpan[] {
  const spans: MdSpan[] = []
  let last = 0
  for (const match of text.matchAll(INLINE_RE)) {
    const index = match.index ?? 0
    if (index > last) spans.push({ kind: 'text', text: text.slice(last, index) })
    const token = match[0]
    if (token.startsWith('`')) {
      spans.push({ kind: 'code', text: token.slice(1, -1) })
    } else {
      // 粗体内容可能是 `前`代码`后`：代码段保持代码，其余仍归入粗体
      for (const inner of parseInline(token.slice(2, -2))) {
        spans.push(inner.kind === 'code' ? inner : { kind: 'strong', text: inner.text })
      }
    }
    last = index + token.length
  }
  if (last < text.length) spans.push({ kind: 'text', text: text.slice(last) })
  return spans
}

const TAG_OF: Record<MdSpan['kind'], MdRunTag> = {
  text: 'span',
  strong: 'strong',
  code: 'code'
}

/** 文本 → run：每个 span 挂一个标签，标签内的文本统一过权威引用切分 */
function runsOfSpans(spans: MdSpan[]): MdRun[] {
  return spans
    .map((span) => ({ tag: TAG_OF[span.kind], segments: citationSegments(span.text) }))
    .filter((run) => run.segments.length > 0)
}

function runsOf(text: string): MdRun[] {
  return runsOfSpans(parseInline(text))
}

/** 全空白的行不产出块——流式里 `\n\n` 与首尾换行很常见 */
function isBlank(runs: MdRun[]): boolean {
  return runs.every((run) => run.segments.every((segment) => segment.text.trim() === ''))
}

/** 该行是否开启一个新块：段落收集到它就该停手 */
function startsBlock(line: string): boolean {
  const trimmed = line.trim()
  return (
    FENCE_RE.test(trimmed) ||
    HR_RE.test(trimmed) ||
    H_RE.test(line) ||
    UL_RE.test(line) ||
    OL_RE.test(line) ||
    line.startsWith('>')
  )
}

/** 多行拼一个块：块内换行用 `\n` 保留（`.ans-text` 是 pre-wrap，等于软换行） */
function runsOfLines(lines: string[]): MdRun[] {
  return runsOf(lines.join('\n'))
}

/**
 * 主入口：按行扫一遍，产出块列表。
 *
 * 永不抛错——md 解析失败也不能让回答不显示，真解析不了就退化成单段落文本。
 */
export function buildAnswerView(text: string): MdViewBlock[] {
  const blocks: MdViewBlock[] = []
  // 行尾先归一化：模型可能给 CRLF，`## 标题\r` 的 `$`（无 m 标志）不会匹配，
  // 标题与列表会整批退化成字面段落，`\r` 还留在正文里。`\r` 是行结构不是可见字符。
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // fenced code：开栏行起吃到**合规闭栏**；没有闭栏就吃到末尾（流式中途正是这样）
    const fence = FENCE_RE.exec(trimmed)
    if (fence !== null) {
      const opener = fence[1]
      // 闭栏 = 同字符、长度 ≥ 开栏、整行只有围栏字符（CommonMark 口径）。
      // 不能用 startsWith 判——体内以 ``` 开头的行（```` ``` 尾巴 ````、````` ```js 说明 `````）
      // 不是闭栏，是内容；按 startsWith 会把整行当闭栏消费掉，行内正文静默消失。
      const closeRe = new RegExp('^' + opener[0] + '{' + opener.length + ',}$')
      const body: string[] = []
      i += 1
      while (i < lines.length && !closeRe.test(lines[i].trim())) {
        body.push(lines[i])
        i += 1
      }
      i += 1
      // 块内是纯文本：不过 parseInline（围栏里的 `**` 就是两个星号），
      // 但仍切引用——「只用于扫描与渲染，不是净化」对代码块一视同仁
      const segments = citationSegments(body.join('\n'))
      blocks.push({ tag: 'pre', runs: segments.length > 0 ? [{ tag: 'span', segments }] : [] })
      continue
    }

    if (HR_RE.test(trimmed)) {
      blocks.push({ tag: 'hr' })
      i += 1
      continue
    }

    const heading = H_RE.exec(line)
    if (heading !== null) {
      // 夹到两级：H1 在聊天气泡里是页面级元素，不该由回答正文决定
      const level = heading[1].length
      blocks.push({ tag: level <= 2 ? 'h2' : 'h3', runs: runsOf(heading[2]) })
      i += 1
      continue
    }

    if (line.startsWith('>')) {
      const quoted: string[] = []
      while (i < lines.length && lines[i].startsWith('>')) {
        quoted.push(lines[i].replace(/^> ?/, ''))
        i += 1
      }
      // 引用块内部不再拆子块：多段用空行拼回一串 run，pre-wrap 下仍看得出分段
      const runs = runsOfLines(quoted)
      if (!isBlank(runs)) blocks.push({ tag: 'blockquote', runs })
      continue
    }

    if (UL_RE.test(line) || OL_RE.test(line)) {
      // 列表块只收同种标记的行：`- ` 与 `1. ` 混排时是两段，不是一个列表
      const ordered = OL_RE.test(line)
      const itemLines: string[][] = []
      const numbers: number[] = []
      while (i < lines.length) {
        const current = lines[i]
        const match = ordered ? OL_RE.exec(current) : UL_RE.exec(current)
        if (match !== null) {
          if (ordered) {
            numbers.push(Number(match[1]))
            itemLines.push([match[2]])
          } else {
            itemLines.push([match[1]])
          }
          i += 1
        } else if (current.trim() === '' || startsBlock(current) || itemLines.length === 0) {
          break
        } else {
          // 列表项的续行（软换行）：并进上一项
          itemLines[itemLines.length - 1].push(current)
          i += 1
        }
      }
      const items = itemLines.map(runsOfLines)
      blocks.push(ordered ? { tag: 'ol', items, numbers } : { tag: 'ul', items })
      continue
    }

    if (trimmed === '') {
      i += 1
      continue
    }

    // 段落：连续非空行，遇到块开头就停
    const paragraph: string[] = []
    while (i < lines.length && lines[i].trim() !== '') {
      if (paragraph.length > 0 && startsBlock(lines[i])) break
      paragraph.push(lines[i])
      i += 1
    }
    const runs = runsOfLines(paragraph)
    if (!isBlank(runs)) blocks.push({ tag: 'p', runs })
  }

  return blocks
}
