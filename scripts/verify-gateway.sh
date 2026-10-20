#!/usr/bin/env bash
# Java 网关联调验证：起真实 Python（假 provider）+ 真实 Java 网关，逐条跑外部 API。
#
# 验收项：`Client → Java → Python` 端到端通过。
# 覆盖：六组 GET 的 Java/Python 一致性、插图字节与目录穿越防护、同步与流式问答透传、
# request_id 生成与透传、SSE 逐帧到达、进度由 Java 本地读写、400/502/504/503 错误路径。
#
# 本脚本自己起停服务，结束（含失败）会回收 RAG / 8080 上的进程，不留孤儿。
# 不发任何真实 provider 调用：Python 用 OMNIREAD_ANSWER_PROVIDER=fake +
# OMNIREAD_RETRIEVAL_PROVIDER=fake，插图走本地目录，不连对象存储。
#
# 前置：
#   - PostgreSQL 已在跑，连接参数从环境变量读：默认本机 55432；迁到 RDS 后是隧道 127.0.0.1:15432；
#   - 环境变量 POSTGRES_PASSWORD 已注入（缺 keymgr profile 时手动传，例如
#     `POSTGRES_PASSWORD=<口令> bash scripts/verify-gateway.sh`）；
#   - 仓库内语料 asset/ 至少有一张插图（用于字节级比对），Java jar 不存在会自动构建；
#   - RAG 端口默认 8000，可用 OMNIREAD_RAG_PORT 覆盖（本机 8000 可能落在 Windows 保留段里）。
#
# 用法：
#   bash scripts/verify-gateway.sh
#   bash scripts/verify-gateway.sh --help
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/temp/gateway-e2e"
IMAGES_ROOT="$RUN_DIR/images"
JAR="$ROOT/services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar"
RAG_PY_DIR="$ROOT/services/rag"
# uv 优先走 PATH；本机装了 uv 但不在 PATH 时回落到 WinGet 安装目录。
# 别写死成 Windows 路径：其余 verify-* 脚本都是这个两段式，写死会让脚本在别的平台直接失效。
if command -v uv >/dev/null 2>&1; then
  UV="uv"
else
  UV="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  if [ ! -x "$UV" ]; then
    echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2
    exit 2
  fi
fi
PYTHON_LOG=""
STREAM_DELAY_MS=200
# 本机 8000 可能落在 Windows 动态保留段里（绑定报 WinError 10013），与 dev-up.sh 同一个开关。
RAG_PORT="${OMNIREAD_RAG_PORT:-8000}"
# PG 走环境变量：默认本机 55432；迁到 RDS 后是隧道 127.0.0.1:15432。
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-55432}"
# 进度落在 Java 侧 SQLite（C2 起不再有 progress.json）；断言只看它是不是本地存在。
DB_FILE="${OMNIREAD_DB_FILE:-$ROOT/var/omniread.db}"
# 联调账户：每次跑新建、结束时停用；口令只经环境变量传，不打印。
E2E_USER="e2e-gateway-$$"
E2E_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | cut -c1-24)"
E2E_READY=0

case "${1:-}" in
  -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/,""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
esac

log()  { printf '[gateway] %s\n' "$*"; }
die()  { printf '[gateway] 失败：%s\n' "$*" >&2; exit 1; }

if command -v uv >/dev/null 2>&1; then
  UV="uv"
elif [ ! -x "$UV" ]; then
  die "找不到 uv；装好 uv 或把 uv 加进 PATH 后重试"
fi

# 端口回收：Windows 路径先 taskkill，再退回 MSYS kill（与 dev-down.sh 同口径）。
stop_port() {
  local port="$1" pids p
  pids="$(netstat -ano 2>/dev/null | grep -E "[:.]$port[[:space:]]+" | grep LISTENING | awk '{print $NF}' | sort -u)"
  [ -z "$pids" ] && return 0
  for p in $pids; do
    taskkill //F //T //PID "$p" >/dev/null 2>&1 || kill "$p" 2>/dev/null || true
  done
}

cleanup() {
  local status=$?
  log "清理：结束 $RAG_PORT / 8080 上的进程"
  stop_port "$RAG_PORT"
  stop_port 8080
  if [ "$E2E_READY" -eq 1 ]; then
    if bash "$ROOT/scripts/account.sh" disable "$E2E_USER" >/dev/null 2>&1; then
      log "已停用联调账户 $E2E_USER"
    else
      log "停用联调账户失败；可手动：bash scripts/account.sh disable $E2E_USER"
    fi
  fi
  return $status
}
trap cleanup EXIT

wait_http() { # label url timeout_seconds
  local label="$1" url="$2" timeout="${3:-90}" i=0
  while [ "$i" -lt $((timeout * 2)) ]; do
    curl -sf -o /dev/null --max-time 2 "$url" && { log "$label 就绪：$url"; return 0; }
    sleep 0.5; i=$((i + 1))
  done
  return 1
}

port_busy() {
  netstat -ano 2>/dev/null | grep -E "[:.]$1[[:space:]]+" | grep -q LISTENING
}

# ---------- 前置检查 ----------
[ -n "${POSTGRES_PASSWORD:-}" ] || cat >&2 <<EOF
POSTGRES_PASSWORD 未注入：本验证要真连 PostgreSQL（检索链读 chunks）。
本机可用一次性口令手动传入：
  POSTGRES_PASSWORD=<口令> bash scripts/verify-gateway.sh
有 keymgr profile 时：keymgr run <profile> bash scripts/verify-gateway.sh
EOF
[ -n "${POSTGRES_PASSWORD:-}" ] || exit 2

port_busy "$RAG_PORT" && die "端口 $RAG_PORT 已被占用；先 bash scripts/dev-down.sh 再重试"
port_busy 8080 && die "端口 8080 已被占用；先 bash scripts/dev-down.sh 再重试"

# PG 用 TCP 探测而不是 netstat：迁到 RDS 后主机可能是隧道或远端，netstat 看不到。
if ! (echo > "/dev/tcp/$PG_HOST/$PG_PORT") 2>/dev/null; then
  die "PostgreSQL $PG_HOST:$PG_PORT 不可达；本机开发先起 docker 的 PG，或用 temp/rds-tunnel.py 起隧道"
fi

mkdir -p "$RUN_DIR/logs" "$IMAGES_ROOT/books/1/images/01_第1卷"
SOURCE_IMAGE="$(ls "$ROOT"/asset/*/images/01_第1卷/007.jpg 2>/dev/null | head -1)"
[ -n "$SOURCE_IMAGE" ] || die "仓库内找不到语料插图 asset/*/images/01_第1卷/007.jpg"
cp "$SOURCE_IMAGE" "$IMAGES_ROOT/books/1/images/01_第1卷/007.jpg"
# 目录穿越的诱饵：防护失效时它会被读出来，断言据此判失败。
printf 'omniread-e2e-secret-should-never-be-served\n' > "$IMAGES_ROOT/secret.txt"

[ -f "$JAR" ] || {
  log "Java jar 不存在，先构建"
  mvn -q -f "$ROOT/services/backend/pom.xml" -DskipTests package || die "Maven 构建失败"
}

# 登录门之后所有外部 API 都要账户：先建一个联调账户，结束时由 cleanup 停用。
log "建联调账户 $E2E_USER"
OMNIREAD_ADMIN_PASSWORD="$E2E_PASSWORD" bash "$ROOT/scripts/account.sh" create "$E2E_USER" \
  > "$RUN_DIR/logs/account-create.log" 2>&1 \
  || die "建联调账户失败，看 $RUN_DIR/logs/account-create.log"
E2E_READY=1

# ---------- 服务起停 ----------
start_python() { # fault(none|provider_error|timeout)
  local fault="$1" label="${1//_/-}"
  PYTHON_LOG="$RUN_DIR/logs/rag-$label.log"
  log "起 Python RAG（假的 answer/retrieval provider，fault=$fault）"
  (
    cd "$ROOT" && exec env \
      PYTHONUTF8=1 \
      POSTGRES_HOST="$PG_HOST" \
      POSTGRES_PORT="$PG_PORT" \
      POSTGRES_DB="${POSTGRES_DB:-omniread}" \
      POSTGRES_USER="${POSTGRES_USER:-omniread}" \
      POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
      POSTGRES_SSLMODE="${POSTGRES_SSLMODE:-}" \
      OMNIREAD_IMAGE_STORAGE_BACKEND=local \
      OMNIREAD_IMAGE_LOCAL_ROOT="$IMAGES_ROOT" \
      OMNIREAD_ANSWER_PROVIDER=fake \
      OMNIREAD_RETRIEVAL_PROVIDER=fake \
      OMNIREAD_FAKE_ANSWER_FAULT="$fault" \
      OMNIREAD_FAKE_ANSWER_DELAY_MS="$STREAM_DELAY_MS" \
      OMNIREAD_LOG_LEVEL=INFO \
      "$UV" run --directory "$RAG_PY_DIR" python -m uvicorn \
        omniread.api.app:create_app --factory --host 127.0.0.1 --port "$RAG_PORT"
  ) > "$PYTHON_LOG" 2>&1 &
  echo $! > "$RUN_DIR/logs/rag.pid"
  wait_http "Python RAG" "http://127.0.0.1:$RAG_PORT/internal/v1/health" 60 \
    || { tail -30 "$PYTHON_LOG" >&2; die "Python RAG 未在 60s 内就绪，看 $PYTHON_LOG"; }
  # 预热一次目录查询：Python 的引擎是懒连接，首个请求才建库连接；本机经 SOCKS 隧道时
  # 这次建连偶发被掐断（SSL EOF），重试几次再进断言——验的是网关接线，不是隧道抖动。
  # 库真不可用时这里重试完直接失败退出，不会被当成通过。
  curl -sf --retry 5 --retry-delay 1 --retry-all-errors \
    "http://127.0.0.1:$RAG_PORT/internal/v1/books" >/dev/null \
    || { tail -30 "$PYTHON_LOG" >&2; die "Python 预热目录查询失败（库不可用？）"; }
}

stop_python() {
  stop_port "$RAG_PORT"
  sleep 1
}

start_java() {
  log "起 Java 网关"
  # 两处覆盖都是本机验证专用：
  # - 走 http，Secure cookie 不会被客户端回送，登录态会"丢"；
  # - 验的是网关接线不是配额，默认 5 轮/分会把连续的断言打成 429。
  (
    cd "$ROOT" && exec env \
      OMNIREAD_RAG_BASE_URL="http://127.0.0.1:$RAG_PORT" \
      OMNIREAD_WEB_DIST="web/dist" \
      OMNIREAD_AUTH_COOKIE_SECURE=false \
      OMNIREAD_QUOTA_PER_MINUTE=100 \
      OMNIREAD_QUOTA_PER_DAY=1000 \
      java -jar "$JAR"
  ) > "$RUN_DIR/logs/backend.log" 2>&1 &
  echo $! > "$RUN_DIR/logs/backend.pid"
  wait_http "Java 网关" "http://127.0.0.1:8080/api/v1/health" 60 \
    || { tail -30 "$RUN_DIR/logs/backend.log" >&2; die "Java 网关未在 60s 内就绪"; }
}

stop_java() {
  stop_port 8080
  sleep 1
}

FAILED=0
run_phase() { # phase args...
  local phase="$1"; shift
  if OMNIREAD_E2E_USER="$E2E_USER" OMNIREAD_E2E_PASSWORD="$E2E_PASSWORD" \
     PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
     "$UV" run --directory "$RAG_PY_DIR" python "$ROOT/scripts/verify_gateway.py" \
      --phase "$phase" --local-store "$DB_FILE" --python-log "$PYTHON_LOG" \
      --python-base "http://127.0.0.1:$RAG_PORT" \
      --stream-delay-ms "$STREAM_DELAY_MS" "$@"; then
    return 0
  fi
  FAILED=$((FAILED + 1))
  return 1
}

# ---------- 阶段 1：主链路 ----------
start_python none
start_java
run_phase main

# ---------- 阶段 2：上游 provider 故障（真实 Python 返回 502 / 504） ----------
stop_python
start_python provider_error
run_phase fault-provider
stop_python
start_python timeout
run_phase fault-timeout

# ---------- 阶段 3：Python 不可达 ----------
stop_python
run_phase offline
stop_java

if [ "$FAILED" -eq 0 ]; then
  printf '\nM0-6 网关联调通过（全程假 provider，未发真实调用）。日志在 %s\n' "$RUN_DIR/logs"
else
  printf '\nM0-6 网关联调有 %d 个阶段失败。日志在 %s\n' "$FAILED" "$RUN_DIR/logs" >&2
fi
exit $((FAILED > 0))
