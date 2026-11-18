# gateway

Spring Boot 4.1.2 + MyBatis + SQLite 的薄网关：鉴权、限流、书/章/进度/会话 CRUD、
统一 `Result`、转发 rag。不做切片、向量、检索与 prompt。

```bash
./mvnw spring-boot:run
```

- 端口：`127.0.0.1:8080`
- 数据库：`var/gateway.db`，可用 `OMNIREAD_GATEWAY_DB` 覆盖（见 `src/main/resources/application.yml`）
- Boot 父版本写 `4.1.2`，不要带 `.RELEASE`（Maven Central 只有 `4.1.2`）
- MyBatis starter 固定为 `4.1.0`（Spring Initializr 的兼容性元数据尚未支持 Boot 4.1.2）

`RagClient` 是唯一调用 Python 的出口。章节增删改后在后台线程触发 `/v1/index`，不阻塞保存。
