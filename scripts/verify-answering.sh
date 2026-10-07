#!/usr/bin/env bash
# M0-5 回答链验证入口：检索 → 装配 → prompt → 流式生成 → 引用 → JSON / SSE 适配器。
#
# 验收对应（M0-03 §2 M0-5）：GLM adapter、拒答、JSON 与 SSE 两个适配器可用。
# 默认全程用假 provider，直接从仓库内语料分块，不发真实调用、不连库；
# 细节与逐项断言在 scripts/verify_answering.py。
#
# 用法（Git Bash，仓库根执行）：
#   bash scripts/verify-answering.sh
#   bash scripts/verify-answering.sh --book-id 1
#   # 真实回答模型（需用户明确批准，凭据经 keymgr 注入）：
#   keymgr run omniread bash scripts/verify-answering.sh --real
#   bash scripts/verify-answering.sh --help
#
# 前置：只读仓库内 asset/ 语料，不需要 PostgreSQL / MinIO；--real 额外需要 GLM_API_KEY。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"

case "${1:-}" in
  -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
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

exec "$UV" run --directory "$RAG_DIR" python "$ROOT/scripts/verify_answering.py" "$@"
