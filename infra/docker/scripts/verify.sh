#!/usr/bin/env bash
# 起停之后的自检：容器状态 + pgvector 扩展 + MinIO 桶。
# 只读取状态，不改动任何容器；不打印凭据。
#
# 用法（凭据从 keymgr 注入的环境变量来）：
#   bash infra/docker/scripts/verify.sh
set -u

PG_CONTAINER="omniread-postgres"
MINIO_IMAGE="minio/minio:RELEASE.2025-04-22T22-12-26Z"
NETWORK="omniread-m0_default"
MINIO_USER="${MINIO_ROOT_USER:-MinIO-Omniread}"
MINIO_PASS="${MINIO_SECRET_KEY:-}"
fail=0

echo "== 容器状态 =="
# 不用 compose ps：它会对必填的凭据变量做插值，把本脚本变成需要密码才能跑
docker ps -a --filter "name=omniread" --format "table {{.Names}}\t{{.Status}}" || fail=1

echo
echo "== pgvector 扩展 =="
if version=$(docker exec "$PG_CONTAINER" psql -U omniread -d omniread -tAc \
    "SELECT extversion FROM pg_extension WHERE extname = 'vector';" 2>/dev/null); then
  echo "  vector $version（期望 0.8.x）"
else
  echo "  失败：连不上库或扩展未建（先确认容器健康，或 down -v 后重建数据卷）"
  fail=1
fi

echo
echo "== MinIO 桶 =="
if [ -z "$MINIO_PASS" ]; then
  echo "  跳过：MINIO_SECRET_KEY 未注入"
  fail=1
elif docker run --rm --network "$NETWORK" --entrypoint sh \
    -e MINIO_ROOT_USER="$MINIO_USER" -e MINIO_ROOT_PASSWORD="$MINIO_PASS" \
    "$MINIO_IMAGE" -c \
    'mc alias set om http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls om' 2>/dev/null; then
  echo "  桶列表如上（期望 omniread-sources）"
else
  echo "  失败：连不上 MinIO 或凭据不对"
  fail=1
fi

echo
[ "$fail" -eq 0 ] && echo "全部通过" || echo "存在失败项"
exit "$fail"
