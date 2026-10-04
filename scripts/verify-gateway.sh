#!/usr/bin/env bash
# M0-6 Java 网关联调验证：起真实 Python（假 provider）+ 真实 Java 网关，逐条跑外部 API。
#
# 验收对应（M0-03 §2 M0-6）：`Client → Java → Python` 端到端通过。
# 覆盖：六组 GET 的 Java/Python 一致性、插图字节与目录穿越防护、同步与流式问答透传、
# request_id 生成与透传、SSE 逐帧到达、进度由 Java 本地读写、400/502/504/503 错误路径。
#
# 本脚本自己起停服务，结束（含失败）会回收 8000 / 8080 上的进程，不留孤儿。
# 不发任何真实 provider 调用：Python 用 OMNIREAD_ANSWER_PROVIDER=fake +
# OMNIREAD_RETRIEVAL_PROVIDER=fake，插图走本地目录，不连 MinIO。
#
# 前置：
#   - PostgreSQL（宿主 55432）已在跑：`bash scripts/dev-up.sh` 或 `docker compose up -d`；
#   - 环境变量 POSTGRES_PASSWORD 已注入（缺 keymgr profile 时手动传，例如
#     `POSTGRES_PASSWORD=<口令> bash scripts/verify-gateway.sh`）；
#   - 仓库内语料 asset/ 至少有一张插图（用于字节级比对），Java jar 不存在会自动构建。
#
# 用法：
#   bash scripts/verify-gateway.sh
#   bash scripts/verify-gateway.sh --help
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/temp/gateway-e2e"
IMAGES_ROOT="$RUN_DIR/images"
PROGRESS_FILE="$RUN_DIR/progress.json"
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

case "${1:-}" in
  -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
esac

log()  { printf '[gateway] %s\n' "$*"; }
die()  { printf '[gateway] 失败：%s\n' "$*" >&2; exit 2; }

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
  log "清理：结束 8000 / 8080 上的进程"
  stop_port 8000
  stop_port 8080
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

port_busy 8000 && die "端口 8000 已被占用；先 bash scripts/dev-down.sh 再重试"
port_busy 8080 && die "端口 8080 已被占用；先 bash scripts/dev-down.sh 再重试"

if ! port_busy 55432; then
  die "PostgreSQL 55432 不可达；先 bash scripts/dev-up.sh（或 docker compose up -d）"
fi

mkdir -p "$RUN_DIR/logs" "$IMAGES_ROOT/books/1/images/01_第1卷"
SOURCE_IMAGE="$(ls "$ROOT"/asset/*/images/01_第1卷/007.jpg 2>/dev/null | head -1)"
[ -n "$SOURCE_IMAGE" ] || die "仓库内找不到语料插图 asset/*/images/01_第1卷/007.jpg"
cp "$SOURCE_IMAGE" "$IMAGES_ROOT/books/1/images/01_第1卷/007.jpg"
# 目录穿越的诱饵：防护失效时它会被读出来，断言据此判失败。
printf 'omniread-e2e-secret-should-never-be-served\n' > "$IMAGES_ROOT/secret.txt"
rm -f "$PROGRESS_FILE"

[ -f "$JAR" ] || {
  log "Java jar 不存在，先构建"
  mvn -q -f "$ROOT/services/backend/pom.xml" -DskipTests package || die "Maven 构建失败"
}

# ---------- 服务起停 ----------
start_python() { # fault(none|provider_error|timeout)
  local fault="$1" label="${1//_/-}"
  PYTHON_LOG="$RUN_DIR/logs/rag-$label.log"
  log "起 Python RAG（假的 answer/retrieval provider，fault=$fault）"
  (
    cd "$ROOT" && exec env \
      PYTHONUTF8=1 \
      POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
      OMNIREAD_IMAGE_STORAGE_BACKEND=local \
      OMNIREAD_IMAGE_LOCAL_ROOT="$IMAGES_ROOT" \
      OMNIREAD_ANSWER_PROVIDER=fake \
      OMNIREAD_RETRIEVAL_PROVIDER=fake \
      OMNIREAD_FAKE_ANSWER_FAULT="$fault" \
      OMNIREAD_FAKE_ANSWER_DELAY_MS="$STREAM_DELAY_MS" \
      OMNIREAD_LOG_LEVEL=INFO \
      "$UV" run --directory "$RAG_PY_DIR" python -m uvicorn \
        omniread.api.app:create_app --factory --host 127.0.0.1 --port 8000
  ) > "$PYTHON_LOG" 2>&1 &
  echo $! > "$RUN_DIR/logs/rag.pid"
  wait_http "Python RAG" "http://127.0.0.1:8000/internal/v1/health" 60 \
    || { tail -30 "$PYTHON_LOG" >&2; die "Python RAG 未在 60s 内就绪，看 $PYTHON_LOG"; }
}

stop_python() {
  stop_port 8000
  sleep 1
}

start_java() {
  log "起 Java 网关"
  (
    cd "$ROOT" && exec env \
      OMNIREAD_RAG_BASE_URL="http://127.0.0.1:8000" \
      OMNIREAD_WEB_DIST="web/dist" \
      OMNIREAD_PROGRESS_FILE="$PROGRESS_FILE" \
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
  if PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
     "$UV" run --directory "$RAG_PY_DIR" python "$ROOT/scripts/verify_gateway.py" \
      --phase "$phase" --progress-file "$PROGRESS_FILE" --python-log "$PYTHON_LOG" \
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
