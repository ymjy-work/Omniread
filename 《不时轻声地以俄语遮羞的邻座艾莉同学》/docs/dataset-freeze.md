# 数据集冻结记录

按 `golden/README.md` §10：校验通过后记录 `dataset_hash` 并冻结；此后改动任何一个字节都视为新版本。

## 当前版本

```
dataset_hash: 601623c7f526d2f7bd02e7f41d15f8ca4246dabf04ae3268747aeafc0c6d5b00
```

| 项 | 值 |
| --- | --- |
| 冻结日期 | 2026-10-08 |
| schema_version | `m0.1.0` |
| 题目文件数 | 86 |
| 分桶 | fact 16 / alias 15 / cross 15 / foreshadow 13 / boundary 13 / spoiler 14 |
| 拒答题 | 14 |
| evidence 叶子 | 357 条，全部逐字命中 `index.jsonl`（MISS 0） |

复算方式：`python golden/validate_golden.py golden`，输出末行即该值。

## 版本沿革

| dataset_hash | 日期 | 差异 |
| --- | --- | --- |
| `d3bc72e3…b24c5d` | 2026-09-19 | 初版冻结。 |
| `601623c7…c6d5b00` | 2026-10-08 | 消费方 Omniread 在 `eval/golden/` 侧改了 4 道题的标注，本次按「项目侧为准」同步回本仓库：`alias-001` 由 `level=full` 改为 `level=past` 并加 `progress: 3`，`alias-001` / `fact-002` / `fact-006` / `boundary-010` 的 `difficulty` 由 `medium` 改为 `easy`。题面、答案、evidence 一字未动。 |

本仓库的 `golden/` 与 `D:\DevProjects\webApp\Omniread\eval\golden\` 现在语义一致（仅有换行符差异：本仓库 CRLF，项目侧 LF；`dataset_hash` 只吃规范化后的 JSON，与换行符无关，两边算出同一个值）。

## 校验口径

本版本通过三层检查：

1. `python golden/validate_golden.py golden` —— 结构、跨字段（`level=past` 时 evidence 章号 ≤ `progress`）、文件名约定、id 唯一、数量目标，并算出 `dataset_hash`。
2. `python temp/verify_evidence.py golden` —— 逐字验真：把每条 `content` 拿回 `index.jsonl` 对应章做子串匹配。**校验器自己声明「是否为原文片段无法机器判定」，这一层补的正是这个空白。**
3. `python temp/dup_scan.py` —— 重复计分点、编号连续性、boundary 桶的 `progress` 是否压住证据所在章。

后两者是 `temp/` 下的一次性辅助脚本，不属于交付内容。

## 编号口径

`<type>-<三位数字>`，**每个桶各自从 001 起连续**，编号与卷号无关。查某题取材于哪一章，看它的 `must_cite_groups[].chapter_id`，不要从编号推测。

## 未处理的已知问题

以下问题在出题过程中被识别但**本版本未处理**，冻结不等于已解决：

- **覆盖率**：本目录 86 题共引用 98 章，其余 95 章零 evidence（复算：`python temp/holdout_check.py`）。整块未覆盖的包括 ch34/45（政近身世，只在辅助文件 `example.json` 里出现）、ch120（母子对峙）、ch130（周防严清外传）、ch71-73（校庆对决结局）、ch164-175（第十卷主线）、ch182（BD特典真相）、ch8（艾莉莎当会长的动机）。
- **`boundary` 桶退化**：13 道题的 `progress` 都恰好等于证据所在章，形态与 `fact` 无异，没有一道真正测试「边界外的内容是否被挡住」。
- **拒答形态单一**：14 道拒答题全部是 `spoiler` 桶。README §6 允许的其他桶拒答题一道都没有。
- **`difficulty` 由桶决定**：alias/boundary 全 medium、fact 全 easy、cross 几乎全 hard，桶内无区分度，且存在倒挂（跨 106 章的题标 medium，跨 2 章的标 hard）。**该维度已于 2026-10-13 废弃**（消费方决定，理由即此条）：存量 86 道的原值保留不迁移，新题不再写，统计与报表不再读它。所以本目录的 difficulty 分布是历史遗留，不是可用的分层依据。
- **evidence 粒度不均**：长度 5–206 字并存，README §4 要求「数十字到数百字」。
