#!/usr/bin/env bash
# M0-4 检索链验证入口：真库语料 + 假 provider，全程不发真实 API 调用。
#
# 验收对应（M0-03 §2 M0-4）：dense / BM25 / RRF / rerank / 装配 cap / leak；
# full 与 past 下 in-realm 排名同源；迭代索引扫描的会话 GUC 已启用。
# 细节与逐项断言在 scripts/verify_retrieval.py。
#
# 用法（Git Bash，仓库根执行，凭据只从环境变量读）：
#   keymgr run omniread bash scripts/verify-retrieval.sh
#   bash scripts/verify-retrieval.sh --progress 120 --book-id 1
#   bash scripts/verify-retrieval.sh --source corpus    # 无库凭据：直接从仓库内语料分块
#   bash scripts/verify-retrieval.sh --help
#
# 前置：--source db（默认）需 PostgreSQL 已起（bash scripts/dev-up.sh）且语料已导入；
#       --source corpus 不需要库与凭据，但不校验 dense 的 SQL 过滤与 NULL 统计。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"
PG_CONTAINER="omniread-postgres"

case "${1:-}" in
  -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
esac

# corpus 模式不连库：跳过凭据与容器前置检查。
SOURCE_MODE=db
for arg in "$@"; do
  [ "$arg" = "corpus" ] && SOURCE_MODE=corpus
done

if [ "$SOURCE_MODE" = "db" ]; then
  if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    cat >&2 <<'EOF'
失败：POSTGRES_PASSWORD 未注入，验证连不上库（凭据只从环境变量读）。
      注入方式：keymgr run omniread bash scripts/verify-retrieval.sh
      或先在当前 shell 导出 POSTGRES_PASSWORD；也可加 --source corpus 免库跑。
EOF
    exit 2
  fi

  if ! docker inspect --format '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true; then
    echo "失败：PostgreSQL 容器 $PG_CONTAINER 没在运行，先跑 bash scripts/dev-up.sh" >&2
    exit 2
  fi
fi

if [ "$SOURCE_MODE" = "db" ]; then
  export POSTGRES_PASSWORD
  export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
  export POSTGRES_PORT="${POSTGRES_PORT:-55432}"
  export POSTGRES_DB="${POSTGRES_DB:-omniread}"
  export POSTGRES_USER="${POSTGRES_USER:-omniread}"
fi
# Windows 控制台默认不是 UTF-8，Python 子进程统一按 UTF-8 输出，避免中文提示变乱码。
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
# DASHSCOPE_API_KEY 不被本脚本读取：embedding / rerank 全部走假 provider。

if command -v uv >/dev/null 2>&1; then
  UV="uv"
else
  UV="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  if [ ! -x "$UV" ]; then
    echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2
    exit 2
  fi
fi

exec "$UV" run --directory "$RAG_DIR" python "$ROOT/scripts/verify_retrieval.py" "$@"
