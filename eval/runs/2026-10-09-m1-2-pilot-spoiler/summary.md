# 评测 run 2026-10-09-m1-2-pilot-spoiler

- 阶段：retrieval+generation；kind：full
- dataset_hash：`601623c7f526d2f7bd02e7f41d15f8ca4246dabf04ae3268747aeafc0c6d5b00`（schema m0.1.0）
- corpus_manifest_hash：`6f47ad1fc83e274fb47358a7ad728517786fbe2370ef1659a18316f4abf3048e`
- 切片：`m0-placeholder-v1`；chunk 来源：db
- embedding：dashscope / `qwen3.7-text-embedding`（1024 维）
- rerank：dashscope / `qwen3.7-text-rerank`
- 回答：glm / `glm-5.3-flash`（prompt `43c1f7631550`）
- 题目数：14

## 指标

- `evidence_recall`：0.7297
- `evidence_total`：37
- `evidence_mapped`：1.0000
- `leak`：0

（`evidence_recall` 分母 = 37 条证据。它是**逐条证据**的召回率，分母是该题全部 evidence（含没映射上的）——分母随映射结果塌缩会让指标虚高。`evidence_mapped` 单列，它衡量的是**映射**而不是检索：切片没对上与检索没召回到，修法不同。`leak` 是硬门禁，任一阶段 >0 即红。**分母为 0 的记 `—`**：那是「没有可判定的证据」，不是「一条都没中」。）

## 答案层

- `answered`：2 / 14（`generation_failed` 0）
- `citation_in_set`：1.0000（分母 2 = 真答出来的题）
- `answered_without_citation`：0
- `citation_out_of_range_total`：0；`citation_malformed_total`：0
- `refusal_correct`：0.8571（分母 14 道该拒答的题）
- `refusal_false_positive`：0

（`citation_in_set` 的分母**不含**拒答与生成失败的题：它们没有引用可判，算通过会虚高、算失败又不对——所以分母单列，缩水多少一眼可见。`answered_without_citation` 必须与 `citation_in_set` 并读：集合判定对空集天然安全，一个从不标注引用的回答会带着 `1.0000` 通过。`refusal_false_positive` 同理，它挡住「见谁都拒答」这个能拿满 `refusal_correct` 的退化解。）

## 答案层 · 按难度分列

| 分组 | 题数 | answered | citation_in_set | 生成失败 |
| --- | --- | --- | --- | --- |
| `hard` | 4 | 0 | — | 0 |
| `medium` | 10 | 2 | 1.0000 | 0 |

## 答案层 · 按题型分列

| 分组 | 题数 | answered | citation_in_set | 生成失败 |
| --- | --- | --- | --- | --- |
| `spoiler` | 14 | 2 | 1.0000 | 0 |

## 按难度分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `hard` | 4 | 11 | 0.8182 | 0 |
| `medium` | 10 | 26 | 0.6923 | 0 |

## 按题型分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `spoiler` | 14 | 37 | 0.7297 | 0 |

## 按realm 等级分列

| 分组 | 题数 | 证据总数 | evidence_recall | leak |
| --- | --- | --- | --- | --- |
| `past` | 14 | 37 | 0.7297 | 0 |
