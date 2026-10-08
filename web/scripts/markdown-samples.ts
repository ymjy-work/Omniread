/**
 * 受限 Markdown 解析器（`src/markdown.ts` 的 `buildAnswerView`）的回归样本。
 *
 * **为什么是脚本、不引 vitest**：解析器是纯函数，喂字符串看块结构，零依赖的脚本就够；
 * 加一个测试框架要多一个依赖加一套配置（`docs/M1-plan.md` M1-3）。
 *
 * **为什么要挂解析钩子**：`src/markdown.ts` 里有无扩展名的相对导入（`from './citation'`），
 * 而 Node 的 ESM 解析要求显式扩展名。`scripts/ts-resolve-hook.mjs` 补上这一步，
 * 代价是 15 行，`src/` 一行没动——把那一行改成 `./citation.ts` 会让它成为 `src` 下
 * 唯一带扩展名导入的文件，为测试改产品代码的写法不划算。
 *
 * **期望值的写法**（`describeBlocks` 就是照这个规则把块结构压平）：
 *
 * - 块之间用换行连接：`hr`；`p|` / `h2|` / `h3|` / `blockquote|` / `pre|` 后接 run 串；
 *   无序列表 `ul|[项1][项2]`；有序列表 `ol(编号,...)|[项1][项2]`（编号按源文原样列出）
 * - run 串：span 原样；strong 写成 `<b>文本</b>`；code 写成 `<c>文本</c>`
 * - run 文本里的规范引用写成 `<C章节号>`；**非规范写法原样保留**（`[c17]`、`[C017]`）
 *
 * 用例覆盖的是**会静默出错**的行为：错一个字就渲染错、或者正文悄悄消失。
 * 每条用例的期望值都对过 `src/markdown.ts` 的 docstring（那是这份解析器的规格），
 * 不是照抄实现输出——照抄会把 bug 一起冻进回归。
 *
 * 用法：
 *   npm run check:markdown
 *   node --import ./scripts/ts-resolve-hook.mjs scripts/markdown-samples.ts --only 围栏
 */
import { pathToFileURL } from 'node:url'

import { buildAnswerView } from '../src/markdown.ts'
import type { MdRun, MdViewBlock } from '../src/markdown.ts'

interface Case {
  /** 这条钉的是什么 */
  name: string
  input: string
  /** 见文件头的写法说明 */
  expect: string
}

/** run 串：span 原样、strong 包 `<b>`、code 包 `<c>`，引用片段写成 `<C7>`。 */
function describeRun(run: MdRun): string {
  const text = run.segments
    .map((segment) => (segment.kind === 'citation' ? `<C${segment.chapterIndex}>` : segment.text))
    .join('')
  if (run.tag === 'strong') return `<b>${text}</b>`
  if (run.tag === 'code') return `<c>${text}</c>`
  return text
}

function describeItems(items: MdRun[][]): string {
  return items.map((item) => `[${item.map(describeRun).join('')}]`).join('')
}

export function describeBlocks(blocks: MdViewBlock[]): string {
  return blocks
    .map((block) => {
      if (block.tag === 'hr') return 'hr'
      if (block.tag === 'ul') return `ul|${describeItems(block.items)}`
      if (block.tag === 'ol') return `ol(${block.numbers.join(',')})|${describeItems(block.items)}`
      return `${block.tag}|${block.runs.map(describeRun).join('')}`
    })
    .join('\n')
}

const CASES: Case[] = [
  {
    name: "围栏体内以 ``` 开头的行是内容不是闭栏",
    input: "```\n``` 尾巴\n```",
    expect: "pre|``` 尾巴",
  },
  {
    name: "闭栏必须不短于开栏（4 个反引号开的，3 个不算闭）",
    input: "````\n```\n````",
    expect: "pre|```",
  },
  {
    name: "闭栏必须同字符（``` 开的，~~~ 不闭）",
    input: "```\n~~~\n```",
    expect: "pre|~~~",
  },
  {
    name: "闭栏长于开栏也算闭栏",
    input: "```\ncode\n`````",
    expect: "pre|code",
  },
  {
    name: "开栏的 info string 被忽略（```js）",
    input: "```js\nconst a = 1\n```",
    expect: "pre|const a = 1",
  },
  {
    name: "未闭合围栏吃到末尾（流式）",
    input: "```\n正在生成",
    expect: "pre|正在生成",
  },
  {
    name: "未闭合围栏不因空行结束（流式）",
    input: "```\n代码\n\n下一段",
    expect: "pre|代码\n\n下一段",
  },
  {
    name: "围栏体内块标记不解析（# 开头的行是内容）",
    input: "```\n# 不是标题",
    expect: "pre|# 不是标题",
  },
  {
    name: "围栏体内不解析行内格式（** 就是两个星号）",
    input: "```\n**不该变粗**\n```",
    expect: "pre|**不该变粗**",
  },
  {
    name: "围栏体内仍切引用",
    input: "```\n见 [C7]\n```",
    expect: "pre|见 <C7>",
  },
  {
    name: "~~~ 围栏体内的 ``` 是内容",
    input: "~~~\n```\n~~~",
    expect: "pre|```",
  },
  {
    name: "段落遇围栏开头就停（没有空行也是）",
    input: "开头\n```\ncode\n```\n结尾",
    expect: "p|开头\npre|code\np|结尾",
  },
  {
    name: "分隔线三种写法都成立",
    input: "---\n***\n___",
    expect: "hr\nhr\nhr",
  },
  {
    name: "正文后紧跟 --- 是分隔线不是 setext 标题",
    input: "正文\n---",
    expect: "p|正文\nhr",
  },
  {
    name: "两个连字符不是分隔线",
    input: "--",
    expect: "p|--",
  },
  {
    name: "# 与 ## 一律夹到 h2",
    input: "# 一级标题\n## 二级标题",
    expect: "h2|一级标题\nh2|二级标题",
  },
  {
    name: "### 起一律夹到 h3",
    input: "### 三级标题\n###### 六级标题",
    expect: "h3|三级标题\nh3|六级标题",
  },
  {
    name: "七个 # 不是标题",
    input: "####### 七级",
    expect: "p|####### 七级",
  },
  {
    name: "段落遇标题开头就停（没有空行也是）",
    input: "正文\n# 标题",
    expect: "p|正文\nh2|标题",
  },
  {
    name: "段落遇列表开头就停（没有空行也是）",
    input: "正文\n- 项",
    expect: "p|正文\nul|[项]",
  },
  {
    name: "空行分段：连续多个空行只分一次",
    input: "第一段\n\n\n第二段",
    expect: "p|第一段\np|第二段",
  },
  {
    name: "全空白行也算空行",
    input: "甲\n   \n乙",
    expect: "p|甲\np|乙",
  },
  {
    name: "首尾空行不产出空块",
    input: "\n\n甲\n\n",
    expect: "p|甲",
  },
  {
    name: "CRLF 归一化：标题与列表不退化成段落",
    input: "## 标题\r\n- 项",
    expect: "h2|标题\nul|[项]",
  },
  {
    name: "孤立 CR 也归一化",
    input: "# 标题\r正文",
    expect: "h2|标题\np|正文",
  },
  {
    name: "闭栏行两侧空白不影响判定",
    input: "```\ncode\n  ```  \n正文",
    expect: "pre|code\np|正文",
  },
  {
    name: "闭栏后紧跟下一个开栏（相邻两个围栏块）",
    input: "```\na\n```\n```\nb\n```",
    expect: "pre|a\npre|b",
  },
  {
    name: "无序列表连续行合并为一个列表",
    input: "- 甲\n- 乙",
    expect: "ul|[甲][乙]",
  },
  {
    name: "连字符与星号混用仍属同一个无序列表",
    input: "- 甲\n* 乙",
    expect: "ul|[甲][乙]",
  },
  {
    name: "星号不跟空格时整行是段落（不吞粗体开头）",
    input: "**重点**",
    expect: "p|<b>重点</b>",
  },
  {
    name: "星号跟空格才是列表项、项内粗体照常解析",
    input: "* **重点**",
    expect: "ul|[<b>重点</b>]",
  },
  {
    name: "无序行与有序行混排拆成两个块（ul→ol）",
    input: "- 甲\n1. 乙",
    expect: "ul|[甲]\nol(1)|[乙]",
  },
  {
    name: "有序行与无序行混排拆成两个块（ol→ul）",
    input: "3. 甲\n- 乙",
    expect: "ol(3)|[甲]\nul|[乙]",
  },
  {
    name: "有序列表源编号原样还原（非 1 起、跳号、两位数）",
    input: "3. 甲\n10. 乙",
    expect: "ol(3,10)|[甲][乙]",
  },
  {
    name: "有序列表续行时编号仍与各条目对齐",
    input: "2. 甲\n附注行\n3. 乙",
    expect: "ol(2,3)|[甲\n附注行][乙]",
  },
  {
    name: "列表项续行以软换行并入上一项（换行保留）",
    input: "- 第一行\n继续的软换行",
    expect: "ul|[第一行\n继续的软换行]",
  },
  {
    name: "续行只并入紧邻上一项，不吞下一项",
    input: "- 甲\n继续\n- 乙",
    expect: "ul|[甲\n继续][乙]",
  },
  {
    name: "仅含空格的行也结束列表",
    input: "- 甲\n \n- 乙",
    expect: "ul|[甲]\nul|[乙]",
  },
  {
    name: "空行后的正文是独立段落而不是续行",
    input: "- 甲\n\n正文段落",
    expect: "ul|[甲]\np|正文段落",
  },
  {
    name: "标题行结束列表",
    input: "- 甲\n## 小标题",
    expect: "ul|[甲]\nh2|小标题",
  },
  {
    name: "引用块行结束列表",
    input: "- 甲\n> 引文",
    expect: "ul|[甲]\nblockquote|引文",
  },
  {
    name: "分隔线结束列表",
    input: "- 甲\n---",
    expect: "ul|[甲]\nhr",
  },
  {
    name: "围栏代码块开栏结束列表",
    input: "- 甲\n```\n原样代码",
    expect: "ul|[甲]\npre|原样代码",
  },
  {
    name: "缩进的「- 」不构成嵌套列表，原样并进上一项",
    input: "- 甲\n  - 乙",
    expect: "ul|[甲\n  - 乙]",
  },
  {
    name: "列表项内规范引用切成角标",
    input: "- 见 [C7]。",
    expect: "ul|[见 <C7>。]",
  },
  {
    name: "列表项内行内代码与引用各自解析",
    input: "- 用 `npm test` 验证 [C7]",
    expect: "ul|[用 <c>npm test</c> 验证 <C7>]",
  },
  {
    name: "粗体内的引用同样切分",
    input: "- **见 [C7]**",
    expect: "ul|[<b>见 <C7></b>]",
  },
  {
    name: "列表项内违规引用写法原样保留（不净化）",
    input: "- 写法 [c7] 与 [C017] 保留",
    expect: "ul|[写法 [c7] 与 [C017] 保留]",
  },
  {
    name: "列表项内未闭合粗体视为普通文本",
    input: "- **未闭合",
    expect: "ul|[**未闭合]",
  },
  {
    name: "续行以 ** 开头时并入上一项且粗体照常",
    input: "- 甲\n**重点**",
    expect: "ul|[甲\n<b>重点</b>]",
  },
  {
    name: "粗体成对生成三个 run（前/中/后）",
    input: "前**中**后",
    expect: "p|前<b>中</b>后",
  },
  {
    name: "整行粗体：是段落不是无序列表",
    input: "**粗体**",
    expect: "p|<b>粗体</b>",
  },
  {
    name: "粗体闭合标记贴行尾",
    input: "句末是**粗体**",
    expect: "p|句末是<b>粗体</b>",
  },
  {
    name: "行内代码整段成一个 code run",
    input: "`代码`",
    expect: "p|<c>代码</c>",
  },
  {
    name: "代码内部不再解析星号",
    input: "`**粗**`",
    expect: "p|<c>**粗**</c>",
  },
  {
    name: "代码 run 内的引用照样切",
    input: "`[C7]`",
    expect: "p|<c><C7></c>",
  },
  {
    name: "粗体 run 内的引用照样切",
    input: "**[C7]**",
    expect: "p|<b><C7></b>",
  },
  {
    name: "粗体包代码不拆出孤儿星号",
    input: "**`[C8]`**",
    expect: "p|<c><C8></c>",
  },
  {
    name: "粗体包代码时两侧文本仍归粗体",
    input: "**前`[C8]`后**",
    expect: "p|<b>前</b><c><C8></c><b>后</b>",
  },
  {
    name: "未闭合粗体保持普通文本",
    input: "这是**未闭合",
    expect: "p|这是**未闭合",
  },
  {
    name: "未闭合反引号保持普通文本",
    input: "`未闭合",
    expect: "p|`未闭合",
  },
  {
    name: "行尾游离的开标记不并入粗体",
    input: "**粗**尾**",
    expect: "p|<b>粗</b>尾**",
  },
  {
    name: "单个星号不成斜体",
    input: "*斜体*",
    expect: "p|*斜体*",
  },
  {
    name: "两个单星号不跨文本配对",
    input: "开始 * 中间 * 结束",
    expect: "p|开始 * 中间 * 结束",
  },
  {
    name: "三星号只取中间那段粗体，外圈星号保留",
    input: "***粗***",
    expect: "p|*<b>粗</b>*",
  },
  {
    name: "粗体紧邻代码各占一段",
    input: "**粗**`码`",
    expect: "p|<b>粗</b><c>码</c>",
  },
  {
    name: "代码紧邻粗体各占一段",
    input: "`码`**粗**",
    expect: "p|<c>码</c><b>粗</b>",
  },
  {
    // 模块 docstring 曾把 `**`x`**` 举成「粗体嵌代码」的例句，但 run 是扁平单标签、
    // 表达不了嵌套：整段都是代码时不产生 strong，两个 `**` 对结果零效果。
    // 钉住它是为了下次再动这条路径时，这个「写了加粗、渲染里没有加粗」的取舍不会被悄悄改掉。
    name: "整段都是代码的粗体只产出 code，不产生 strong",
    input: "**`乙`**",
    expect: "p|<c>乙</c>",
  },
  {
    name: "粗体里夹代码时，代码与粗体是兄弟 run 而不是嵌套",
    input: "**前`中`后**",
    expect: "p|<b>前</b><c>中</c><b>后</b>",
  },
  {
    name: "四星号拆成相邻两段粗体",
    input: "**甲****乙**",
    expect: "p|<b>甲</b><b>乙</b>",
  },
  {
    name: "粗体内含单星号时整段不成立",
    input: "**2*3**",
    expect: "p|**2*3**",
  },
  {
    name: "普通文本 run 里的引用切成片段",
    input: "见 [C7]。",
    expect: "p|见 <C7>。",
  },
  {
    name: "粗体内引用两侧的字符一个不丢",
    input: "**见 [C7]。**",
    expect: "p|<b>见 <C7>。</b>",
  },
  {
    name: "行内代码内不解析格式、但引用照切",
    input: "`**[C7]**`",
    expect: "p|<c>**<C7>**</c>",
  },
  {
    name: "围栏块内不解析行内格式、只切引用",
    input: "```\n**见 [C7]**\n```",
    expect: "pre|**见 <C7>**",
  },
  {
    name: "多行代码块两行都切引用、换行原样",
    input: "```\n第一 [C7]\n第二 [C8]\n```",
    expect: "pre|第一 <C7>\n第二 <C8>",
  },
  {
    name: "小写 [c17] 不切、同 run 的 [C7] 照切",
    input: "见 [c17] 与 [C7]",
    expect: "p|见 [c17] 与 <C7>",
  },
  {
    name: "粗体 run 里前导零 [C017] 原样保留",
    input: "**[C017]**",
    expect: "p|<b>[C017]</b>",
  },
  {
    name: "三位内是引用、四位不是（跨 run 对照）",
    input: "`[C999]` 与 [C1234]",
    expect: "p|<c><C999></c> 与 [C1234]",
  },
  {
    name: "数字后多一个空格不算引用、空格不丢",
    input: "**见 [C7 ]。**",
    expect: "p|<b>见 [C7 ]。</b>",
  },
  {
    name: "段首段尾与相邻引用一个不落",
    input: "[C1]甲[C2]",
    expect: "p|<C1>甲<C2>",
  },
  {
    name: "斜体星号与引用互不干扰",
    input: "*斜体* [C7] *再斜体*",
    expect: "p|*斜体* <C7> *再斜体*",
  },
  {
    name: "未闭合粗体里的引用仍然切",
    input: "**见 [C7]",
    expect: "p|**见 <C7>",
  },
  {
    name: "引用被粗体拆开时不跨 run 拼回",
    input: "[C**7**]",
    expect: "p|[C<b>7</b>]",
  },
  {
    name: "全角数字不是引用（两语言口径一致）",
    input: "[C7] 与 [C７]",
    expect: "p|<C7> 与 [C７]",
  },
  {
    name: "空输入不产出任何块",
    input: "",
    expect: "",
  },
  {
    name: "只有空行的帧不产出块",
    input: "\n\n\n",
    expect: "",
  },
  {
    name: "纯空白（空格与制表符）等同空行",
    input: "   \t  ",
    expect: "",
  },
  {
    name: "首尾换行不产出空块",
    input: "\n正文\n",
    expect: "p|正文",
  },
  {
    name: "CRLF 行尾先归一化，标题不退化、\\r 不进正文",
    input: "## 标题\r\n正文",
    expect: "h2|标题\np|正文",
  },
  {
    name: "半截闭栏（两个反引号）留在体内不消失",
    input: "```\ncode\n``",
    expect: "pre|code\n``",
  },
  {
    name: "闭栏补齐后成为完整代码块",
    input: "```\ncode\n```",
    expect: "pre|code",
  },
  {
    name: "围栏体内以 ``` 开头的行是内容不是闭栏",
    input: "```\n```js 说明\n真正的内容\n```",
    expect: "pre|```js 说明\n真正的内容",
  },
  {
    name: "~~~ 围栏同样不解析行内、只切引用",
    input: "~~~\n**粗** 见 [C3]\n~~~",
    expect: "pre|**粗** 见 <C3>",
  },
  {
    name: "未闭合围栏不因空行停手",
    input: "```\n码\n\n后文",
    expect: "pre|码\n\n后文",
  },
  {
    name: "半截列表：只有「- 」、项为空",
    input: "要点：\n- ",
    expect: "p|要点：\nul|[]",
  },
  {
    name: "列表项续行并进上一项",
    input: "- 第一项\n项内第二行",
    expect: "ul|[第一项\n项内第二行]",
  },
  {
    name: "有序列表标记「2.」没有空格时并入上一项",
    input: "1. 一\n2.",
    expect: "ol(1)|[一\n2.]",
  },
  {
    name: "有序列表补全后成为第二项且编号原样",
    input: "1. 一\n2. 二",
    expect: "ol(1,2)|[一][二]",
  },
  {
    name: "只有「>」的帧不产出空引用块",
    input: ">",
    expect: "",
  },
  {
    name: "引用块连续行合并为一段",
    input: "> 一\n> 二",
    expect: "blockquote|一\n二",
  },
  {
    name: "未闭合的 ** 是两个普通字符",
    input: "前**中",
    expect: "p|前**中",
  },
  {
    name: "末尾未闭合的 ** 不吞掉前面的粗体",
    input: "**粗体** 和 **未闭合",
    expect: "p|<b>粗体</b> 和 **未闭合",
  },
  {
    name: "半截引用原样显示不消失",
    input: "见 [C7",
    expect: "p|见 [C7",
  },
  {
    name: "空列表项照样出块——isBlank 管不到列表侧",
    input: "- \n- ",
    expect: "ul|[][]",
  },
  {
    name: "空引用块整块消失——同一份空白在引用侧被抑制",
    input: ">\n>",
    expect: "",
  },
  {
    name: "只有开栏行的围栏产出空 pre（流式第一帧）",
    input: "```",
    expect: "pre|",
  },
  {
    name: "空标题（井号+一个空格）退化成字面段落",
    input: "## ",
    expect: "p|## ",
  },
  {
    name: "空标题多一个空格反而命中——产出空 h2",
    input: "##   ",
    expect: "h2|  ",
  },
  {
    name: "原文行非空但解析后全空白的段落被整块丢掉",
    input: "** **",
    expect: "",
  },
  {
    name: "CRLF：列表行同理（行首锚定正则不吃行尾 CR）",
    input: "- 甲\r\n- 乙",
    expect: "ul|[甲][乙]",
  },
  {
    name: "行首空白按块型分叉：缩进列表项是段落、缩进分隔线是 hr",
    input: "  - 甲",
    expect: "p|  - 甲",
  },
]

function main(): number {
  const onlyIndex = process.argv.indexOf('--only')
  const only = onlyIndex >= 0 ? process.argv[onlyIndex + 1] : undefined
  const cases = only === undefined ? CASES : CASES.filter((item) => item.name.includes(only))

  const failures: string[] = []
  for (const item of cases) {
    let actual: string
    try {
      actual = describeBlocks(buildAnswerView(item.input))
    } catch (error) {
      // `buildAnswerView` 承诺永不抛错——抛了就是契约破了，单独报出来。
      failures.push(`${item.name}\n  输入 ${JSON.stringify(item.input)}\n  抛错 ${String(error)}`)
      continue
    }
    if (actual !== item.expect) {
      failures.push(
        `${item.name}\n  输入 ${JSON.stringify(item.input)}\n` +
          `  期望 ${JSON.stringify(item.expect)}\n  实际 ${JSON.stringify(actual)}`,
      )
    }
  }

  if (failures.length > 0) {
    console.error(`markdown 回归：${failures.length}/${cases.length} 条不符合期望\n`)
    for (const failure of failures) console.error(`- ${failure}\n`)
    return 1
  }
  console.log(`markdown 回归：${cases.length} 条通过${only === undefined ? '' : `（--only ${only}）`}`)
  return 0
}

// 只有作为入口运行时才跑用例。直接执行才是入口，`import` 不是——否则谁 import 一下
// `describeBlocks`（调试探针常这么干）就会把整套跑一遍再退出，拿不到函数。
const invokedDirectly =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) process.exit(main())
