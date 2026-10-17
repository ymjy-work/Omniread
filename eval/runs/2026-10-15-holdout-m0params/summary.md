# 评测 run 2026-10-15-holdout-m0params

- 阶段：retrieval；kind：retrieval
- dataset_hash：`5fb103e87a6594bdb24e7d3c8d885d19716e49de4188851f4bc0ab957204780f`（schema m0.1.0）
- corpus_manifest_hash：`6f47ad1fc83e274fb47358a7ad728517786fbe2370ef1659a18316f4abf3048e`
- 切片：`m0-placeholder-v1`；chunk 来源：db
- embedding：dashscope / `qwen3.7-text-embedding`（1024 维）
- rerank：dashscope / `qwen3.7-text-rerank`
- 题目数：30

> **可信度**：本次题集不满交付数量目标（--allow-incomplete）：dataset_hash 与 Golden 不同，数字不可与 Golden 基线并列，只用于留出验证。

## 指标

- `evidence_recall`：0.7591
- `evidence_total`：137
- `evidence_mapped`：1.0000
- `leak`：0

（`evidence_recall` 分母 = 137 条证据。它是**逐条证据**的召回率，分母是该题全部 evidence（含没映射上的）——分母随映射结果塌缩会让指标虚高。`evidence_mapped` 单列，它衡量的是**映射**而不是检索：切片没对上与检索没召回到，修法不同。`leak` 是硬门禁，任一阶段 >0 即红。**分母为 0 的记 `—`**：那是「没有可判定的证据」，不是「一条都没中」。）

## 按题型分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `alias` | 6 | 15 | 0.7333 | 0 |
| `boundary` | 6 | 25 | 0.8000 | 0 |
| `cross` | 8 | 49 | 0.8367 | 0 |
| `fact` | 3 | 10 | 0.8000 | 0 |
| `foreshadow` | 4 | 29 | 0.7931 | 0 |
| `spoiler` | 3 | 9 | 0.1111 | 0 |

## 按realm 等级分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `full` | 3 | 19 | 0.8421 | 0 |
| `past` | 27 | 118 | 0.7458 | 0 |
