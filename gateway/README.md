# gateway

Spring Boot 4.1.2 + MyBatis + SQLite 的薄网关：鉴权、限流、书/章/进度/会话 CRUD、
统一 `Result`、转发 rag。不做切片、向量、检索与 prompt。

## 启动

```bash
# 首次：复制模板并填写 admin 与 jwt secret（secret 至少 32 字节，缺失则启动失败）
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
| POST | `/api/chat/sessions/{id}/ask` | `{question,level}`，level=past/full，缺省 past |

除登录外均需 `Authorization: Bearer <token>`。

## rag 转发

`RagClient` 是唯一调用 Python 的出口（`omniread.rag.base-url`，默认 `http://127.0.0.1:8000`）。
章节增删改与 seed 后在后台单线程触发 `/v1/index`，连续变更合并为一次，不阻塞保存；
ask 携带当前进度章节号与最近 6 条历史，`top_k=8`。

## 校验

```bash
./mvnw -DskipTests compile
./mvnw test   # 临时 SQLite + 随机端口 + 进程内 rag stub
```
