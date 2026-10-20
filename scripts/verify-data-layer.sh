#!/usr/bin/env bash
# 数据层端到端验证：迁移升级 / 回滚往返 + 对象读写。
#
# 验收项：迁移可升级回滚，对象读写通过。
# 本脚本会真连 PostgreSQL（**只允许本地 compose 容器**）与对象存储（本地 MinIO 9100，或外部 S3），
# 因此不属于日常快速校验，只在显式调用时跑；`scripts/verify-all.sh --data-layer` 会转发到这里。
# **它会对迁移目标跑 `alembic downgrade base`（DROP 全部表）**：`POSTGRES_HOST/PORT` 必须指向
# 本地容器（127.0.0.1:55432）。若 `.env` 已 source（指向 RDS 隧道 15432），脚本会直接拒绝执行——
# 迁移目标与下面 `psql_t` 的断言（只查本地容器）必须是同一个库。
#
# 用法（Git Bash，仓库根执行）：
#   bash scripts/verify-data-layer.sh              复用已起的 infra
#   bash scripts/verify-data-layer.sh --start-infra  先用 compose 起 infra 再跑
#   bash scripts/verify-data-layer.sh --keep-objects 对象读写后不删除测试对象
#   bash scripts/verify-data-layer.sh --help
#
# 凭据只从环境变量读：POSTGRES_PASSWORD 供迁移连库；对象存储用 MINIO_ROOT_USER /
# MINIO_SECRET_KEY（本地），或 AWS_*（外部 S3）。两者都不写文件、不打印。
# 起不来时的排查提示会直接打在下面对应步骤里。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"
COMPOSE_FILE="$ROOT/infra/docker/docker-compose.yml"

PG_CONTAINER="omniread-postgres"
PG_USER="${POSTGRES_USER:-omniread}"
PG_DB="${POSTGRES_DB:-omniread}"
MINIO_USER="${MINIO_ROOT_USER:-MinIO-Omniread}"
# 外部对象存储（AWS）已配置时不检查本地 MinIO 容器，凭据改从 AWS_* 读。
OBJECT_STORE_EXTERNAL=0
[ -n "${AWS_ACCESS_KEY_ID:-}" ] && OBJECT_STORE_EXTERNAL=1

START_INFRA=0
KEEP_OBJECTS=0
for arg in "$@"; do
  case "$arg" in
    --start-infra) START_INFRA=1 ;;
    --keep-objects) KEEP_OBJECTS=1 ;;
    -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/,""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

PASS=0
FAIL=0
step() { printf '\n=== %s ===\n' "$1"; }
ok()   { printf '  OK   %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  FAIL %s\n       看这里：%s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }

# uv 不在 PATH 上时用 WinGet 安装目录下的绝对路径（与 dev-up.sh / verify-all.sh 一致）。
find_uv() {
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  local p="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  [ -x "$p" ] && { echo "$p"; return; }
  echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2; exit 2
}

container_running() { # container_name
  [ "$(docker inspect --format '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]
}

# 在 PG 容器里执行 SQL（容器内本地 socket 默认 trust，不需要口令，也不打印任何凭据）。
psql_t() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "$1" 2>&1; }

# ---------- 0. 前置条件 ----------
step "0 前置条件：docker / infra 容器 / 凭据"

if ! command -v docker >/dev/null 2>&1; then
  echo "  失败：找不到 docker。装好 Docker Desktop 并启动后重试。" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "  失败：Docker 守护进程没在跑。启动 Docker Desktop 后重试。" >&2
  exit 2
fi

if ! container_running "$PG_CONTAINER"; then
  if [ "$START_INFRA" -eq 1 ]; then
    echo "  容器未起，按 --start-infra 执行 docker compose up -d ..."
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?--start-infra 需要 POSTGRES_PASSWORD 经 keymgr 注入}" \
    MINIO_SECRET_KEY="${MINIO_SECRET_KEY:?--start-infra 需要 MINIO_SECRET_KEY 经 keymgr 注入}" \
      docker compose -f "$COMPOSE_FILE" up -d || { echo "  失败：compose up 未成功，看上方输出。" >&2; exit 2; }
    for _ in $(seq 1 120); do container_running "$PG_CONTAINER" && break; sleep 0.5; done
  else
    cat >&2 <<EOF
  失败：PostgreSQL 没起来（容器 $PG_CONTAINER 不在运行）。
       先跑：bash scripts/dev-up.sh
       或加：bash scripts/verify-data-layer.sh --start-infra
EOF
    exit 2
  fi
fi
if ! container_running "$PG_CONTAINER"; then
  echo "  失败：等待 $PG_CONTAINER 超时。看 docker logs $PG_CONTAINER" >&2
  exit 2
fi
ok "PostgreSQL 容器在运行（$PG_CONTAINER）"

if [ "$OBJECT_STORE_EXTERNAL" -eq 0 ]; then
  if ! container_running omniread-minio; then
    cat >&2 <<EOF
  失败：MinIO 没起来（容器 omniread-minio 不在运行）。
       先跑：bash scripts/dev-up.sh
       或加：bash scripts/verify-data-layer.sh --start-infra
       用外部 S3 时改注入 AWS_* 与 S3_BUCKET_NAME，本检查会自动跳过。
EOF
    exit 2
  fi
  ok "MinIO 容器在运行（omniread-minio）"
fi

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  cat >&2 <<EOF
  失败：POSTGRES_PASSWORD 未注入，迁移连不上库（凭据只从环境变量读）。
       注入方式：keymgr run omniread bash scripts/verify-data-layer.sh
       或先在当前 shell 导出 POSTGRES_PASSWORD 再重跑。
EOF
  exit 2
fi
ok "POSTGRES_PASSWORD 已注入（不打印）"

if [ "$OBJECT_STORE_EXTERNAL" -eq 1 ]; then
  if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ] \
     || [ -z "${S3_BUCKET_NAME:-}" ]; then
    cat >&2 <<EOF
  失败：外部 S3 需要 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / S3_BUCKET_NAME。
       注入方式：set -a; . ./.env; set +a 后重跑。
EOF
    exit 2
  fi
  ok "外部 S3 凭据已注入（不打印）"
elif [ -z "${MINIO_SECRET_KEY:-}" ]; then
  cat >&2 <<EOF
  失败：MINIO_SECRET_KEY 未注入，对象读写无法登录 MinIO。
       注入方式：keymgr run omniread bash scripts/verify-data-layer.sh
EOF
  exit 2
fi
if [ "$OBJECT_STORE_EXTERNAL" -eq 0 ]; then
  ok "MINIO_SECRET_KEY 已注入（不打印）"
fi

# 迁移和对象读写都用同一份 Settings / session，凭据经环境变量传入子进程。
export POSTGRES_PASSWORD
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-55432}"

# ---------- 硬守卫：本脚本会 DROP 全部表，只允许本地 compose 容器 ----------
# `:-` 只在变量未设置时补默认，已导出的值原样保留——`.env` 里 POSTGRES_PORT=15432
# 指向 RDS 隧道时，downgrade 会打到真库上，而下面的 psql_t 断言只查本地容器，
# 「数据没了」不会被正确报出。这里拒绝，不警告。
if [ "$POSTGRES_HOST" != "127.0.0.1" ] && [ "$POSTGRES_HOST" != "localhost" ]; then
  echo "  失败：POSTGRES_HOST=$POSTGRES_HOST 不是本地容器；本脚本会 DROP 全部表，拒绝执行。" >&2
  echo "       本地跑请先 unset POSTGRES_HOST POSTGRES_PORT。" >&2
  exit 2
fi
if [ "$POSTGRES_PORT" != "55432" ]; then
  echo "  失败：POSTGRES_PORT=$POSTGRES_PORT 疑似指向 RDS 隧道（15432）；本脚本会 DROP 全部表，拒绝执行。" >&2
  echo "       本地跑请先 unset POSTGRES_HOST POSTGRES_PORT。" >&2
  exit 2
fi
ok "迁移目标：$POSTGRES_HOST:$POSTGRES_PORT（本地容器；本脚本只允许它）"

export POSTGRES_DB="$PG_DB"
export POSTGRES_USER="$PG_USER"
export OMNIREAD_IMAGE_STORAGE_BACKEND=s3
export OMNIREAD_OBJECT_STORE_PREFIX="${OMNIREAD_OBJECT_STORE_PREFIX:-omniread}"
export OMNIREAD_OBJECT_STORE_PROXY="${OMNIREAD_OBJECT_STORE_PROXY:-}"
if [ "$OBJECT_STORE_EXTERNAL" -eq 1 ]; then
  # AWS 凭据名 → 应用侧通用名，映射只在这里做一次。
  export OMNIREAD_OBJECT_STORE_ENDPOINT="${OMNIREAD_OBJECT_STORE_ENDPOINT:-s3.${AWS_DEFAULT_REGION}.amazonaws.com}"
  export OMNIREAD_OBJECT_STORE_REGION="${AWS_DEFAULT_REGION:-}"
  export OMNIREAD_OBJECT_STORE_BUCKET="$S3_BUCKET_NAME"
  export OMNIREAD_OBJECT_STORE_SECURE="${OMNIREAD_OBJECT_STORE_SECURE:-true}"
  export OMNIREAD_OBJECT_STORE_ACCESS_KEY="$AWS_ACCESS_KEY_ID"
  export OMNIREAD_OBJECT_STORE_SECRET_KEY="$AWS_SECRET_ACCESS_KEY"
else
  export OMNIREAD_OBJECT_STORE_ENDPOINT="${OMNIREAD_OBJECT_STORE_ENDPOINT:-127.0.0.1:9100}"
  export OMNIREAD_OBJECT_STORE_REGION=""
  export OMNIREAD_OBJECT_STORE_BUCKET="${OMNIREAD_OBJECT_STORE_BUCKET:-omniread-sources}"
  export OMNIREAD_OBJECT_STORE_SECURE="${OMNIREAD_OBJECT_STORE_SECURE:-false}"
  export OMNIREAD_OBJECT_STORE_ACCESS_KEY="${OMNIREAD_OBJECT_STORE_ACCESS_KEY:-$MINIO_USER}"
  export OMNIREAD_OBJECT_STORE_SECRET_KEY="${OMNIREAD_OBJECT_STORE_SECRET_KEY:-${MINIO_SECRET_KEY:-}}"
fi
# Windows 控制台默认不是 UTF-8，Python 子进程统一按 UTF-8 输出，避免中文提示变乱码。
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
# 对象样本默认用 book 1；桶里已有 book 1 的正式导入产物时，可用它换一个空 book 前缀，
# 避免验证覆盖真实数据（脚本自身也会在发现 manifest.json 时拒绝写入）。
export OMNIREAD_VERIFY_BOOK_ID="${OMNIREAD_VERIFY_BOOK_ID:-1}"

UV="$(find_uv)"
alembic() { "$UV" run --directory "$RAG_DIR" alembic "$@"; }

# ---------- 1. 迁移升级 ----------
step "1 迁移升级：alembic upgrade head"
if alembic upgrade head; then
  ok "alembic upgrade head"
else
  bad "alembic upgrade head" "$RAG_DIR/migrations/；建扩展失败看容器日志 docker logs $PG_CONTAINER"
fi

TABLES="$(psql_t "SELECT string_agg(tablename, ',' ORDER BY tablename) FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version';")"
if [ "$TABLES" = "books,chapters,chunk_mappings,chunks,rag_runs,volumes" ]; then
  ok "六张表就位：$TABLES"
else
  bad "表集合与预期不一致" "实际：$TABLES
期望：books,chapters,chunk_mappings,chunks,rag_runs,volumes"
fi

if [ "$(psql_t "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename='progress';")" = "0" ]; then
  ok "progress 不在本库"
else
  bad "progress 表不该存在于 RAG 库" "阅读进度由 Java 侧持久化；删表并修迁移"
fi

VECTOR_VERSION="$(psql_t "SELECT extversion FROM pg_extension WHERE extname='vector';")"
if [ -n "$VECTOR_VERSION" ]; then
  ok "vector 扩展已建：$VECTOR_VERSION"
else
  bad "vector 扩展缺失" "迁移第一步 CREATE EXTENSION IF NOT EXISTS vector 未生效"
fi

EMBEDDING_TYPE="$(psql_t "SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding' AND NOT attisdropped;")"
if [ "$EMBEDDING_TYPE" = "vector(1024)" ]; then
  ok "chunks.embedding = vector(1024)"
else
  bad "embedding 维度不是 1024（实际：$EMBEDDING_TYPE）" "维度是单向门，改维度要重建向量列"
fi

HNSW_DEF="$(psql_t "SELECT indexdef FROM pg_indexes WHERE indexname='ix_chunks_embedding_hnsw';")"
if echo "$HNSW_DEF" | grep -q "USING hnsw" \
   && echo "$HNSW_DEF" | grep -Eq "m='?16'?" \
   && echo "$HNSW_DEF" | grep -Eq "ef_construction='?64'?"; then
  ok "HNSW 索引参数显式：m=16 / ef_construction=64"
else
  bad "HNSW 索引缺失或参数不是 m=16 / ef_construction=64" "实际定义：$HNSW_DEF"
fi

# 运行时 GUC 的落点：走项目自己的引擎连一次库，确认连接层真的下发了这三个参数。
if "$UV" run --directory "$RAG_DIR" python - <<'PY'
import sys

from sqlalchemy import text

try:
    from omniread.infrastructure.db.session import create_engine_from_env
    engine = create_engine_from_env()
    with engine.connect() as connection:
        actual = {
            name: connection.execute(text(f"SHOW hnsw.{name}")).scalar()
            for name in ("iterative_scan", "max_scan_tuples", "ef_search")
        }
except Exception as exc:  # noqa: BLE001 - 验证脚本要把任何失败原因打出来
    print(f"      连接层下发失败：{exc}")
    sys.exit(1)

expected = {"iterative_scan": "relaxed_order", "max_scan_tuples": "20000", "ef_search": "100"}
for name, want in expected.items():
    if str(actual.get(name)) != want:
        print(f"      hnsw.{name} 期望 {want}，实际 {actual.get(name)}")
        sys.exit(1)
print(f"      {actual}")
PY
then
  ok "会话 GUC：hnsw.iterative_scan / max_scan_tuples / ef_search 已下发"
else
  bad "会话 GUC 未按约定下发" "看 infrastructure/db/session.py 的 HNSW_SESSION_SETTINGS"
fi

# ---------- 2. 迁移回滚 ----------
step "2 迁移回滚：alembic downgrade base"
if alembic downgrade base; then
  ok "alembic downgrade base"
else
  bad "alembic downgrade base" "$RAG_DIR/migrations/versions/；看 alembic 输出的首个 ERROR"
fi

REMAINING="$(psql_t "SELECT coalesce(string_agg(tablename, ',' ORDER BY tablename), '') FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version';")"
if [ -z "$REMAINING" ]; then
  ok "回滚后业务表清空（仅剩 alembic_version）"
else
  bad "回滚后有残留表：$REMAINING" "downgrade 的 DROP 顺序或遗漏"
fi

# ---------- 3. 再升级（往返） ----------
step "3 再次升级：alembic upgrade head（确认往返可重复）"
if alembic upgrade head; then
  ok "upgrade → downgrade → upgrade 往返"
else
  bad "二次 upgrade 失败" "迁移不可重复执行，检查是否用了不带 IF NOT EXISTS 的裸对象创建"
fi
if [ "$(psql_t "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename='chunks';")" = "1" ]; then
  ok "二次升级后 chunks 表存在"
else
  bad "二次升级后 chunks 表缺失" "看 alembic 输出"
fi

# ---------- 4. 对象读写 ----------
step "4 对象读写：写入 → 读回比对 → 清理（MinIO bucket）"
KEEP_FLAG=0
[ "$KEEP_OBJECTS" -eq 1 ] && KEEP_FLAG=1
export OMNIREAD_VERIFY_KEEP_OBJECTS="$KEEP_FLAG"
if "$UV" run --directory "$RAG_DIR" python - <<'PY'
import hashlib
import os
import sys

from minio.error import S3Error

from omniread.config import Settings
from omniread.infrastructure.objectstore.s3 import build_object_store

BOOK = int(os.environ.get("OMNIREAD_VERIFY_BOOK_ID", "1"))
# 验证对象只写保留前缀 _verify/：即使脚本中断，也不会和 books/ 下的产品数据混在一起。
ROOT = f"_verify/books/{BOOK}/"
PAYLOADS = {
    f"{ROOT}source/index.jsonl": (b'{"id":"verify-only"}\n', "application/x-ndjson"),
    f"{ROOT}source/说明.md": ("# 验证样本\n".encode(), "text/markdown; charset=utf-8"),
    f"{ROOT}checksums.json": (b'{"book_id":1,"chapters":[]}\n', "application/json"),
    f"{ROOT}manifest.json": (b'{"book_id":1,"chapter_count":0}\n', "application/json"),
}

settings = Settings()
store = build_object_store(settings)

written: list[str] = []
failures: list[str] = []
try:
    for key, (payload, content_type) in PAYLOADS.items():
        store.put(key, payload, content_type)
        written.append(key)
        stored = store.get(key)
        if stored is None:
            failures.append(f"{key} 读回为空")
            continue
        if stored.data != payload:
            failures.append(f"{key} 读回字节不一致")
        if hashlib.sha256(stored.data).hexdigest() != hashlib.sha256(payload).hexdigest():
            failures.append(f"{key} sha256 不一致")
        if stored.content_type != content_type:
            failures.append(f"{key} content-type 期望 {content_type}，实际 {stored.content_type}")
except S3Error as exc:
    print(f"      对象存储访问失败：{exc}")
    sys.exit(1)

if failures:
    print("      " + "；".join(failures))
    sys.exit(1)

print(f"      写入并读回 {len(written)} 个对象，字节、sha256 与 content-type 一致")

if os.environ.get("OMNIREAD_VERIFY_KEEP_OBJECTS") == "1":
    print("      按 --keep-objects 保留测试对象，未清理")
    sys.exit(0)

for key in written:
    store.remove(key)
left = [key for key in written if store.exists(key)]
if left:
    print(f"      清理后仍存在：{left}")
    sys.exit(1)
print(f"      已清理 {len(written)} 个测试对象")
PY
then
  ok "对象写入 / 读回 / 清理通过（前缀 $OMNIREAD_OBJECT_STORE_PREFIX/_verify/）"
else
  bad "对象读写失败" "本地看 docker logs omniread-minio；外部 S3 看 AWS_* 与 IAM 策略；见上方 python 输出"
fi

# ---------- 汇总 ----------
printf '\n=== 汇总：%d 项通过，%d 项失败 ===\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "M0-2 数据层验证通过（迁移可升级回滚，对象读写通过）。"
else
  echo "存在失败项；PG 相关先看 bash scripts/dev-up.sh，对象相关先看 docker logs omniread-minio。"
fi
[ "$FAIL" -eq 0 ] || exit 1
