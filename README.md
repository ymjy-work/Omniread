# Omniread

小说 RAG 系统：把「小说语料 → 检索 → 回答 → 引用 → 评测」做成可复现的单轮基线，
由 Java 薄网关、Python RAG 服务、Vue 前端与 PostgreSQL + pgvector / MinIO 四部分组成。

> 当前处于 **M0（流程冒烟与效果简测）**：契约冻结，Java 网关与 Python RAG 全部端点、
> 数据层与迁移、语料导入与向量化、检索链、回答链、前端端到端链路均已可用，Golden 86 题已冻结，
> evidence→chunk 映射已全量跑通（357/357）。
> M0-8 judge 校准、M0-9 基准与 `baseline-m0` 未做；Ready Gate 八条全过，Golden 已冻结；
> 真实 provider 凭据未接入，见下文「当前进度」。

## 目录结构

```text
omniread/
  contracts/openapi/     # 唯一真相源：frontend-api-v1.yaml（外部 8 条）、rag-internal-v1.yaml（内部 8 条）
  docs/m0/               # M0-00 开发指导 ~ M0-05 技术选型（本地保留，不入库）
  web/                   # Vue 3 + Vite + TypeScript；构建产物 web/dist 由 Java 托管
  services/
    backend/             # Java 25 + Spring Boot 4.1 薄网关（Maven）
    rag/                 # Python 3.13 RAG 服务（uv 管理，src/omniread）
  infra/docker/          # PostgreSQL + pgvector、MinIO 的 compose 与初始化
  scripts/               # 一键启动 / 停止 / 验证脚本（本 README 的主角）
  eval/                  # Golden 86 题（已冻结）、评测产物与 fixture 目录
  temp/                  # 一次性脚本与运行时日志（本地保留，不入库）
  asset/                 # 语料（不入库）
```

## 端口与入口约定

四个产物共用一张端口表，任意一处改动都要同步其余位置。

| 服务 | 宿主地址 | 固定其来源 |
| --- | --- | --- |
| Python RAG | `127.0.0.1:8000` | `services/backend/.../application.yml` 的 `omniread.rag.base-url` 默认值 |
| Java 网关 | `127.0.0.1:8080` | `application.yml` 的 `server.port`；`web/vite.config.ts` 的 proxy target |
| 前端 dev server | `localhost:5173` | `web/vite.config.ts` 的 `server.port` |
| PostgreSQL | `localhost:55432` | `infra/docker/docker-compose.yml`；连接串 `postgresql://omniread@localhost:55432/omniread` |
| MinIO | S3 API `localhost:9100`、控制台 `localhost:9101` | compose；`services/rag/src/omniread/config.py` 的 `minio_endpoint` 默认值 |

两个宿主端口是为避让本机已有容器而错开的：PG 5432 → 55432，MinIO 9000/9001 → 9100/9101，
容器内部仍是镜像默认端口。Java 与前端同源（生产由 Java 托管 `web/dist`），因此没有 CORS 配置。

**入口一致性**：MinIO 桶名为 `omniread-sources`（M0-02 §4），三处取值一致——
`services/rag/src/omniread/config.py` 的 `minio_bucket` 默认值、`infra/docker` 的 `minio-init` 建桶、
`scripts/dev-up.sh` 启动 Python 时显式传入的 `OMNIREAD_MINIO_BUCKET`。
启动脚本里仍显式传，是为了把约定钉在脚本上、不依赖配置默认值。改桶名时要同时改这三处。

## 环境要求

| 组件 | 版本 |
| --- | --- |
| JDK / Maven | Java 25 / Maven 3.9.15（本地仓库重定向到 `D:/DevTools/maven-repo`） |
| Python / uv | Python 3.13.13 / uv（不在 PATH 时脚本自动用 WinGet 安装目录下的绝对路径） |
| Node / npm | Node 26 / npm 12 |
| 容器 | Docker Desktop + Compose v2 |
| 密钥 | keymgr（Windows Credential Manager 后端） |

## 一次性准备

```bash
# 1. Python 依赖（脚本会在 .venv 缺失时自动跑，手动跑也可以）
uv sync --all-groups --directory services/rag

# 2. 前端依赖（仅在需要 --web 或重建 web/dist 时）
npm --prefix web install

# 3. 密钥注入：配置 keymgr 的 omniread profile
#    scripts/keymgr-profile.example.json 里是要合并进
#    %USERPROFILE%\.config\keymgr\profiles.json 的 "omniread" 段。
#    其中 POSTGRES_PASSWORD 指向的条目要先建：keymgr set omniread-pg
```

**profile 是全有或全无**：只要其中任一 Key 不存在，`keymgr run omniread` 整个失败，
连其余几个能用的也一起用不了。所以缺哪个就先补哪个，不要先把映射写进去占位。
当前本机已配齐 GLM / DeepSeek / 百炼 / MinIO 四项，缺 `omniread-pg`；
`keymgr list` 是查准确名称（区分大小写）的唯一途径。验证用
`keymgr.cmd run omniread python temp/probe_keymgr_env.py`（只打印注入与否与长度，不打印明文）。

密钥只经 keymgr 注入进程环境，不写进源码、`.env`、compose 或日志（M0-00 §6）。
`infra/docker/docker-compose.yml` 里的两个口令是必填插值，未注入时 compose 直接报错，不会退化成空密码。

## 启动

在 Git Bash 里从仓库根执行：

```bash
bash scripts/dev-up.sh                  # infra + Python(8000) + Java(8080)
bash scripts/dev-up.sh --web            # 额外起前端 dev server(5173)
bash scripts/dev-up.sh --no-infra       # 复用已在跑的 infra
bash scripts/dev-up.sh --fake-providers # 联调：回答/检索改假 provider，不调 GLM/百炼
bash scripts/dev-up.sh --build          # 强制重建 Java jar
bash scripts/dev-up.sh --force          # 端口被占时先结束占用进程
bash scripts/dev-down.sh                # 停 Java + Python（+ 前端）
bash scripts/dev-down.sh --all -v       # 连 infra 与数据卷一起删
```

provider 开关默认钉死为真实适配器（`glm` / `ali`）：父 shell 里残留的联调 export
（`OMNIREAD_ANSWER_PROVIDER=fake` 等）不会带进本次启动；要联调就显式加 `--fake-providers`。

免凭据起 API 形状验证链路（不起 infra，Python 用 `temp/images` 作图片目录、不连 MinIO）：

```bash
bash scripts/dev-up.sh --no-infra --local-images
```

该模式不要求、也不经 keymgr 注入 `POSTGRES_PASSWORD`，因此 Python 目录读库不接线、拿不到数据：
`GET /api/v1/books` 返回空列表、章节接口返回 400。它的用途是「不起 infra、不连 MinIO 时验证 API 形状」，
不是数据可用链路；要看真实数据需注入 `POSTGRES_PASSWORD` 且让 infra 在跑。

启动脚本做三件事：等 `omniread-postgres` / `omniread-minio` healthy；后台起 Python 与 Java，
PID 与日志写进 `temp/run/`；轮询 `/internal/v1/health` 与 `/api/v1/health` 直到就绪。
Java jar 不存在时会自动 `mvn -DskipTests package`。

浏览器访问 `http://127.0.0.1:8080/`（生产形态，Java 托管 `web/dist`）；
用 `--web` 时走 `http://localhost:5173/`（HMR，`/api` 代理到 8080）。

## 验证

一条命令把四个产物的构建与检查串起来，默认还会跑检索链与回答链冒烟：

```bash
bash scripts/verify-all.sh                # 默认 9 步：compose / Python / Java 测试 / Java 打包 / web / 检索冒烟 / 回答冒烟 / 映射链 / 产物红线
bash scripts/verify-all.sh --smoke        # 追加第 6 步：起一次全栈，curl 端到端后自动停
bash scripts/verify-all.sh --skip-web     # 跳过 web 三步（没装 node 时）
bash scripts/verify-all.sh --data-layer   # 追加第 7 步：真连 PG / MinIO 验证数据层
bash scripts/verify-all.sh --gateway      # 追加第 10 步：起 Java + Python（假 provider）跑 M0-6 网关联调
```

M0-7b 的两条也可单独跑（都不需要凭据）。下文的 `python` 一律指
`services/rag/.venv/Scripts/python.exe`：

```bash
bash scripts/verify-mapping.sh            # 映射链：语料直读 + 假 provider 兜底，25 项断言
bash scripts/verify-artifacts.sh          # eval/ 产物红线：文件白名单 + 字段长度 + 与语料比对
python scripts/run_mapping.py             # 跑一次映射，产出 eval/runs/<run_id>/ 与 temp/ 复核件
python scripts/run_mapping.py --source db --write-db   # 读真库切片并写 chunk_mappings（需凭据）
python scripts/render_golden_review.py    # Golden 逐题复核件 → temp/（免凭据）
```

M0-9 检索层评测（**需要真实 embedding/rerank**，假 provider 的数字是噪声不可作基线）。
用 venv 的 python：`local-env.sh` 只注入环境变量、不激活 venv，裸 `python` 没有本项目依赖：

```bash
source temp/local-env.sh && keymgr run omniread \
  services/rag/.venv/Scripts/python.exe scripts/run_eval.py --write-db   # 顺带写 rag_runs
```

改口径（改了 `summary` / `failures` 的算法）后**不必重跑**——它们是
`retrieval.scores.jsonl` 的确定性函数，离线重算即可，零费用：

```bash
services/rag/.venv/Scripts/python.exe scripts/resummarize_eval.py \
  --run-id 2026-09-20-m0-baseline --dry-run    # 先看差异；去掉 --dry-run 才落盘
```

M0-9 生成层评测（**需要 `GLM_API_KEY`**；真跑 86 题 = 86 次 GLM + 172 次百炼）。
**用与检索层不同的 `run_id`**——它是 `rag_runs` 主键，同名会把检索层基线 upsert 掉：

```bash
source temp/local-env.sh && keymgr run omniread \
  services/rag/.venv/Scripts/python.exe scripts/run_generation_eval.py --write-db

# 只验链路结构（假回答模型 + 假检索，零费用；产物会写明不可作基线）
... --fake-providers --limit 3

# 断了接着跑：已答出来的题不重花调用；generation_failed 的题会重试
... --resume
```

产物分两处：`temp/generation/<run_id>/run.gen.jsonl` 放**模型看到与写出的全部文本**
（`temp/` 不进 git，全仓只有这一处能放），`eval/runs/<run_id>/generation.scores.jsonl`
只放指针与标量——`eval/` 进 git，那里的字段集由 `GenerationScoreRecord` 定死。

数据层（M0-2）单独跑：

```bash
bash scripts/verify-data-layer.sh         # 迁移 upgrade/downgrade 往返 + 对象读写 + 清理
bash scripts/verify-data-layer.sh --start-infra   # 顺手用 compose 起 infra
```

`verify-data-layer.sh` 要求 infra 已起、凭据已注入（`POSTGRES_PASSWORD`、`MINIO_SECRET_KEY`），
失败时会直接给出「先跑 `scripts/dev-up.sh`」这类可操作提示。

| 步骤 | 命令 | 失败时看哪里 |
| --- | --- | --- |
| 1 infra | `docker compose -f infra/docker/docker-compose.yml config --quiet` | compose 文件语法或必填插值问题；`infra/docker/README.md` 的排错一节 |
| 2 Python | `uv sync --all-groups` → `pytest` / `ruff check` / `mypy` | 依赖冲突看 uv 输出；用例名对应 `services/rag/tests/` |
| 3 Java 测试 | `mvn -f services/backend/pom.xml test` | `services/backend/target/surefire-reports/` |
| 4 Java 打包 | `mvn -f services/backend/pom.xml -DskipTests package` | 首个 `ERROR`；产物 `services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar` |
| 5 前端 | `npm --prefix web run typecheck` / `npm --prefix web run build` | `web/src` 按文件:行号；产物 `web/dist` |
| 6 smoke | `dev-up.sh --no-infra --local-images` + curl（只验 API 形状，无数据） | `temp/run/rag.log`、`temp/run/backend.log` |
| 7 数据层（`--data-layer`） | `verify-data-layer.sh`：`alembic upgrade/downgrade` 往返 + 对象读写 | 先 `dev-up.sh` 起 infra；PG 相关看容器日志，MinIO 相关看 `docker logs omniread-minio` |
| 8 检索冒烟 | `verify-retrieval.sh --source corpus`：语料直读 + 假 embedding，不连库 | 脚本输出的逐项断言 |
| 9 回答冒烟 | `verify-answering.sh`：假 provider 跑通事件流与 JSON / SSE 适配器 | 脚本输出；细节在 `scripts/verify_answering.py` |
| 10 网关联调（`--gateway`） | `verify-gateway.sh`：Client → Java → Python 端到端 | 需要 `POSTGRES_PASSWORD` 与已起的 PostgreSQL |
| 11 映射链 | `verify-mapping.sh`：确定性区间映射 + 假 provider 兜底 + 产物红线 | 脚本输出的逐项断言；语料需在 `asset/` 下 |
| 12 产物红线 | `verify-artifacts.sh`：`eval/runs/` 的文件白名单、字段长度、与语料比对 | `eval/` 进 git，夹带正文只能重写历史；报错行给出文件名与字符位置 |

手动 smoke（全栈起好后）：

```bash
curl -s http://127.0.0.1:8080/api/v1/health                 # 200 {"status":"ok","service":"omniread-backend"}
curl -s http://127.0.0.1:8080/api/v1/books                  # 200，books[] 含已导入的 1 本书
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/          # 200（前端首页）
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/v1/nope  # 404（未知接口不能回落成首页）
docker exec omniread-postgres psql -U omniread -d omniread -tAc \
  "SELECT extversion FROM pg_extension WHERE extname='vector';"          # 0.8.6
bash infra/docker/scripts/verify.sh                          # 容器 / 扩展 / 桶 一起查
```

## 当前进度

**已完成 M0-1 ~ M0-6、M0-7a、M0-7b**：

- **契约冻结**：`contracts/openapi/` 两份契约冻结；Java 的 DTO 由 `openapi-generator` 从内部契约生成 model。
- **Java 网关**：外部端点全部落位，Controller → QueryOrchestrator → RagGatewayClient 分层，
  request_id 生成与透传、realm 校验、错误码映射、图片与 SSE 的字节级透传、静态资源托管均可用。
- **Python RAG**：内部端点全部落位，事件流与 JSON / SSE 两个适配器、图片路径防护、MinIO / 本地双存储可用。
- **数据层**：表结构与 Alembic 迁移 0001~0003 可用；语料已导入 **1 本书 / 15 卷 / 193 章 / 1807 chunks**，
  且已全部嵌入；230 张插图归档到 MinIO。
- **检索链**：dense(top60) / BM25(top60) / RRF 融合 / rerank(top24) / 装配三 cap / realm 过滤可用。
- **回答链**：GLM 适配器 + 拒答判定 + JSON / SSE 双适配器可用。
- **评测**：Golden 86 题已冻结；evidence→chunk 映射 357/357 命中
  （335 唯一覆盖 / 19 跨块引入者 / 3 章内重复出现），run 产物在 `eval/runs/2026-09-20-m0-mapping/`。
- **前端**：书库 → 章节树 → 正文（含插图）→ 提问 → 流式回答 → 引用跳章 整条链路可跑通。

**未做**：

- `rag_runs.dataset_hash` 落库（Ready Gate 八条已全过、Golden 已冻结；落库需 `POSTGRES_PASSWORD`）；
- M0-8 judge 校准；
- M0-9 基准与 `baseline-m0`。

**真实 provider 凭据未接入**：keymgr 没有映射 `GLM_API_KEY` 的 profile，真实问答目前发不出去；
联调靠 `dev-up.sh --fake-providers`（回答/检索改用假 provider），不要靠 export 环境变量。

## 已知边界与集成注意

- **API 形状验证模式没有数据**：`dev-up.sh --no-infra --local-images` 不注入 `POSTGRES_PASSWORD`，
  此时目录读库不接线，`GET /books` 返回空列表、章节接口返回 400；它只验证 API 形状与传输结构，
  验证不了检索内容。要看真实数据需注入 `POSTGRES_PASSWORD` 且 infra 在跑。
- **阅读进度由 Java 侧单独持久化**：Python 按 M0-01 §1 不保存用户进度，内部契约（`rag-internal-v1.yaml`）
  没有 progress 端点；外部契约保留的 `GET/PUT /api/v1/books/{id}/progress` 由 Java 自己读写本地文件
  （路径可配，默认 `var/progress.json`，已被 `.gitignore` 覆盖），整条链路不经过 Python。
  M0 是单机单用户，一本书一条记录；默认未读值为第 1 章。
- **MinIO 镜像 tag 只在有缓存的本机可用**：`minio/minio:RELEASE.2025-04-22T22-12-26Z` 在 Docker Hub 已下线，
  换机器要改用 `quay.io/minio/minio` 的冻结 tag，compose 里两处都要改。
- **`verify-all.sh` 不验证镜像可拉取性**：第 1 步只跑 `compose config`（查文件语法与必填插值），
  smoke 又走 `--no-infra` 复用已起的容器，所以「换机器时 MinIO 镜像拉不到」这类问题不会被这条序列暴露；
  换机器首次起栈要靠 `dev-up.sh` 实际拉一次镜像。
- **契约等价测试只覆盖双方共有的 schema**：`services/rag/tests/test_contract_equivalence.py` 比对的是两侧
  都有的 11 个 schema，对单侧 schema（外部 `Progress`/`ProgressWrite`、内部 `RetrievalOnlyResponse`/`ScoredChunks`）
  只断言「是否单侧」，不比对字段形状——改动它们的字段名不会被这条测试拦住，改这些要手工核对。
- **`verify-all.sh` 的 Java 两步不用 `clean`**：热 `target/` 里的旧生成源可能掩盖契约漂移；
  改过 `contracts/openapi/` 后要单独跑一次 `mvn clean test`。
- **PostgreSQL 口令只在数据卷首次初始化时读**：先用临时口令起过就必须 `dev-down.sh --all -v` 重建数据卷。
- **前端为 history 路由**：Java 已对无扩展名的非 `/api` 路径回落 `index.html`，`/api/**` 的未知路径仍返回 404。
- **只写现状**：注释与文档只描述当前做法及其必要性，不记录实现的历史过程；
  确需留痕的决策放 `docs/` 的独立决策文件。
