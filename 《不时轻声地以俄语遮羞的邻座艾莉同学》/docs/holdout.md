# 调参验证留出集（30 题）

**用途**：**校验 86 道本身**，防止调参时的选择偏差被误读成「系统真的提升了」。已冻结的 86 题（`golden/`）是调参时看着调的集合，用它自己证明调参有效是循环论证；这 30 道没参与调参，只用来在调完之后复核一遍。

**因此它不并入 `golden/`，也不写回 `D:\DevProjects\webApp\Omniread\eval\`。** 一旦进入项目仓库的评测目录，它就会被卷进调参循环，退回成第二个「86 题」，这 30 道就白出了。它只留在本仓库，作为对照。

**本文件不属于交付内容。** 交付物是 `golden-holdout/` 目录本身。

## 目录约定

`golden-holdout/` 是**独立数据集目录**，自带套件四件套（`README.md` / `schema.json` / `example.json` / `validate_golden.py`，均与 `golden/` 同内容），与 `golden/` 平级、互不覆盖。

### 编号从 101 起

规范 §1.2 说三位数字「从 001 起」。这里**故意从 101 起**：

- 留出集与 `golden/` 会被同一个评测流程加载（86 + 30 = 116），`id` 在合并后必须仍然唯一；
- 若沿用 001，`cross-001` 在两边各有一个，合并时直接撞车。

所以 `cross-101`…`cross-108`、`alias-101`…`alias-106`、`boundary-101`…`boundary-106`、`fact-101`…`fact-103`、`foreshadow-101`…`foreshadow-104`、`spoiler-101`…`spoiler-103`。文件名仍满足 §1.2 的 `<type>-<三位数字>.json` 约定，校验器照常识别。

### 数量目标会报 FAIL，这是预期的

规范 §7 的数量目标（总量 ≥60、每桶 ≥8、拒答题 ≥10）按**整个数据集**统计。留出集只有 30 题，跑目录级校验必然出现：

```
FAIL 总量: 30（目标 ≥60）
FAIL   alias: 6（目标 ≥8）  …
```

**这不是缺陷。** 留出集不是一份可独立交付的数据集，它是 `golden/` 的补充集；数量目标对「补充集」没有意义。校验口径相应改为：

- 逐题校验：`python golden-holdout/validate_golden.py golden-holdout/<文件名>` —— 这条必须全过；
- 跨文件规则（文件名 = id、合并后 id 唯一、逐字原文、无重复片段）由 `temp/holdout_check.py` 补；
- 目录级校验照跑，只看结构类报错，忽略数量目标那几行 FAIL。

## 出题口径（与 `golden/` 的差异）

| 项 | `golden/` 现状 | 本留出集 |
| --- | --- | --- |
| 编号 | 每桶 001 起 | 每桶 101 起（见上） |
| `difficulty` | 存量题保留原值不迁移（`fact` 全 easy、`cross` 几乎全 hard、alias/boundary 全 medium，与桶重合） | **不写该字段**。难度维度已于 2026-10-13 废弃，见下 |
| 章节取材 | 引用 98 章，95 章零 evidence | 优先取材于那 95 章，降低「调参时见过这些章」的混淆 |
| `boundary` 桶 | 13 道全部退化成 `fact`（`progress` 恰好等于证据章，题目本身没有越界诱惑） | 必须构造出真正的越界诱惑：偷看 `progress` 之后会得到不同答案 |
| evidence 片段 | 与 `golden/` 共用会重复计分 | 与 `golden/` **零重叠**（含同章内的近似重复），逐片段机检 |

### difficulty 已废弃（2026-10-13）

消费方 Omniread 的决定：`difficulty` 是评测者的主观标签，而 `type` 几乎完全决定了它（`fact`→easy、`cross`→hard），不承载额外信息。此后**存量题保留原值、不迁移；新题不写；统计与报表一概不再读它**。

落地方式：`schema.json` 把 `difficulty` 移出 `required`（仍留在 `properties` 里带 enum，存量值才合法），校验器改成「写了才校验取值、不写不管」。本目录的 30 道按「新题」处理，全部不写该字段；`golden/` 的 86 道按「存量」处理，原值一个未动，`dataset_hash` 因此保持不变。

> 待办（项目侧）：`eval/golden/README.md` 还停在 2026-10-10，§2 的必填字段集仍写着 `difficulty`，与 10-13 的 `schema.json`、校验器已经对不上。本仓库的 `golden/README.md`、`golden-holdout/README.md` 是该文件的副本，因此同样带着这处不一致——规范以 `schema.json` + 校验器为准。

`golden/README.md` 的其余规则（字段集封闭、`level=past` 的 evidence 章号 ≤ `progress`、evidence 必须是原文片段、`spoiler` 桶必须 `expect_refusal=true`）**一条不改**，全部照旧。

## 校验口径

| 层 | 命令 | 管什么 |
| --- | --- | --- |
| 1 | `python golden-holdout/validate_golden.py golden-holdout/<文件>` | 单题结构、跨字段（章号 ≤ `progress`） |
| 2 | `python temp/holdout_check.py` | 文件名 = id、与 `golden/` 合并后 id 唯一、与 `golden/` 零片段重叠、桶分布、章节覆盖 |
| 3 | `python temp/verify_evidence.py golden-holdout` | 逐条 evidence 是否**逐字**命中 `index.jsonl`（补校验器自己声明判不了的那条） |
| 4 | `python temp/leak_scan.py` | 拒答题文书是否把答案写了出来（把题面文书切 n-gram 回进度之后的章节里找） |

第 2–4 层是 `temp/` 下的一次性脚本，不属于交付内容。

## 结果

```
dataset_hash: 5fb103e87a6594bdb24e7d3c8d885d19716e49de4188851f4bc0ab957204780f
```

| 项 | 值 |
| --- | --- |
| 冻结日期 | 2026-10-09 |
| 题目文件数 | 30 |
| 分桶 | cross 8 / alias 6 / boundary 6 / foreshadow 4 / fact 3 / spoiler 3 |
| 拒答题 | 3 |
| `level` | past 27 / full 3 |
| `difficulty` | 无此字段（30 道全不写） |
| evidence 叶子 | 137 条，全部 `OK-exact`（MISS 0，OK-ws 0） |
| 章节覆盖 | 41 章，其中 31 章是 `golden/` 从未用过的 |
| 与 `golden/` 的片段重叠 | 0 处 |

四层检查全过，仅目录级数量目标报 FAIL（见上，预期内）。

## 已知弱点

- **`spoiler-103` 与 `golden/spoiler-012` 同题材**：两者都以「乃乃亚的作票陷阱」为对象，`progress` 只差 1（174 对 173）。留出集在这条剧情弧线上没有提供独立信息，看这条弧的表现时应以 `golden/spoiler-012` 为准。其参考口径里还出现了「真正的幕后主使」这一只在第 174 章之后才有的表述——用来说「尚未被指认」，未给出身份，但仍是提示。
- **`boundary` 的越界诱惑强弱不一**：`boundary-103`（照片的含义在第 121 章才揭开）与 `boundary-105`（乃乃亚的动机在第 175 章才揭开）最强；`boundary-102`、`boundary-104`、`boundary-106` 弱一些——偷看后文会改变措辞，但不太会改变结论。
- **`alias-105` 是反向题**：题面写正式全名，正文只用简称（「统也／剑崎会长」），方向与其余 5 道相反。规范 §3 允许，但它测的归并方向与同桶其他题不同。
- **`cross-108` 只跨相邻两章**（57→58），多跳整合的强度低于同桶其他题。
- **难度维度已废弃，本集不再有难度分层**：原先按「真实难度」给值（hard 14 / medium 13 / easy 3）是本集相对 `golden/` 的一处改进，随 2026-10-13 的废弃决定一并作废，现在两道集都不可按难度分层统计。

## 未处理

- 留出集与 `golden/` 合并后仍有章节零 evidence。
- 留出集不重复 `golden/` 的 evidence 片段，但**题目主题可能与 `golden/` 有交叠**（同一段剧情换个问法，`spoiler-103` 即一例）。这是有意的：留出集要测的是「模型/检索在没调过的题上还灵不灵」，不是「问了全新剧情」。
