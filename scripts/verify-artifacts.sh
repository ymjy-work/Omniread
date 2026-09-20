#!/usr/bin/env bash
# eval/ 产物入库红线扫描入口：文件白名单 + 字符串长度上限 + 与语料比对。
#
# 为什么单独一条：eval/ 进 git，一段正文一旦 push 就只能重写历史。
# 规格要求「CI 检查 JSONL 内任一字符串字段长度上限 500 字符」，本脚本是它的实现载体。
#
# 用法（Git Bash，仓库根执行，**不需要任何凭据**）：
#   bash scripts/verify-artifacts.sh
#   bash scripts/verify-artifacts.sh --min-overlap 40
#   bash scripts/verify-artifacts.sh --help
#
# 没有仓库内语料时（公共 CI）只跳过「与语料比对」这一条并显式说明，不静默当作通过。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"

case "${1:-}" in
  -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
esac

# Windows 控制台默认不是 UTF-8，Python 子进程统一按 UTF-8 输出，避免中文提示变乱码。
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

if command -v uv >/dev/null 2>&1; then
  UV="uv"
else
  UV="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  if [ ! -x "$UV" ]; then
    echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2
    exit 2
  fi
fi

exec "$UV" run --directory "$RAG_DIR" python "$ROOT/scripts/verify_artifacts.py" "$@"
