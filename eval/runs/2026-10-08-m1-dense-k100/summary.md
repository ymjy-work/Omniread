# 评测 run 2026-10-08-m1-dense-k100

- 阶段：retrieval；kind：retrieval
- dataset_hash：`601623c7f526d2f7bd02e7f41d15f8ca4246dabf04ae3268747aeafc0c6d5b00`（schema m0.1.0）
- corpus_manifest_hash：`6f47ad1fc83e274fb47358a7ad728517786fbe2370ef1659a18316f4abf3048e`
- 切片：`m0-placeholder-v1`；chunk 来源：db
- embedding：dashscope / `qwen3.7-text-embedding`（1024 维）
- rerank：dashscope / `qwen3.7-text-rerank`
- 题目数：86

## 指标

- `evidence_recall`：0.6891
- `evidence_total`：357
- `evidence_mapped`：1.0000
- `leak`：0

（`evidence_recall` 分母 = 357 条证据。它是**逐条证据**的召回率，分母是该题全部 evidence（含没映射上的）——分母随映射结果塌缩会让指标虚高。`evidence_mapped` 单列，它衡量的是**映射**而不是检索：切片没对上与检索没召回到，修法不同。`leak` 是硬门禁，任一阶段 >0 即红。**分母为 0 的记 `—`**：那是「没有可判定的证据」，不是「一条都没中」。）

## 按难度分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `easy` | 16 | 51 | 0.7843 | 0 |
| `hard` | 27 | 154 | 0.6494 | 0 |
| `medium` | 43 | 152 | 0.6974 | 0 |

## 按题型分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `alias` | 15 | 52 | 0.6538 | 0 |
| `boundary` | 13 | 47 | 0.6383 | 0 |
| `cross` | 15 | 96 | 0.5312 | 0 |
| `fact` | 16 | 48 | 0.8750 | 0 |
| `foreshadow` | 13 | 77 | 0.8701 | 0 |
| `spoiler` | 14 | 37 | 0.5946 | 0 |

## 按realm 等级分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `full` | 3 | 23 | 0.4348 | 0 |
| `past` | 83 | 334 | 0.7066 | 0 |
