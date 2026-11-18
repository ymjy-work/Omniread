#!/usr/bin/env bash
# Omniread M0 一键启动（在 Git Bash 里执行）。
#
# 启动顺序：基础设施（PostgreSQL + MinIO）→ Python RAG（127.0.0.1:8000）→ Java 网关（127.0.0.1:8080）。
# 前端构建产物由 Java 托管，因此默认不起前端；需要热更新时加 --web 另起 Vite dev server（5173）。
#
# 用法：
#   bash scripts/dev-up.sh                 起 infra + Python + Java
#   bash scripts/dev-up.sh --no-infra      复用已经在跑的 infra
#   bash scripts/dev-up.sh --local-images  Python 用本地图片目录（temp/images），不连 MinIO
#   bash scripts/dev-up.sh --web           额外起前端 dev server
#   bash scripts/dev-up.sh --force         端口被占时先结束占用进程再起
#   bash scripts/dev-up.sh --build         强制重新构建 Java jar
#
# 凭据只从环境变量读：不写文件、不打印（M0-00 §6）。
# 缺凭据时若 keymgr 存在 omniread profile，则自动 `keymgr run omniread` 重入本脚本；
# 没有该 profile 时打印一次性配置方法后退出。配 --no-infra --local-images 可完全免凭据启动。
#
# 端口固定为 Python 8000 / Java 8080 / PG 55432 / MinIO 9100-9101，与以下位置一致：
#   services/backend/src/main/resources/application.yml、web/vite.config.ts
#   services/rag/src/omniread/config.py、infra/docker/docker-compose.yml
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/temp/run"
JAR="$ROOT/services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar"
RAG_PY="$ROOT/services/rag/.venv/Scripts/python.exe"
COMPOSE_FILE="$ROOT/infra/docker/docker-compose.yml"
PROFILES_JSON="${USERPROFILE:-$HOME}/.config/keymgr/profiles.json"
KEYMGR_PROFILE="${OMNIREAD_KEYMGR_PROFILE:-omniread}"

START_INFRA=1
LOCAL_IMAGES=0
START_WEB=0
FORCE=0
REBUILD=0

for arg in "$@"; do
  case "$arg" in
    --no-infra) START_INFRA=0 ;;
    --local-images) LOCAL_IMAGES=1 ;;
    --web) START_WEB=1 ;;
    --force) FORCE=1 ;;
    --build) REBUILD=1 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

log()  { printf '[dev-up] %s\n' "$*"; }
die()  { printf '[dev-up] 失败：%s\n' "$*" >&2; exit 1; }

# uv 不在本机 PATH 上时用 WinGet 安装目录下的绝对路径。
find_uv() {
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  local p="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  [ -x "$p" ] && { echo "$p"; return; }
  die "找不到 uv。装好 uv 或把 uv 加进 PATH 后重试。"
}

# 端口是否被占用。netstat 列出的是宿主端口。
port_busy() {
  netstat -ano 2>/dev/null | grep -E "[:.]$1[[:space:]]+" | grep -q LISTENING
}

# 按端口结束占用进程（Windows 路径：taskkill）。
stop_port() {
  local port="$1" pids p
  pids="$(netstat -ano 2>/dev/null | grep -E "[:.]$port[[:space:]]+" | grep LISTENING | awk '{print $NF}' | sort -u)"
  [ -z "$pids" ] && return 0
  for p in $pids; do
    log "结束占用端口 $port 的进程 PID=$p"
    taskkill //F //T //PID "$p" >/dev/null 2>&1 || kill "$p" 2>/dev/null || true
  done
  sleep 1
}

# 确保端口可用：被占且带了 --force 就清掉，否则报错退出。
require_port() {
  local port="$1" who="$2"
  port_busy "$port" || return 0
  if [ "$FORCE" -eq 1 ]; then
    stop_port "$port"
    port_busy "$port" && die "$who 的端口 $port 仍被占用"
  else
    die "$who 的端口 $port 已被占用（换端口或加 --force 结束占用进程）"
  fi
}

profile_exists() {
  [ -f "$PROFILES_JSON" ] && grep -q "\"$1\"" "$PROFILES_JSON"
}

# 凭据缺失时：有 keymgr profile 就用它重入，否则给出配置方法退出。
ensure_creds() {
  local need=() dedup=() v missing=()
  [ "$START_INFRA" -eq 1 ] && need+=(POSTGRES_PASSWORD MINIO_SECRET_KEY)
  [ "$LOCAL_IMAGES" -eq 0 ] && need+=(MINIO_SECRET_KEY)
  for v in "${need[@]}"; do
    case " ${dedup[*]-} " in *" $v "*) ;; *) dedup+=("$v") ;; esac
  done
  for v in "${dedup[@]}"; do [ -n "${!v:-}" ] || missing+=("$v"); done
  [ "${#missing[@]}" -eq 0 ] && return 0

  log "缺少环境变量：${missing[*]}"
  if [ "${OMNIREAD_KEYMGR_REEXEC:-0}" != "1" ] && profile_exists "$KEYMGR_PROFILE"; then
    log "检测到 keymgr profile '$KEYMGR_PROFILE'，用它注入凭据后重入本脚本"
    export OMNIREAD_KEYMGR_REEXEC=1
    exec keymgr run "$KEYMGR_PROFILE" bash "$0" "$@"
  fi
  cat >&2 <<EOF

凭据未注入，且没有可用的 keymgr profile。任选一种：

  A. 配置一次性 keymgr profile（推荐，之后每次启动都不用再管）
     1) 为 PostgreSQL 口令建一个条目（M0-01 §5.2 的映射表尚未登记它）：
          keymgr set omniread-pg
     2) 把 scripts/keymgr-profile.example.json 里的 "omniread" 段合并进
        %USERPROFILE%\\.config\\keymgr\\profiles.json
     3) 重新执行本脚本即可。

  B. 免凭据起最简链路（Python 用本地图片目录，且不起 infra）：
          bash scripts/dev-up.sh --no-infra --local-images

  说明：凭据只经 keymgr 注入进程环境，不写进任何文件（M0-00 §6）。
EOF
  exit 2
}

wait_container() { # name timeout_seconds
  local name="$1" timeout="${2:-90}" i=0 status
  while [ "$i" -lt $((timeout * 2)) ]; do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
    [ "$status" = "healthy" ] && { log "$name 就绪（healthy）"; return 0; }
    sleep 0.5; i=$((i + 1))
  done
  return 1
}

wait_http() { # label url timeout_seconds
  local label="$1" url="$2" timeout="${3:-90}" i=0
  while [ "$i" -lt $((timeout * 2)) ]; do
    curl -sf -o /dev/null --max-time 2 "$url" && { log "$label 就绪：$url"; return 0; }
    sleep 0.5; i=$((i + 1))
  done
  return 1
}

# 后台起进程：日志写 temp/run/<name>.log，PID 写 temp/run/<name>.pid。
# 用 ( cd ... && exec env ... ) 让记录到的 PID 就是服务本身，便于 dev-down 收尾。
spawn() { # name cwd logfile pidfile cmd...
  local name="$1" cwd="$2" logfile="$3" pidfile="$4"; shift 4
  ( cd "$cwd" && exec "$@" ) >"$logfile" 2>&1 &
  echo $! >"$pidfile"
  log "已启动 $name（PID $(cat "$pidfile")，日志 $logfile）"
}

mkdir -p "$RUN_DIR"
ensure_creds

# ---------- 1. 基础设施 ----------
if [ "$START_INFRA" -eq 1 ]; then
  log "启动基础设施（PostgreSQL 55432 / MinIO 9100-9101）"
  docker compose -f "$COMPOSE_FILE" up -d || die "docker compose up 失败，先看上方 compose 输出"
  wait_container omniread-postgres 90 || die "omniread-postgres 未在 90s 内 healthy；看 docker logs omniread-postgres"
  wait_container omniread-minio 90 || die "omniread-minio 未在 90s 内 healthy；看 docker logs omniread-minio"
else
  log "按 --no-infra 跳过基础设施，直接复用已起的容器"
fi

# ---------- 2. Python RAG（8000） ----------
require_port 8000 "Python RAG"
UV="$(find_uv)"
if [ ! -x "$RAG_PY" ]; then
  log "services/rag/.venv 不存在，先 uv sync --all-groups"
  "$UV" sync --all-groups --directory "$ROOT/services/rag" || die "uv sync 失败，看上方 uv 输出"
fi

RAG_ENV=(OMNIREAD_LOG_LEVEL=INFO)
if [ "$LOCAL_IMAGES" -eq 1 ]; then
  # 本地图片目录：不读 MinIO 凭据，目录固定放在被 git 忽略的 temp/ 下
  RAG_ENV+=(OMNIREAD_IMAGE_STORAGE_BACKEND=local "OMNIREAD_IMAGE_LOCAL_ROOT=$ROOT/temp/images")
  log "Python 图片后端=local（$ROOT/temp/images），不连 MinIO"
else
  # 端点 / access key / 桶名与 infra/docker 对齐：MinIO 宿主 9100，access key MinIO-Omniread。
  # 桶名显式传，把约定钉在脚本上：config.py 的默认值与 infra 的 minio-init 建桶都已是
  # omniread-sources（M0-02 §4），显式传是为了不依赖配置默认值。
  RAG_ENV+=(
    OMNIREAD_IMAGE_STORAGE_BACKEND=minio
    OMNIREAD_MINIO_ENDPOINT=127.0.0.1:9100
    OMNIREAD_MINIO_BUCKET=omniread-sources
    OMNIREAD_MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-MinIO-Omniread}"
    "OMNIREAD_MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-}"
  )
fi
spawn "Python RAG" "$ROOT" "$RUN_DIR/rag.log" "$RUN_DIR/rag.pid" \
  env "${RAG_ENV[@]}" "$RAG_PY" -m uvicorn omniread.api.app:create_app --factory --host 127.0.0.1 --port 8000
wait_http "Python RAG" "http://127.0.0.1:8000/internal/v1/health" 60 \
  || die "Python RAG 未在 60s 内就绪，看 $RUN_DIR/rag.log"

# ---------- 3. Java 网关（8080） ----------
require_port 8080 "Java 网关"
if [ "$REBUILD" -eq 1 ] || [ ! -f "$JAR" ]; then
  log "构建 Java jar（mvn -DskipTests package）"
  mvn -q -f "$ROOT/services/backend/pom.xml" -DskipTests package || die "Maven 构建失败，看上方 mvn 输出"
fi
if [ ! -d "$ROOT/web/dist" ]; then
  log "警告：web/dist 不存在，Java 将只托管 API，不托管前端页面"
fi
spawn "Java 网关" "$ROOT" "$RUN_DIR/backend.log" "$RUN_DIR/backend.pid" \
  env OMNIREAD_RAG_BASE_URL=http://127.0.0.1:8000 OMNIREAD_WEB_DIST=web/dist \
  java -jar "$JAR"
wait_http "Java 网关" "http://127.0.0.1:8080/api/v1/health" 60 \
  || die "Java 网关未在 60s 内就绪，看 $RUN_DIR/backend.log"

# ---------- 4. 前端 dev server（可选） ----------
if [ "$START_WEB" -eq 1 ]; then
  require_port 5173 "前端 dev server"
  [ -d "$ROOT/web/node_modules" ] || { log "web/node_modules 不存在，先 npm install"; ( cd "$ROOT/web" && npm install --no-audit --no-fund ) || die "npm install 失败"; }
  spawn "前端 dev server" "$ROOT/web" "$RUN_DIR/web.log" "$RUN_DIR/web.pid" npm run dev
  wait_http "前端 dev server" "http://localhost:5173/" 60 \
    || die "前端 dev server 未在 60s 内就绪，看 $RUN_DIR/web.log"
fi

# ---------- 5. 汇总 ----------
cat <<EOF

Omniread 已就绪：
  Java 网关      http://127.0.0.1:8080          （前端页面与 /api/v1 同源）
  Python RAG     http://127.0.0.1:8000/internal/v1/health
  自检           curl -s http://127.0.0.1:8080/api/v1/health
EOF
[ "$START_INFRA" -eq 1 ] && cat <<EOF
  PostgreSQL     postgresql://omniread@localhost:55432/omniread
  MinIO S3 API   http://localhost:9100     控制台 http://localhost:9101
EOF
[ "$START_WEB" -eq 1 ] && echo "  前端（Vite）   http://localhost:5173"
cat <<EOF

日志在 temp/run/ 下；停止用 bash scripts/dev-down.sh。
注意：M0-1 未导入语料，GET /api/v1/books 返回空列表，问答路径会因 book_id 不存在返回 400 RAG_INVALID_REALM；
检索链本身也尚未实现（Python 侧返回 503 RAG_UNAVAILABLE）。
EOF
