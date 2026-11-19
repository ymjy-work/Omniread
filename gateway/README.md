# gateway

Spring Boot 4.1.2 + MyBatis + SQLite 的薄网关：鉴权、限流、书/章/进度/会话 CRUD、
统一 `Result`、转发 rag。不做切片、向量、检索与 prompt。

## 启动

```bash
# 首次：复制模板并填写 admin、jwt secret（至少 32 字节）、crypto key（base64 的 32 字节）
# 三者缺失均启动失败
cp src/main/resources/application-local.yml.example src/main/resources/application-local.yml

./mvnw spring-boot:run
```

- 端口：`127.0.0.1:8080`
- 数据库：`var/gateway.db`，可用 `OMNIREAD_GATEWAY_DB` 覆盖；表结构见 `src/main/resources/schema.sql`
- 不开放注册；启动时按 `omniread.admin.username/password` 创建管理员（BCrypt）
- CORS 允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`
- Boot 父版本写 `4.1.2`，不要带 `.RELEASE`（Maven Central 只有 `4.1.2`）；MyBatis starter 固定 `4.1.0`

## 语料导入（seed）

```bash
# 默认读 ../《不时轻声地以俄语遮羞的邻座艾莉同学》/index.jsonl，可用 OMNIREAD_SEED_JSONL 覆盖
./mvnw spring-boot:run -Dspring-boot.run.arguments=--omniread.seed.enabled=true
```

幂等：book=1 与 193 章已存在时跳过；第 N 行 `chapter_index=N`，`chapter_id=book:1:chapter:N`。
导入完成后后台触发一次 `/v1/index`。也可用 `--omniread.seed.jsonl=<路径>` 直接指定文件。

## 端点（统一 `Result{code,message,data}`，成功 code=0）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | `{username,password}` → `{token,user}`，失败限流 |
| GET | `/api/books` | 书籍列表 |
| POST | `/api/books` | 新建书籍 |
| GET | `/api/books/{id}` | 书籍详情（含章节数） |
| GET | `/api/books/{id}/chapters` | 章节目录（不带正文） |
| GET | `/api/books/{id}/chapters/{chapterIndex}` | 单章完整正文 |
| POST/PUT/DELETE | `/api/books/{id}/chapters[/{chapterIndex}]` | 章节写操作，后台触发重建索引 |
| GET/PUT | `/api/books/{id}/progress` | `{chapterIndex,scrollRatio}`，scrollRatio 0..1 |
| POST | `/api/chat/sessions` | `{bookId,title?}` |
| GET | `/api/chat/sessions?bookId=` | 会话列表 |
| GET | `/api/chat/sessions/{id}/messages` | 消息记录（assistant 带 citations） |
| POST | `/api/chat/sessions/{id}/ask` | `{question,level,mode,provider?,model?}`，level=past/full 缺省 past，mode=auto/platform/byok 缺省 auto |
| GET | `/api/plans` | 套餐目录：free(0/100)、plus(20/500)、pro(60/2000)、ultra(100/4000)，周期 30 天 |
| GET | `/api/me/account` | `{role,plan,credits,balance,planExpiresAt}`，顺带做到期续期/回落 |
| POST | `/api/me/plan` | `{plan}` 余额购买付费档，扣余额、重置积分、开新周期 |
| GET/POST/DELETE | `/api/me/api-keys` | BYOK Key（bailian/openai/deepseek/siliconflow），AES-GCM 加密存储，只返回掩码；DELETE 带 `?provider=` |
| GET | `/api/models?mode=platform\|byok&provider=` | platform 按当前套餐过滤目录模型（free 为空）；byok 返回固定提供商与建议模型 |
| POST/GET | `/api/admin/users` | 管理员建号（free/100 积分/20 余额）/ 列表，需 role=admin |
| POST | `/api/admin/users/{id}/balance` | `{amount,reason?}` 发放余额并写流水 |

除登录外均需 `Authorization: Bearer <token>`（JWT 含 role 声明）。

## 计费口径

- ask：auto 全档位可用扣 1 积分；platform free 档禁止、model 必须在当前套餐目录内、provider 固定 bailian、扣 1 积分；byok 需已存该 provider 的 Key、model 自由填写、不扣积分。
- 成功后才条件扣积分（`credits >= 1`），写 `usage_record` 与 `credit_ledger`；rag 失败不扣。
- free 每 30 天重置 100 积分；付费到期未续费回落 free。`ensureCurrent` 在账户查询与 ask 前执行。
- 启动迁移（`SchemaMigrator`）：PRAGMA 检查 user 缺列才 ALTER，保留现有数据；幂等 seed `plan_catalog` / `model_catalog`。
- BYOK 明文 Key 只在 ask 请求体内传给 rag，不落库、不写日志；错误码 40201 积分不足 / 40202 余额不足。

## rag 转发

`RagClient` 是唯一调用 Python 的出口（`omniread.rag.base-url`，默认 `http://127.0.0.1:8000`）。
章节增删改与 seed 后在后台单线程触发 `/v1/index`，连续变更合并为一次，不阻塞保存；
ask 携带当前进度章节号与最近 6 条历史，`top_k=8`。

## 校验

```bash
./mvnw -DskipTests compile
./mvnw test   # 临时 SQLite + 随机端口 + 进程内 rag stub
```
