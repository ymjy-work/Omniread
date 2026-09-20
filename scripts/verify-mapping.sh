#!/usr/bin/env bash
# M0-7b 映射链验证入口：确定性区间映射 + 兜底路径 smoke + 产物红线，全程不发真实 API 调用。
#
# 验收对应（M0-03 §2 M0-7b）：evidence→chunk 映射完成且抽样复核可用、数据集 hash 可冻结。
# 细节与逐项断言在 scripts/verify_mapping.py。
#
# 用法（Git Bash，仓库根执行，**不需要任何凭据**）：
#   bash scripts/verify-mapping.sh
#   bash scripts/verify-mapping.sh --help
#
# 本脚本走语料直读（不连库）：区间的还原函数与库模式共用，差别只在数据取自哪里。
# 要验真库冻结的那份切片，用 python scripts/run_mapping.py --source db（需 POSTGRES_PASSWORD）。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"

case "${1:-}" in
  -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
esac

if [ ! -d "$ROOT/asset/《不时轻声地以俄语遮羞的邻座艾莉同学》" ]; then
  cat >&2 <<'EOF'
失败：读不到仓库内语料（asset/ 不入 git）。
      本验证要拿真实语料还原 chunk 区间；换机器需先把语料放回 asset/ 下。
EOF
  exit 2
fi

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

exec "$UV" run --directory "$RAG_DIR" python "$ROOT/scripts/verify_mapping.py" "$@"
