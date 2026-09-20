# infra/docker —— M0 本地基础设施

M0 的数据面只有两件东西：

| 服务 | 镜像 | 宿主端口 | 容器内端口 | 用途 |
| --- | --- | --- | --- | --- |
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.6-pg16` | 55432 | 5432 | 结构索引、检索与服务数据（M0-02 §3） |
| MinIO | `minio/minio:RELEASE.2025-04-22T22-12-26Z` | 9100 / 9101 | 9000 / 9001 | 原始件归档：语料与插图（M0-02 §4） |

Java / Python 服务不在这个 compose 里，由各自的构建流程启动。

## 起停

先注入凭据（值不落文件）：

```bash
keymgr ...        # 注入 POSTGRES_PASSWORD、MINIO_SECRET_KEY、GLM_API_KEY、DEEPSEEK_API_KEY、DASHSCOPE_API_KEY
```

然后在**仓库根**执行（`-f` 指定文件时，compose 的项目目录就是 `infra/docker`，`.env` 也从那里读）：

```bash
docker compose -f infra/docker/docker-compose.yml config      # 只校验语法与变量插值
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml ps
docker compose -f infra/docker/docker-compose.yml down        # 加 -v 会连数据卷一起删
```

`minio-init` 是一次性容器：等 minio 健康后建好 `omniread-sources` 桶就退出，`Exited (0)` 是正常状态。

## 端口为什么是这样

- **PostgreSQL 55432**：宿主 5432 可能已被别的实例占用，映射到 55432 让本机可以并存多个 PG。
  连接串用 `postgresql://omniread@localhost:55432/omniread`（密码由 keymgr 注入）。
- **MinIO 9100 / 9101**：本机已有一个 minio 容器在跑并占用 9000/9001，两个都映射 9000 会直接起不来。
  9100 是 S3 API（`http://localhost:9100`），9101 是控制台（`http://localhost:9101`）。

容器内部端口保持镜像默认（5432、9000/9001），换机器时只需改宿主侧。

## 初始化做了什么

- **pgvector**：官方镜像只带扩展文件，**不会自动 `CREATE EXTENSION`**。
  `initdb/01-create-extension.sql` 挂在 `/docker-entrypoint-initdb.d/`，在数据卷首次初始化时建好扩展。
  这一步必须早于 Alembic 迁移——迁移会直接用 `vector` 类型。
  该脚本只在**空数据卷**上执行；改了它要看到效果必须先 `down -v` 重建数据卷。
- **MinIO**：不会自动建桶，`minio-init` 负责建 `omniread-sources`。

## 验证

```bash
# 扩展已建好，并且版本 ≥ 0.8
docker exec omniread-postgres psql -U omniread -d omniread -c \
  "SELECT extversion FROM pg_extension WHERE extname = 'vector';"

# 桶已存在（minio-init 退出后）
docker run --rm --network omniread-m0_default --entrypoint sh \
  minio/minio:RELEASE.2025-04-22T22-12-26Z \
  -c 'mc alias set om http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc ls om'
```

也可以直接跑 `infra/docker/scripts/verify.sh`，它把上面两步和健康状态一起查一遍。

## 注意事项

- **MinIO 这个 tag 拉不到了**：`minio/minio` 在 Docker Hub 的仓库已下线，该 tag 实测返回 404。
  它只在本机可用（镜像已在本地缓存）。换机器时改用 `quay.io/minio/minio` 的冻结 tag，
  并同步修改 compose——两处 `minio/minio:` 都要改。
- **不要动本机既有容器**：`minio`（9000/9001）、`mysql-dev`、`redis-dev` 与本 compose 无关。
- **凭据不写文件**：compose 里的 `POSTGRES_PASSWORD`、`MINIO_SECRET_KEY` 都是必填插值，
  未注入时 `docker compose config` / `up` 会直接报错，而不是退化成空密码。
- **第一次 `up` 就要用正式凭据**：PostgreSQL 只在数据卷首次初始化时读 `POSTGRES_PASSWORD`，
  之后改环境变量不会改库里的口令。先用临时口令起过一次，就要 `down -v` 重建数据卷，
  否则后续连接会一直用旧口令。
- **MinIO 的 secret 至少 8 个字符**：短于 8 时容器直接 FATAL 退出并反复重启，
  compose 只看到 `container is unhealthy`，看不出根因。用 keymgr 里的正式值不会碰到这条。
