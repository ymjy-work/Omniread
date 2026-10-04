#!/usr/bin/env bash
# Omniread M0 可复现验证序列：把四个产物（Java / Python / infra / web）的构建与检查串成一条命令。
#
# 用法（Git Bash，仓库根执行）：
#   bash scripts/verify-all.sh                默认跑第 1–5、8、9、11、12 步（共 9 步）
#   bash scripts/verify-all.sh --skip-web     跳过第 5 步（没装 node 时）
#   bash scripts/verify-all.sh --smoke        跑完后再起一次全栈并 curl 端到端，最后自动停掉
#   bash scripts/verify-all.sh --data-layer   追加第 7 步：真连 PG / MinIO 跑迁移往返与对象读写
#   bash scripts/verify-all.sh --gateway      追加第 10 步：起 Java + Python 跑 M0-6 网关联调
#   bash scripts/verify-all.sh --ci           公开 CI 用：跳过依赖 asset/ 的三步（8、9、11），
#                                             语料不入库，远端跑不了那三步
#
# 每步失败都会打印「看哪里」。默认不写任何凭据；只有 --smoke 且未加 --local-images 时
# 才会因 compose 的必填插值需要凭据（注入方式见 scripts/dev-up.sh --help）；
# --data-layer 需要已起的 infra 与注入的 POSTGRES_PASSWORD / MINIO_SECRET_KEY；
# --gateway 需要已起的 PostgreSQL 与 POSTGRES_PASSWORD，自己起停 Java / Python（假 provider）。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/temp/run"
SKIP_WEB=0
SMOKE=0
DATA_LAYER=0
GATEWAY=0
CI=0
for arg in "$@"; do
  case "$arg" in
    --skip-web) SKIP_WEB=1 ;;
    --smoke) SMOKE=1 ;;
    --data-layer) DATA_LAYER=1 ;;
    --gateway) GATEWAY=1 ;;
    --ci) CI=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

find_uv() {
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  local p="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  [ -x "$p" ] && { echo "$p"; return; }
  echo "找不到 uv" >&2; exit 1
}
UV="$(find_uv)"

PASS=0
FAIL=0
step() { printf '\n=== [%s] %s ===\n' "$1" "$2"; }
ok()   { printf '  OK   %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  FAIL %s\n      看这里：%s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
run()  { # 名称 排查提示 命令...
  local name="$1" hint="$2"; shift 2
  if "$@"; then ok "$name"; else bad "$name" "$hint"; fi
}

step 1 "infra/docker：compose 配置校验（不启容器）"
# 仅校验语法与必填插值，用占位值即可；这一步不创建任何容器，也不会写文件。
if POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-__verify__}" \
   MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-__verify__}" \
   docker compose -f "$ROOT/infra/docker/docker-compose.yml" config --quiet; then
  ok "compose config"
else
  bad "compose config" "infra/docker/docker-compose.yml；或读 infra/docker/README.md 的排错一节"
fi

step 2 "services/rag：依赖同步 + pytest + ruff + mypy"
run "uv sync --all-groups" "services/rag/pyproject.toml；uv.lock 与依赖冲突看 uv 输出" \
  "$UV" sync --all-groups --directory "$ROOT/services/rag"
run "pytest" "services/rag/tests/；失败用例名直接对应 tests 下的文件" \
  "$UV" run --directory "$ROOT/services/rag" pytest
run "ruff check" "services/rag/src 与 tests；按 ruff 输出行号定位" \
  "$UV" run --directory "$ROOT/services/rag" ruff check
run "mypy" "services/rag/src；mypy 报的模块名对应 src/omniread 下的文件" \
  "$UV" run --directory "$ROOT/services/rag" mypy

step 3 "services/backend：Maven 单元测试"
run "mvn test" "services/backend/target/surefire-reports/；编译错误看 mvn 输出首个 ERROR" \
  mvn -q -f "$ROOT/services/backend/pom.xml" test

step 4 "services/backend：可执行 fat jar"
run "mvn -DskipTests package" "同上；产物在 services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar" \
  mvn -q -f "$ROOT/services/backend/pom.xml" -DskipTests package

if [ "$SKIP_WEB" -eq 1 ]; then
  step 5 "web：按 --skip-web 跳过"
else
  step 5 "web：lint + 类型检查 + 生产构建"
  if [ ! -d "$ROOT/web/node_modules" ]; then
    run "npm install" "web/package.json、web/package-lock.json" \
      npm --prefix "$ROOT/web" install --no-audit --no-fund
  fi
  run "eslint" "web/src；报错按文件:行号定位" \
    npm --prefix "$ROOT/web" run lint
  run "vue-tsc --noEmit" "web/src；报错按文件:行号定位" \
    npm --prefix "$ROOT/web" run typecheck
  run "vite build" "web/vite.config.ts；产物在 web/dist，由 Java 托管" \
    npm --prefix "$ROOT/web" run build
fi

if [ "$SMOKE" -eq 1 ]; then
  step 6 "端到端 smoke：起全栈 → curl → 停"
  # 本地图片后端 + 复用已起 infra，可免凭据；此模式不注入数据库凭据、没有数据，
  # 只断言 API 形状（books 空列表也算通过）；要真实数据需注入凭据（见 dev-up.sh --help）。
  if bash "$ROOT/scripts/dev-up.sh" --no-infra --local-images; then
    sleep 1
    echo "  --- 探活 ---"
    curl -s -o /dev/null -w '  GET /api/v1/health -> %{http_code}\n' http://127.0.0.1:8080/api/v1/health
    curl -s -o /dev/null -w '  GET /api/v1/books  -> %{http_code}\n' http://127.0.0.1:8080/api/v1/books
    curl -s -o /dev/null -w '  GET /internal/v1/health -> %{http_code}\n' http://127.0.0.1:8000/internal/v1/health
    bash "$ROOT/scripts/dev-down.sh"
    ok "smoke（断言：health=200 / books=200 / 内部 health=200）"
  else
    bad "smoke" "temp/run/rag.log 与 temp/run/backend.log；起不来的常见原因是端口被占（加 --force）"
  fi
else
  step 6 "端到端 smoke：未启用（加 --smoke 才会起服务）"
fi

if [ "$DATA_LAYER" -eq 1 ]; then
  step 7 "M0-2 数据层：真连 PG / MinIO 跑迁移往返 + 对象读写"
  # 真实基础设施验证，默认不启用：它要求 infra 已起且凭据已注入，比默认那 7 步慢得多。
  if bash "$ROOT/scripts/verify-data-layer.sh"; then
    ok "data-layer"
  else
    bad "data-layer" "先 bash scripts/dev-up.sh 起 infra，再注入 POSTGRES_PASSWORD / MINIO_SECRET_KEY 重跑"
  fi
else
  step 7 "M0-2 数据层：未启用（加 --data-layer 才跑；会真连 PG 55432 / MinIO 9100）"
fi

# 第 8、9 步默认启用：两者都走语料直读 + 假 provider，不连库、不发真实调用，因此不需要凭据。
# 它们把 M0-4 / M0-5 的冒烟纳入项目级校验。
if [ "$CI" -eq 1 ]; then
  step 8 "M0-4 检索链：跳过（--ci；语料不入库，远端没有 asset/）"
  step 9 "M0-5 回答链：跳过（--ci；verify-answering 要读语料）"
else
  step 8 "M0-4 检索链：语料直读 + 假 embedding（不连库）"
  if bash "$ROOT/scripts/verify-retrieval.sh" --source corpus; then
    ok "retrieval-smoke"
  else
    bad "retrieval-smoke" "bash scripts/verify-retrieval.sh --source corpus 看详情"
  fi

  step 9 "M0-5 回答链：假 provider 跑通事件流与两个适配器"
  if bash "$ROOT/scripts/verify-answering.sh"; then
    ok "answering-smoke"
  else
    bad "answering-smoke" "bash scripts/verify-answering.sh 看详情"
  fi
fi

# 第 10 步可选：要起真实 Java + Python（假 provider）且真连 PG，比默认那 7 步慢得多，
# 因此默认不跑；它自己起停服务，失败时打印可操作提示，结束不留孤儿进程。
if [ "$GATEWAY" -eq 1 ]; then
  step 10 "M0-6 Java 网关联调：Client → Java → Python 端到端"
  if bash "$ROOT/scripts/verify-gateway.sh"; then
    ok "gateway-e2e"
  else
    bad "gateway-e2e" "bash scripts/verify-gateway.sh 看详情；需要 POSTGRES_PASSWORD 与已起的 PostgreSQL"
  fi
else
  step 10 "M0-6 Java 网关联调：未启用（加 --gateway 才跑；需 POSTGRES_PASSWORD 与已起的 PostgreSQL）"
fi

# 第 11、12 步默认启用：两者都走语料直读 + 假 provider，不连库、不发真实调用。
# 它们把 M0-7b 的映射链与 eval/ 产物的入库红线纳入项目级校验。
if [ "$CI" -eq 1 ]; then
  step 11 "M0-7b 映射链：跳过（--ci；要读 asset/ 语料）"
else
  step 11 "M0-7b 映射链：语料直读 + 假 provider 兜底（不连库、不发真实调用）"
  if bash "$ROOT/scripts/verify-mapping.sh"; then
    ok "mapping-smoke"
  else
    bad "mapping-smoke" "bash scripts/verify-mapping.sh 看详情；语料需在 asset/ 下"
  fi
fi

step 12 "eval/ 产物红线：文件白名单 + 字段长度 + 与语料比对"
if bash "$ROOT/scripts/verify-artifacts.sh"; then
  ok "artifact-redline"
else
  bad "artifact-redline" "bash scripts/verify-artifacts.sh 看详情；eval/ 进 git，夹带正文只能重写历史"
fi

printf '\n=== 汇总：%d 项通过，%d 项失败 ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
