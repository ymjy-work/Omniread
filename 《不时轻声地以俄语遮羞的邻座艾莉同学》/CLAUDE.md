# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这是什么

《不时轻声地以俄语遮羞的邻座艾莉同学》的**语料资产库**，没有构建系统、没有测试框架、没有产品代码。工作只有两类：

1. **语料使用 / 维护**——从 `chapters/`、`index.jsonl`、`全文.txt`、`epub/`、`images/` 里取内容。背景与版式约定见 `说明.md`。
2. **出评测题**——按 `golden/README.md` 的 M0 Golden 规范产出剧情问答题，题目就产在 `golden/` 里（它本身就是数据集目录）。

## 语料的权威事实

- 规模：193 章正文 / 15 卷分组 / 230 张插图 / 约 141.5 万字。
- `index.jsonl`：193 行，一行一章，**第 N 行（从 1 数）就是 `chapter_index = N`**。它是章节号的唯一权威来源。字段 `{id, vol, title, url, images, text}`；`text` 是纯正文（段落以 `\n\n` 分隔），`images` 是**仓库根相对**路径。
- `chapter_id` 格式恒为 `book:1:chapter:N`（`book_id` 永远为 1）。
- `chapters/<卷>/NNN_标题.md`：第 1 行是 `# 标题`，空行分段，插图写作 `![插图NNN](../../images/<卷目录>/NNN.jpg)`——**相对章节文件的路径**，与 jsonl 里的写法不同。
- `全文.txt` 是合并全文，插图位置以 `[插图 NNN]` 占位。
- 卷序号 ↔ 章节范围对照表在 `golden/README.md` §8，不在此重复。
- 重新抓取 / 整理 / 打包 EPUB 的脚本不在本目录（`说明.md` 提到的 `.work/` 不存在）；`temp/` 是放这类一次性脚本的地方。
- `scripts/` 里只有 `validate_golden.py` 在本仓库可用（`golden/` 内有同内容副本）。同目录的 `dev-up.sh` / `dev-down.sh` / `verify-all.sh` / `verify-data-layer.sh` / `keymgr-profile.example.json` 属于 Omniread 仓库，依赖本目录没有的 Java / Python 服务 / PostgreSQL / MinIO 布局，**不要照着跑**。

## 出题工作（`golden/`）

**`golden/` 本身就是数据集目录**，不是规范副本。规范唯一入口是 `golden/README.md`，自解释，直接照着做；题目文件直接产在这里，不要再套子目录、不要另建数据集目录。四件套已齐：`README.md` / `schema.json` / `example.json` / `validate_golden.py`。

```bash
# 只校验一道题
python golden/validate_golden.py golden/fact-001.json
# 提交前：校验整个数据集（文件名约定、id 唯一、数量目标）
python golden/validate_golden.py golden
```

退出码 `0` 通过 / `1` 有校验问题 / `2` 用法或路径错误。当前环境 Python 3.13。

**必须显式传路径。** 不给参数时校验器默认找「校验器所在目录的上一级的 `eval/golden`」（`validate_golden.py` 的 `main()`），那是写死给 Omniread 布局的；在本仓库跑无参会直接 `[ERROR] 路径不存在` 并 exit 2。**别把 `golden/` 改名成 `eval/golden/` 来迎合它**——无参不是本仓库的用法。

**只做 JSON Schema 校验是不够的。** 以下规则 `schema.json` 表达不了，只有校验器权威执行：`level=past` 时每条 evidence 的 `chapter_index ≤ progress`、`book_id`/`progress` 必须是整数、`id` 在数据集内唯一、数量目标（总量 ≥60、六桶每桶 ≥8、`expect_refusal=true` ≥10）。

出题时容易踩的几条：

- 字段集是封闭的（`additionalProperties: false`）——多写一个键就失败，`must_not_claim` / `notes` / `source_seqs` 都不存在。
- `difficulty` 已废弃（2026-10-13，消费方决定）：**新题不写这个键**；`golden/` 存量 86 道保留原值不迁移。`schema.json` 里它已不在 `required`，校验器只在「写了」时校验取值。`golden/README.md` §2 的必填字段集仍列着它，那是尚未跟上的旧文，以 `schema.json` + 校验器为准。
- `level=past` 必填 `progress`（1..193）；`level=full` 时 `progress` 必须**整个键缺省**，不能写 `null`。
- `must_cite_groups` 外层 AND、组内 OR；evidence 叶子只有 `chapter_id` + `content`，没有 `chunk_id`。
- `content` 必须是**从语料复制的原文片段**，不是转述——校验器判断不了，只能人工保证；转述会让运行时到切片的映射失准。
- `spoiler` 桶的 `expect_refusal` 必须为 `true`（校验器强制）。
- 拒答题要在 `progress` 域内**确实没有答案**，仍须写非空的 `must_cite_groups`。

## 红线

- **整本语料不得进入数据集目录**：`index.jsonl`、章节导出、`全文.txt`、`epub/`、`images/` 一律不拷贝。只有 evidence 的短片段随题目保存。
- 题目目录会被复制、提交、分发，整本原文一旦进去就收不回来。
- 交付后冻结：改动任何一个字节即视为新版本，靠校验器打印的 `dataset_hash` 区分，不要把改过的题和未改的题混作同一版。

## 工作约定

- `docs/` 是**人机交互文件夹**（需求 / spec、设计决策、验收标准、评审记录）；`temp/` 是**脚本与临时测试文件夹**（一次性脚本、临时验证）。两者都不属于产品代码，勿清理。
- 用 `temp/` 而非 `test/`：正式单测目录的通行命名是 `tests/`，并排极易看错，且 pytest 会递归收集 `test*` 目录。
- 决策记录**默认不创建**；确需留痕时在 `docs/` 下单开一个决策文件，不要混进需求 / 验收 / 评审文件，也不要写进代码注释或本文件。
