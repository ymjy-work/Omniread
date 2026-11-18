# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 本目录现状

三端已实现并跑通联调：`web/`（Vue 3）、`gateway/`（Spring Boot + SQLite）、`rag/`（FastAPI + LangChain）。
架构与契约见 `.agent/docs/Omniread架构.md`，语料资产库在 `《不时轻声地以俄语遮羞的邻座艾莉同学》/`。
本目录是 git 仓库，按阶段提交。

联调状态：193 章已导入并索引（2703 chunks）；`past` 越界问题拒答、`full` 正常回答并带按章去重引用；
fact-001 回答「化学参考书」且引用第 2 章。gateway 20 项测试、rag 25 项测试通过，web build 通过。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `web/` | Vue 3 + TypeScript 前端 |
| `gateway/` | Spring Boot 4.1.2 + MyBatis + SQLite 薄网关 |
| `rag/` | Python 3.13 + FastAPI + LangChain 检索服务 |
| `.agent/docs/` | 项目文档：架构说明、阶段计划、迁移记录、决策 |
| `.agent/plan/` | 计划书与任务清单（有成文计划才放） |
| `.agent/temp/` | 一次性脚本、探针、临时产物；每个文件登记到 `tracking.md` |
| `opus/` | 交给人工的交付物：需求/spec、验收标准、评审记录 |
| `《不时轻声地以俄语遮羞的邻座艾莉同学》/` | 语料资产库，自带 `CLAUDE.md` |

`.agent/` 只放工作产物、不进版本库；工具配置仍在 `.claude/`。

## 常用命令

```bash
# web
cd web && npm install && npm run dev        # 5173
npm run build

# gateway
cd gateway && ./mvnw spring-boot:run        # 8080
./mvnw -DskipTests compile

# rag
cd rag && uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run pytest -q
```

## 目标架构（`.agent/docs/Omniread架构.md`）

```
web (Vue 3) ──HTTP/JSON──▶ gateway (Java) ──HTTP──▶ rag (Python)
                                 │                     │
                            gateway.db              rag.db
                            (SQLite)                (SQLite)
```

- **gateway 是薄网关**：鉴权/限流、书/章/进度/会话 CRUD、事务、统一 `Result`、转发 rag；不做切片、向量、检索、prompt。
- **rag 承担全部 AI 判断**：切片、向量、索引、边界过滤、检索、prompt、引用校验、拒答；不管登录、不碰用户表。
- 模型全部走阿里云百炼：chat `qwen3.7-plus`、embedding `qwen3.7-text-embedding`（1024 维，归一化）、
  rerank `qwen3-rerank`（候选 30 → 取 8）；key 只在 rag，gateway 不接触模型。
- 数据归属：`user` / `book` / `chapter` / `reading_progress` / `chat_session` / `chat_message` / `login_attempt`
  在 `gateway.db`；`chunk` 在 `rag.db`。两个独立 SQLite 文件、各自单写者：gateway 不读 `rag.db`，
  rag 不连 `gateway.db`；rag 不存章节正文，正文只在索引请求中传入。
  `chunk` 的向量以 BLOB（float32）存放，余弦在 rag 进程内计算，不依赖向量索引；
  `chunk` 行保留 `chapter_id` / `chapter_index` / `title`。
  阅读器只从 `gateway.db` 的 `chapter` 取完整正文，`chunk` 不对外；citations 只带 `chapter_id`，
  前端凭它向 gateway 取整章。
- 层间契约只有三个：`POST /v1/index {book_id, chapters[]} → {indexed_chunks}`（`chapters` 是整本章节内容，
  整体替换该书 chunk）、`POST /v1/ask {book_id, question, level, progress, history[], top_k} → {answer, citations[]}`、
  `GET /v1/health → {status}`。
- 两条链路：索引 = gateway 校验登录 → 从 `gateway.db` 读 chapter → rag 切片/向量 → 替换 `rag.db` 的 chunk；
  问答 = gateway 取 progress、落用户消息 → rag 按章节区间过滤 → 余弦 top-k → prompt → LLM → 引用校验/拒答 →
  gateway 落 assistant 消息。
- 索引触发：章节新增、导入、编辑或删除后由 gateway 自动调用 `/v1/index`，不设前端手动触发入口；
  批量导入或连续变更合并为一次调用，不做按章增量。调用在后台线程执行，不阻塞章节保存。
- 多轮对话：gateway 在 `/v1/ask` 里带最近 6 条消息；rag 用 `trim_messages` 裁剪，有历史时先把问题改写为
  独立查询再检索；rag 不做历史持久化，不引入 Agent / checkpointer。
- 分层规则：web 的 `main.ts` 只挂载，`api/` 只发请求，状态进 `stores/`；gateway 一个模块一个限界上下文，
  Controller 只校验参数、Service 管事务、Mapper 只写 SQL，`model/` 按 `Entity` / `DTO` / `VO` 后缀区分，
  `RagClient` 是唯一出站口；rag 的 `api/` 只做参数与错误映射，流程在 `rag/pipeline.py`，
  `rag/realm.py`（past/full → 章节区间）与 `rag/citations.py`（引用校验）是本项目业务核心。

## 语料资产库

`《不时轻声地以俄语遮羞的邻座艾莉同学》/` 自带 `CLAUDE.md`，**处理语料与出题前先读它**；来源、授权与版式见 `说明.md`。

- 规模：193 章 / 15 卷 / 230 张插图 / 约 141.5 万字。`chapters/` 下 207 个 `.md` 是因为含卷头插图等非正文章节文件，正文仍以 `index.jsonl` 的 193 行为准。
- **章节号唯一权威**：`index.jsonl` 第 N 行（从 1 数）= `chapter_index = N`；`book_id` 恒为 1，
  `chapter_id = book:1:chapter:N`。卷号与章节范围对照见 `golden/README.md` §8。
- `chapters/<卷>/NNN_标题.md` 的插图是相对章节文件的路径，`index.jsonl` 里的 `images` 是仓库根相对路径，两者写法不同。
- `scripts/` 里只有 `validate_golden.py` 在本目录可用；`dev-up.sh` / `dev-down.sh` / `verify-*.sh`
  依赖本目录没有的服务布局，**不要照着跑**。

### Golden 数据集

- `golden/`：86 题，六桶 fact 16 / alias 15 / cross 15 / foreshadow 13 / boundary 13 / spoiler 14，拒答 14。
- `golden-holdout/`：30 题独立留出集，编号从 101 起，用于调参后的复核。
- 规范入口是 `golden/README.md`，但 **`schema.json` + `validate_golden.py` 权威**：`difficulty` 已于 2026-10-13 废弃，
  存量题保留原值，新题不写该键（README §2 仍列着它是旧文）。
- 校验器只用标准库，必须**显式传路径**；无参会默认找 `../eval/golden` 并 exit 2。在项目根执行（实测通过）：

  ```bash
  # 整个 golden 数据集（末行输出 dataset_hash）
  PYTHONIOENCODING=utf-8 python "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden/validate_golden.py" "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden"

  # 单题
  PYTHONIOENCODING=utf-8 python "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden/validate_golden.py" "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden/fact-001.json"

  # 留出集只能逐题校验（目录级数量目标 FAIL 是预期）
  PYTHONIOENCODING=utf-8 python "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden-holdout/validate_golden.py" "《不时轻声地以俄语遮羞的邻座艾莉同学》/golden-holdout/fact-101.json"
  ```

  退出码 `0` 通过 / `1` 有校验问题 / `2` 用法或路径错误。
- 冻结口径：改一个字节即新版本，按 `dataset_hash` 区分。当前值记录在语料目录的 `docs/dataset-freeze.md`
  （golden）与 `docs/holdout.md`（holdout）。
- **留出集红线**：`golden-holdout/` 不得并入 `golden/`，也不得写回项目侧 `eval/`，否则会被卷进调参循环；
  目录级数量目标对补充集无意义。
- 校验器自认判不了「evidence 是否为逐字原文」；语料目录 `temp/` 下的一次性脚本补这一层：
  `verify_evidence.py`（逐字命中 `index.jsonl`）、`dup_scan.py`、`holdout_check.py`（与 golden 的 id/片段冲突、桶分布）、
  `leak_scan.py`（拒答题文书是否泄漏答案）。它们不是产品代码，也不是测试套件。

## 协作分工

- 脚手架：本会话只建目录、契约、配置模板与占位文件，不写业务实现。
- `gateway/`：Claude Code + DeepSeek。
- `rag/`：Codex + DeepSeek 写代码；系统提示与引用/拒答提示词由 Qwen4Max 子代理撰写。
- `web/`：Codex + Qwen4Max。
- Codex 会话复用：同一大阶段内用 `codex resume --last` 或指定 session 继续，不要每个任务新开会话；
  一个大阶段结束后再换会话。

## 红线

- 语料可以按需入库；唯一限制是整本小说原文不要以明文形式（`.md` / `.txt` / `index.jsonl` 等）进入版本库。
  数据库文件与 `golden/` 题目不受此限。
- 密钥/Token 只写本机 `.env`（仓库建立后须 gitignore），模板留空值；覆盖含凭证文件前先 Read 并请示。
- 是否 `git init` / 提交 / 推送由用户决定，不擅自执行。
- 代码注释与项目文档只写现状，不写「原本是 A → 后来改成 B」；需要留痕的决策单独放决策文件。

## 环境与坑

- Windows + Git Bash，Python 3.13.13。跑会输出中文的 Python 一律加 `PYTHONIOENCODING=utf-8`，否则 Windows 控制台 GBK 会崩。
- 含中文的路径在 shell 里偶发 `cd` 失败；优先从当前目录用相对路径 + 引号调用。
- Spring Boot 父版本写 `4.1.2`，不要带 `.RELEASE`（Maven Central 只有 `4.1.2`）；MyBatis starter 用 `4.1.0`。
- `web/` 用 TypeScript 6.0.3 + vue-tsc 3.3.14，`npm run build` 已通过，不要按旧经验降回 5.x。
- 百炼 `qwen3.7-text-embedding` 单请求最多 20 条；`OpenAIEmbeddings` 必须设
  `check_embedding_ctx_length=False`，否则会发 token 数组被兼容端点拒绝。
- `qwen3.7-plus` 默认思考模式会把 completion tokens 吃光、`content` 为空；`ChatOpenAI` 必须加
  `extra_body={"enable_thinking": False}`。
- gateway 的 `HttpClient` 固定 `HTTP_1_1`，不要用默认 HTTP/2 打 uvicorn（h2c upgrade 会 400）。
- 语料目录的 `docs/` 是人机交付物，`temp/` 是一次性脚本与探针，两者都不属于产品代码，勿清理。
