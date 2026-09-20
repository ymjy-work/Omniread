/**
 * 引用标记 `[C{chapter_index}]` 的扫描与渲染（TS 侧实现）。
 *
 * 权威定义在仓库根 `citation-format.json`：正则、语义与样本都只有那一份。
 * 两语言无法共用同一个文件，所以这里复制一份实现，Python 侧在
 * `services/rag/src/omniread/domain/citation.py`，两侧由
 * `services/rag/tests/test_citation_equivalence.py` 用同一批样本断言等价。
 *
 * 三条口径：
 * - 大小写敏感：`[c17]` 不是引用。
 * - 捕获组必须无前导零：`[C017]` 不是引用。
 * - 只用于扫描与渲染，不是净化规则：正文原样输出，越界引用与违规写法都保留。
 */

/** 规范引用正则源码，与 citation-format.json 的 `pattern` 逐字一致 */
export const CITATION_PATTERN = '\\[C(\\d{1,3})\\]'

/** 非规范写法的候选扫描正则源码，与 citation-format.json 的 `candidate_pattern` 逐字一致 */
export const CANDIDATE_PATTERN = '\\[[Cc]\\d[^\\]]*\\]'

const CANDIDATE_RE = new RegExp(CANDIDATE_PATTERN, 'g')
const CITATION_FULL_RE = new RegExp(`^(?:${CITATION_PATTERN})$`)

export interface CitationHit {
  chapterIndex: number
  /** 命中的原文片段（含方括号） */
  text: string
  /** 在原文中的起止下标（UTF-16 码元，JS 字符串语义） */
  start: number
  end: number
}

export interface CitationSegment {
  kind: 'text' | 'citation'
  text: string
  /** 仅 kind === 'citation' 时有值 */
  chapterIndex: number | null
}

/** 前导零（`017`）不算规范写法；`0` 本身没有前导零，仍是规范数字 */
export function isCanonicalNumber(digits: string): boolean {
  return digits !== '' && !(digits.length > 1 && digits.startsWith('0'))
}

/** 扫描正文中全部**规范**引用，按出现顺序返回 */
export function findCitations(text: string): CitationHit[] {
  const hits: CitationHit[] = []
  for (const match of text.matchAll(CANDIDATE_RE)) {
    const raw = match[0]
    const canonical = CITATION_FULL_RE.exec(raw)
    if (canonical === null || !isCanonicalNumber(canonical[1])) continue
    const start = match.index ?? 0
    hits.push({ chapterIndex: Number(canonical[1]), text: raw, start, end: start + raw.length })
  }
  return hits
}

/** 扫描正文中全部非规范写法（计违规，不忽略），按出现顺序返回原文片段 */
export function findViolations(text: string): string[] {
  const citationStarts = new Set(findCitations(text).map((hit) => hit.start))
  return [...text.matchAll(CANDIDATE_RE)]
    .filter((match) => !citationStarts.has(match.index ?? 0))
    .map((match) => match[0])
}

/**
 * 把正文切成「普通文本 / 规范引用」交替的片段，供渲染层插入角标。
 * 非规范写法落在普通文本片段里，原样显示。
 */
export function citationSegments(text: string): CitationSegment[] {
  const segments: CitationSegment[] = []
  let cursor = 0
  for (const hit of findCitations(text)) {
    if (hit.start > cursor) {
      segments.push({ kind: 'text', text: text.slice(cursor, hit.start), chapterIndex: null })
    }
    segments.push({ kind: 'citation', text: hit.text, chapterIndex: hit.chapterIndex })
    cursor = hit.end
  }
  if (cursor < text.length) {
    segments.push({ kind: 'text', text: text.slice(cursor), chapterIndex: null })
  }
  return segments
}
