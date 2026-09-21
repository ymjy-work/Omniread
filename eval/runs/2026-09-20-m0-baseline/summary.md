# 评测 run 2026-09-20-m0-baseline

- 阶段：retrieval；kind：retrieval
- dataset_hash：`601623c7f526d2f7bd02e7f41d15f8ca4246dabf04ae3268747aeafc0c6d5b00`（schema m0.1.0）
- corpus_manifest_hash：`6f47ad1fc83e274fb47358a7ad728517786fbe2370ef1659a18316f4abf3048e`
- 切片：`m0-placeholder-v1`；chunk 来源：db
- embedding：dashscope / `qwen3.7-text-embedding`（1024 维）
- rerank：dashscope / `qwen3.7-text-rerank`
- 题目数：86

## 指标

- `must_cite_recall`：0.6250
- `evidence_recall`：0.7003
- `group_recall`：0.7854
- `all_evidence_recall`：0.4186
- `chapter_recall`：0.8837
- `evidence_mapped`：1.0000
- `leak`：0

（`must_cite_recall` 分母 = 72。拒答题不进这个分母——它衡量的是「答案该引的都引了」，而拒答题本就不该引用；拒答题的检索质量由 `evidence_recall` 与失败清单承载，**没能召回到判定所需的证据仍算失败**。分列表同口径，**分母为 0 的记 `—`**：那是「没有可判定的题」，不是「一道都没中」。）

## 按难度分列

| 分组 | 题数 | must_cite 分母 | must_cite_recall | evidence_recall | leak |
| --- | --- | --- | --- | --- | --- |
| `easy` | 16 | 16 | 0.8125 | 0.7843 | 0 |
| `hard` | 27 | 23 | 0.5652 | 0.6558 | 0 |
| `medium` | 43 | 33 | 0.5758 | 0.7171 | 0 |

## 按题型分列

| 分组 | 题数 | must_cite 分母 | must_cite_recall | evidence_recall | leak |
| --- | --- | --- | --- | --- | --- |
| `alias` | 15 | 15 | 0.4000 | 0.7115 | 0 |
| `boundary` | 13 | 13 | 0.6154 | 0.6383 | 0 |
| `cross` | 15 | 15 | 0.5333 | 0.5417 | 0 |
| `fact` | 16 | 16 | 0.8125 | 0.8750 | 0 |
| `foreshadow` | 13 | 13 | 0.7692 | 0.8701 | 0 |
| `spoiler` | 14 | 0 | — | 0.5946 | 0 |

## 按realm 等级分列

| 分组 | 题数 | must_cite 分母 | must_cite_recall | evidence_recall | leak |
| --- | --- | --- | --- | --- | --- |
| `full` | 3 | 3 | 0.6667 | 0.4348 | 0 |
| `past` | 83 | 69 | 0.6232 | 0.7186 | 0 |
