#!/usr/bin/env bash
# 从备份恢复 Java 侧的 SQLite。**会覆盖当前库里的一切。**
#
# 用法（Git Bash / Linux）：
#   bash scripts/restore-db.sh <备份文件> [--yes]
#
# 做什么：停栈 → 删卷 → 重建卷 → 把备份拷回 → 清掉可能残留的 -wal / -shm → 起栈。
# 不加 --yes 会先要一次确认；非交互场景（比如 runbook）加 --yes。
#
# **版本要对得上**：`SchemaInitializer` 对「库比代码旧/新」都拒绝启动。
# 用旧备份恢复会把站点挡在启动那一步——恢复前先核对备份对应的 SCHEMA_VERSION。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME="omniread-app_omniread-data"
ASSUME_YES=0
SOURCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/,""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
    -*) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
    *) SOURCE="$1"; shift ;;
  esac
done

die() { echo "[restore] $*" >&2; exit 1; }
log() { printf '[restore] %s\n' "$*"; }

[ -n "$SOURCE" ] || { echo "用法：bash scripts/restore-db.sh <备份文件> [--yes]" >&2; exit 2; }
[ -f "$SOURCE" ] || die "找不到备份文件：$SOURCE"

if [ "$ASSUME_YES" -ne 1 ]; then
  printf '[restore] 将删除卷 %s 的全部内容并用 %s 覆盖。继续？[y/N] ' "$VOLUME" "$SOURCE"
  read -r answer
  [ "$answer" = "y" ] || [ "$answer" = "Y" ] || die "已取消"
fi

log "停止站点（保留数据卷，只是让 backend 放开数据库文件）"
systemctl stop omniread 2>/dev/null || docker compose -f "$ROOT/infra/docker/docker-compose.app.yml" stop backend

log "删除并重建卷 $VOLUME"
docker volume rm "$VOLUME" >/dev/null 2>&1 || true
docker volume create "$VOLUME" >/dev/null

MOUNTPOINT="$(docker volume inspect "$VOLUME" -f '{{ .Mountpoint }}')"
cp "$SOURCE" "$MOUNTPOINT/omniread.db"
chmod 644 "$MOUNTPOINT/omniread.db"
# 旧的 -wal / -shm 与新库不属于同一代，留着会被 SQLite 当成未提交事务去回放。
rm -f "$MOUNTPOINT/omniread.db-wal" "$MOUNTPOINT/omniread.db-shm"

log "启动站点"
systemctl start omniread 2>/dev/null || docker compose -f "$ROOT/infra/docker/docker-compose.app.yml" up -d

log "完成。验证：curl -s http://127.0.0.1:8080/api/v1/health，然后登录一次确认账户还在。"
