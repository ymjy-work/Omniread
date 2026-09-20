#!/usr/bin/env bash
# M0-3 导入入口：读语料 index.jsonl，写 books/volumes/chapters/chunks，回填 prev/next。
#
# 幂等：同一份语料重跑不产生重复行（单事务内整批替换该书的行）。
# 可重复执行，语料只按行读、不拷贝进任何入库路径。
#
# 用法（Git Bash，仓库根执行）：
#   keymgr run omniread bash scripts/import-corpus.sh           # 默认语料，先跑迁移
#   bash scripts/import-corpus.sh --no-migrate                  # 迁移已跑过时
#   bash scripts/import-corpus.sh --corpus-root "<dir>" --book-id 1
#   bash scripts/import-corpus.sh --help
#
# 凭据只从环境变量读：POSTGRES_PASSWORD 供连库，不写文件、不打印（M0-00 §6）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"
DEFAULT_CORPUS_ROOT="$ROOT/asset/《不时轻声地以俄语遮羞的邻座艾莉同学》"

CORPUS_ROOT="$DEFAULT_CORPUS_ROOT"
BOOK_ID=1
CORPUS_VERSION=""
RUN_MIGRATIONS=1

usage() { sed -n '2,16p' "$0"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --corpus-root) CORPUS_ROOT="$2"; shift 2 ;;
    --book-id) BOOK_ID="$2"; shift 2 ;;
    --corpus-version) CORPUS_VERSION="$2"; shift 2 ;;
    --no-migrate) RUN_MIGRATIONS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

# uv 不在 PATH 上时用 WinGet 安装目录下的绝对路径（与 dev-up.sh / verify-data-layer.sh 一致）。
find_uv() {
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  local p="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  [ -x "$p" ] && { echo "$p"; return; }
  echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2; exit 2
}

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  cat >&2 <<'EOF'
失败：POSTGRES_PASSWORD 未注入，导入连不上库（凭据只从环境变量读）。
      注入方式：keymgr run omniread bash scripts/import-corpus.sh
      或先在当前 shell 导出 POSTGRES_PASSWORD 再重跑。
EOF
  exit 2
fi

if [ ! -f "$CORPUS_ROOT/index.jsonl" ]; then
  echo "失败：语料根目录里没有 index.jsonl：$CORPUS_ROOT" >&2
  exit 2
fi

export POSTGRES_PASSWORD
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-55432}"
export POSTGRES_DB="${POSTGRES_DB:-omniread}"
export POSTGRES_USER="${POSTGRES_USER:-omniread}"
# Windows 控制台默认不是 UTF-8，Python 子进程统一按 UTF-8 输出，避免中文变乱码。
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

UV="$(find_uv)"

if [ "$RUN_MIGRATIONS" -eq 1 ]; then
  echo "[import] alembic upgrade head"
  "$UV" run --directory "$RAG_DIR" alembic upgrade head
fi

echo "[import] 语料：$CORPUS_ROOT（book_id=$BOOK_ID）"
ARGS=(--corpus-root "$CORPUS_ROOT" --book-id "$BOOK_ID")
[ -n "$CORPUS_VERSION" ] && ARGS+=(--corpus-version "$CORPUS_VERSION")
"$UV" run --directory "$RAG_DIR" python -m omniread.pipelines.importing "${ARGS[@]}"
