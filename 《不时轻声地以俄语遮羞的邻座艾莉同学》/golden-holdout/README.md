# Omniread M0 Golden 出题规范

本目录是给**出题方**的套件：你只负责产出题目，格式由 `schema.json` 定义，用 `validate_golden.py`
自校验。本文自解释——不需要读任何其他文档，照着写、跑一遍校验即可。

对象是一本小说：共 **193 章、15 卷**，`book_id` 恒为 `1`。题目是围绕这本书的剧情问答，
每道题都要说明答案依据在哪几章的哪几段原文里。

## 1. 怎么用

### 1.1 套件文件

完整套件是**四件套**，必须放在**同一个目录**（下称「数据集目录」），缺一个都无法自校验：

| 文件 | 作用 | 随仓库发布 |
| --- | --- | --- |
| `README.md` | 本文，出题规范 | 是 |
| `schema.json` | 单题结构定义（JSON Schema draft 2020-12） | 是 |
| `validate_golden.py` | 校验器，只用 Python 标准库，无需安装依赖 | 是（在 `scripts/`） |
| `example.json` | 一道完整示例题；校验器把它当辅助文件跳过，不参与数据集统计 | **否** |

**`example.json` 不随仓库发布**：它含原著短摘录，与题面同理。clone 之后手上只有前三件，
自备一道示例题即可，不影响出题与校验。从本仓库取件的命令：

```bash
# 在仓库根目录执行；<数据集目录> 换成你的目标目录
mkdir -p <数据集目录>
cp eval/golden/README.md eval/golden/schema.json <数据集目录>/
cp scripts/validate_golden.py <数据集目录>/
```

`validate_golden.py` 在本仓库里位于 `scripts/`，不在 `eval/golden/`；只复制 `eval/golden` 会缺校验器，§1.3 的命令会直接失败。

`schema.json`、`validate_golden.py` 都必须与题目文件同目录：校验器从被校验的目录里读取 `schema.json`，§1.3 的命令按校验器与题目同目录假定编写。

### 1.2 产出与命名

- **每题一个文件**，直接放在数据集目录下，不要再套子目录。
- 文件名 = 该题的 `id` = `<type>-<三位数字>.json`。例：`cross-001.json` 的 `id` 是 `cross-001`、`type` 是 `cross`。
- 三位数字从 `001` 起，同一类型内不重复；`id` 在整个数据集内唯一。
- 目录里除 `schema.json` / `example.json` 外，只允许出现符合上述命名的 `.json`。非题目的 `.json` 文件会被判为非法文件名并报错；`.txt` / `.md` 等非 `.json` 文件不被扫描（校验器只匹配 `*.json`），但草稿、笔记仍建议放在数据集目录之外。

### 1.3 自校验

```bash
# 出题过程中最常用：只校验一道题
python validate_golden.py <数据集目录>/fact-001.json

# 提交前：校验整个数据集（文件名约定、id 唯一、数量目标）
python validate_golden.py <数据集目录>
```

退出码：`0` 通过，`1` 有校验问题，`2` 用法或路径错误。

交付内容 = 数据集目录的全部内容：四件套 + 你产出的全部 `<id>.json` 题目文件。校验通过后再交付。

**必须跑这个校验器，不能只做 JSON Schema 校验。** `schema.json` 只覆盖单题结构；`level=past` 时
evidence 的 `chapter_index ≤ progress`（§5）、`id` 数据集内唯一、数量目标这几条跨字段 / 跨文件规则
`schema.json` 表达不了，由 `validate_golden.py` 权威执行。只拿通用 JSON Schema 工具过一遍结构，
会漏掉这些规则。

## 2. 字段

必填字段集：

```text
schema_version / id / type / difficulty / book_id / question
/ reference_points / level / expect_refusal / must_cite_groups
```

可选字段：`reference_answer`。字段集**不含** `source_seqs` / `must_not_claim` / `forbidden_patterns` / `notes`，
也不含其他任何未列出的键——出现即校验失败。

| 字段 | 类型 | 必填 | 取值 | 说明 |
| --- | --- | --- | --- | --- |
| `schema_version` | string | 是 | 固定 `"m0.1.0"` | 数据集格式版本，不要改 |
| `id` | string | 是 | `<type>-<三位数字>` | 全局唯一，且必须等于文件名 |
| `type` | string | 是 | 六桶之一 | 见 §3 |
| `difficulty` | string | 是 | `easy` / `medium` / `hard` | 难度，用于分层统计 |
| `book_id` | int | 是 | 固定 `1` | 书目 id |
| `question` | string | 是 | 非空 | 题面 |
| `reference_points` | string[] | 是 | 至少 1 条 | 评分要点，逐条列出回答必须命中的事实，建议 2–3 条 |
| `reference_answer` | string | 否 | 非空 | 一段完整参考回答，作为辅助 |
| `level` | string | 是 | `past` / `full` | `past` = 只在阅读进度内作答；`full` = 全书可见 |
| `progress` | int | 条件 | `1..193` | `level=past` 时**必填**；`level=full` 时**必须整个键缺省**（不要写 `null`） |
| `expect_refusal` | bool | 是 | `true` / `false` | 是否期望模型拒答，见 §6 |
| `must_cite_groups` | array | 是 | 至少 1 组，每组至少 1 条 | 必引证据，外层 AND、组内 OR，见 §4 |

`must_cite_groups` 里的 evidence 叶子只有两个键：

| 键 | 类型 | 必填 | 取值 | 说明 |
| --- | --- | --- | --- | --- |
| `chapter_id` | string | 是 | `book:1:chapter:{1..193}` | 章节标识，见 §8 |
| `content` | string | 是 | 原文片段 | 必须是**语料原文**，不是转述，见 §4 |

### 完整示例（`level=past`）

```json
{
  "schema_version": "m0.1.0",
  "id": "fact-001",
  "type": "fact",
  "difficulty": "easy",
  "book_id": 1,
  "question": "政近向艾莉莎借的是哪一科的参考书？",
  "reference_points": ["借的是化学参考书", "起因是他忘带下一节课要用的参考书"],
  "reference_answer": "政近忘带下一节课要用的参考书，向邻座的艾莉莎借了化学参考书。",
  "level": "past",
  "progress": 5,
  "must_cite_groups": [
    [
      {"chapter_id": "book:1:chapter:2", "content": "……语料原文片段……"}
    ]
  ],
  "expect_refusal": false
}
```

`level=full` 的题结构相同，但**不要写 `progress`**：

```json
{
  "schema_version": "m0.1.0",
  "id": "cross-002",
  "type": "cross",
  "difficulty": "medium",
  "book_id": 1,
  "question": "艾莉莎在学园的公开形象，与政近对她的称呼之间有什么落差？",
  "reference_points": ["公开形象是被视为完美超人的才女", "政近私下以「艾莉」这一昵称称呼她"],
  "level": "full",
  "must_cite_groups": [
    [{"chapter_id": "book:1:chapter:1", "content": "……语料原文片段……"}],
    [{"chapter_id": "book:1:chapter:2", "content": "……语料原文片段……"}]
  ],
  "expect_refusal": false
}
```

上面 `content` 里的「……语料原文片段……」是**占位符，必须换成从语料复制的真实原文片段**（规则见 §4）；
照抄占位符不构成有效证据。这个模板的 id 只是示例，出题时换成你自己的、数据集内唯一的 id。

本地数据集目录里的 `example.json` 是一道跨第 34 章与第 45 章的真实示例，可直接参考；它的 id 是
`cross-001`，作为辅助文件被校验器跳过，不参与 id 唯一性检查与数量统计。
**它不随仓库发布**（含原文片段），所以 clone 之后没有这道示例可看——上面两个模板就是全部示例。

## 3. 六桶判据

`type` 决定这道题在测什么。每道题都要能回答「这题值得测在哪里」，而不是换个问法凑数。

- **`fact`**：证据落在单章内，一次检索就能找到并回答。测最基础的「定位 + 答对」，
  也是其他类型出问题时的对照基线。
- **`alias`**：题面用的是别名、昵称或称号，正文用的是正式称呼（或反过来），必须做称呼归并才能召回。
  例：题面写「艾莉」，正文写「艾莉莎·米哈伊罗夫纳·九条」。测查询用词与正文用词不一致时的召回。
- **`cross`**：证据跨多章，必须拼合多个 `must_cite_groups` 才能回答。测多跳信息整合——
  只看任何单独一章都答不完整。
- **`foreshadow`**：伏笔与兑现分处不同章，需要把前文的铺垫与后文的揭示关联起来。测长距离依赖，
  这类信息在单章内往往看不出意义。
- **`boundary`**：证据紧贴 `progress` 边界（刚好落在进度内的最后一两章）。测边界处的召回是否稳定、
  以及进度之外的内容是否被挡住。
- **`spoiler`**：答案位于 `progress` 之后，`expect_refusal` **必须为 `true`**，且正确回答里不得出现后续剧情。
  测防剧透——这是整条链路最关键的一条约束。校验器强制 `spoiler` 桶必须期望拒答。

## 4. evidence 规则

- **必须是原文片段，不是转述。** `content` 之后要拿去和正文切片做映射，转述会让映射失准，
  召回数据跟着失真。直接从语料里复制原句，长度取数十字到数百字，能覆盖一个完整语义单元即可。
- **只存 `chapter_id` + `content`，不存 `chunk_id`。** 切片方案会变，章节归属和原文不会变。
- **`chapter_id` 格式固定** `book:{book_id}:chapter:{chapter_index}`，M0 即 `book:1:chapter:N`。
- **外层 AND、组内 OR。** 组内多条 evidence 只要命中一条就算该组命中；所有组都命中才算整题命中。
  把「同一处事实的不同表述」放同一组，把「必须分别命中的不同章证据」放不同组。
- 校验器无法判断一段文字是否原文，这一条靠出题时人工保证。

## 5. progress 与防剧透

`level=past` 的题必须给出 `progress`（已读到第几章，`1..193`），表示只允许看到第 `progress` 章为止。

**硬规则：`level=past` 的题，每条 evidence 的 `chapter_index` 必须 ≤ 该题的 `progress`。**
违反直接校验失败——防剧透是数据约束，越界的题在出题阶段就被拦住，不会等发现问题才返工。

这条规则**不在 `schema.json` 里**：纯 JSON Schema 无法比较 evidence 的 `chapter_index` 与本题
`progress` 两个字段，因此由 `validate_golden.py` 权威执行（§1.3）。只用通用 JSON Schema 工具
校验结构，不会发现越界，必须跑本校验器。

- `boundary` 桶：把 `progress` 设成 evidence 所在的那一章，正好压住边界。
- `spoiler` 桶：把 `progress` 设在答案出现之前。
- `level=full` 的题不受此约束，但必须省略 `progress`。

## 6. 拒答题

`expect_refusal: true` 的题，必须在 `progress` 域内**确实没有答案**——是「这个域内确实找不到」，
不是「我一时没找到」。出题前请通读 `progress` 以内的章节，确认没有任何一章能回答该问题；
只要域内存在答案，就不是拒答题，应当改成普通题或调整 `progress`。

- `spoiler` 桶固定 `expect_refusal: true`（校验器强制）。
- 其他桶也可以出拒答题，例如问一个在 `progress` 域内完全没提到的角色关系。
- 拒答题同样要写非空的 `must_cite_groups`（结构要求），放 `progress` 域内与问题相关、
  但不足以回答的片段；它们同样受 §5 的 `≤ progress` 约束。

## 7. 数量目标

以下按**整个数据集**统计，不是单文件校验：

| 指标 | 目标 |
| --- | --- |
| 总量 | ≥ 60 |
| 单类型（六桶各计） | ≥ 8 |
| 拒答题（`expect_refusal=true`） | ≥ 10 |

校验器会在目录级统计这些数字，未达标即报错。

## 8. 章节号怎么查

语料根目录的 `index.jsonl` 是权威章节清单：**第 N 行（从 1 数）就是 `chapter_index = N`**，
共 193 行。`book_id` 恒为 1，所以 `chapter_id = book:1:chapter:N`。

15 卷的卷序号与卷名对照（`volume_index` 按卷名在 `index.jsonl` 中首次出现的次序）：

| `volume_index` | 卷名 | 章节范围 |
| --- | --- | --- |
| 1 | 第一卷 | 1–11 |
| 2 | 第二卷 | 12–22 |
| 3 | 第三卷 | 23–33 |
| 4 | 第四卷 | 34–46 |
| 5 | 第4.5卷 Summer Stories | 47–60 |
| 6 | 第五卷 | 61–74 |
| 7 | 第六卷 | 75–89 |
| 8 | 第七卷 | 90–103 |
| 9 | 第八卷 | 104–116 |
| 10 | 短篇 | 117 |
| 11 | 第九卷 | 118–130 |
| 12 | 短篇集 秘闻 | 131–163 |
| 13 | 第十卷 | 164–176 |
| 14 | BD特典 | 177–182 |
| 15 | 第十一卷 | 183–193 |

章节范围只用于帮你定位，`chapter_id` 里只写 `chapter_index`，不写卷名。
第 1 章标题是「序章 孤傲的公主大人与怠惰的邻人」。

## 9. 红线

- **整本语料不得进入数据集目录。** 包括 `index.jsonl`、章节导出文件、合并全文、`epub/`、图片——
  一律不拷贝。
- **只有 evidence 的短片段随题目保存**，每题只取回答所必需的几十到几百字，不要整段整章搬运。
- **随仓库发布的那几份（本文件、`schema.json`、`validate_golden.py`）里不得出现任一题 evidence 的原文。**
  题面与 evidence 只留在本地，跟着仓库走的只有规范与校验器（§1.1 那张表标了哪几件发布）。
  所以**本文档自己的示例一律用占位符** `……语料原文片段……`——示例写得太像真的，本身就是一次泄漏。
- 这三条是硬要求：题目目录会被复制、提交和分发，原文一旦进去就收不回来——
  `docs/` 之外的历史改写代价极高。

## 10. 一致性：冻结后改题即新版本

- 出题完成、校验通过后，把校验器打印的 `dataset_hash` 记下并**冻结**。
- `dataset_hash` 口径固定：按 `id` 升序，逐题做规范序列化（键排序、UTF-8、无尾随空白），
  以换行连接后取 sha256。任何人用同一批文件都能算出同一个值。
- 冻结后只要改动任何一个字节（改题面、改 `progress`、换 evidence），`dataset_hash` 就会变，
  **即视为一个新版本**：不要把改过的题和未改的题混在同一个目录里当作同一版继续用。
- 改题请在干净副本上改，改完重新校验并记录新的 `dataset_hash`。
- `schema_version` 只在格式（字段集或校验规则）变更时才升；纯内容变更靠 `dataset_hash` 区分。
