#!/usr/bin/env bash
# Omniread M0 停止脚本：先停 Java / Python（可选前端），再按需停基础设施。
#
# 用法（Git Bash）：
#   bash scripts/dev-down.sh          只停 Java + Python（+ 前端，若在跑）
#   bash scripts/dev-down.sh --all    连 infra 容器一起停（保留数据卷）
#   bash scripts/dev-down.sh --all -v 连数据卷一起删（PostgreSQL / MinIO 数据清空）
#
# 停止优先按 temp/run/*.pid 记录，找不到再按端口回收，避免残留进程占住 8000 / 8080。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/temp/run"
COMPOSE_FILE="$ROOT/infra/docker/docker-compose.yml"

STOP_INFRA=0
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --all) STOP_INFRA=1 ;;
    -v|--volumes) PURGE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

log() { printf '[dev-down] %s\n' "$*"; }

# 按端口结束进程（Windows 路径：taskkill）。
stop_port() {
  local port="$1" pids p
  pids="$(netstat -ano 2>/dev/null | grep -E "[:.]$port[[:space:]]+" | grep LISTENING | awk '{print $NF}' | sort -u)"
  [ -z "$pids" ] && return 0
  for p in $pids; do
    log "结束占用端口 $port 的进程 PID=$p"
    taskkill //F //T //PID "$p" >/dev/null 2>&1 || kill "$p" 2>/dev/null || true
  done
}

# 先按 pid 文件停，确保服务本身（不是它的父 shell）被回收。
stop_service() { # name pidfile port
  local name="$1" pidfile="$2" port="$3" pid
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ]; then
      # pid 文件记的是 MSYS 侧 pid：先试 Windows 的 taskkill，再退回 MSYS kill。
      # 两者都失败时交给下面的按端口回收兜底。
      if taskkill //F //T //PID "$pid" >/dev/null 2>&1 || kill "$pid" 2>/dev/null; then
        log "已停止 $name（PID $pid）"
      fi
    fi
    rm -f "$pidfile"
  fi
  stop_port "$port"
}

stop_service "Java 网关" "$RUN_DIR/backend.pid" 8080
stop_service "Python RAG" "$RUN_DIR/rag.pid" 8000
stop_service "前端 dev server" "$RUN_DIR/web.pid" 5173

if [ "$STOP_INFRA" -eq 1 ]; then
  # down 只做删除，插值里的占位值仅为通过 compose 的必填校验，不会写进任何文件、也不影响已有数据。
  local_args=()
  [ "$PURGE" -eq 1 ] && local_args+=(--volumes)
  log "停止基础设施${PURGE:+（连数据卷一起删）}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-__teardown__}" \
  MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-__teardown__}" \
    docker compose -f "$COMPOSE_FILE" down "${local_args[@]}" \
    || log "compose down 失败：可能 infra 本来就没起过"
fi

log "完成。容器状态："
docker ps -a --filter "name=omniread" --format "table {{.Names}}\t{{.Status}}"
