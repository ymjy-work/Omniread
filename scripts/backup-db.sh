#!/usr/bin/env bash
# 备份 Java 侧的 SQLite（账户 / 会话 / 进度 / 用量）。
#
# 用法（Git Bash / Linux）：
#   bash scripts/backup-db.sh [--out <目录>] [--keep <天数>]
#
# 做什么：对活动库跑 `VACUUM INTO`，得到一份**一致快照**（含 WAL 里还没落盘的部分），
# 落到宿主机 <目录>/omniread-YYYYmmdd-HHMMSS.db，权限 0600。
# **不要直接 cp**：库开着 WAL，cp 出来的可能是缺 `-wal` 的坏快照。
#
# 依赖：宿主机有 sqlite3（`apt install -y sqlite3`）。容器里没有，镜像里只有 Java。
# 红线：备份含 chat_messages，可能逐字含原著片段——只落本机、权限 0600，
#       不进 git / S3 / 同步盘。**同机备份防的是误删与容器重建，不防主机级事故。**
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME="omniread-app_omniread-data"
OUT="/var/backups/omniread"
KEEP_DAYS=14

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="${2:?--out 需要目录}"; shift 2 ;;
    --keep) KEEP_DAYS="${2:?--keep 需要天数}"; shift 2 ;;
    -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/,""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

die() { echo "[backup] $*" >&2; exit 1; }
log() { printf '[backup] %s\n' "$*"; }

command -v sqlite3 >/dev/null 2>&1 \
  || die "宿主机没有 sqlite3。装一个：sudo apt install -y sqlite3"

MOUNTPOINT="$(docker volume inspect "$VOLUME" -f '{{ .Mountpoint }}' 2>/dev/null || true)"
[ -n "$MOUNTPOINT" ] || die "找不到卷 $VOLUME（站点没起过，或 compose 项目名变了）"

DB="$MOUNTPOINT/omniread.db"
[ -f "$DB" ] || die "卷里没有 omniread.db：$DB"

mkdir -p "$OUT"
chmod 700 "$OUT"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
TARGET="$OUT/omniread-$STAMP.db"

# VACUUM INTO 读的是同一条连接上的快照：库还在写也不会拿到半截数据。
# 先写临时名，成功后再改名——中断留下的半成品不会被当成一份有效备份。
sqlite3 "$DB" ".timeout 5000" "VACUUM INTO '$TARGET.partial'"
mv "$TARGET.partial" "$TARGET"
chmod 600 "$TARGET"

log "已备份 → $TARGET（$(du -h "$TARGET" | cut -f1)）"

# 轮转：只按文件名里的日期判，不用 -mtime（那样会受文件被复制的时间影响）。
find "$OUT" -maxdepth 1 -name 'omniread-*.db' -mtime "+$KEEP_DAYS" -print -delete \
  | sed 's/^/[backup] 清理过期备份：/'

log "完成。当前共 $(find "$OUT" -maxdepth 1 -name 'omniread-*.db' | wc -l) 份。"
