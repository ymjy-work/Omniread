#!/usr/bin/env bash
# M0-3 导入后确定性抽检（真连 PostgreSQL 55432，不属于日常快速校验）。
#
# 抽检项（对应 M0-03 §2 M0-3 验收）：
#   1 chunk 总数与每章 chunk 数的最小 / 中位 / 最大值；
#   2 无跨章：prev/next 不得指向别的章，也不得有悬空指针；
#   3 prev/next 闭环：各章首块沿 next 走到末块、反向走回，长度等于该章 chunk 数；
#   4 token_count 抽查：count(content) == token_count，且全表 ≤ 600；
#   5 幂等：再导入一次，行数与 chunk_key 集合不变。
#
# 用法（Git Bash，仓库根执行）：
#   keymgr run omniread bash scripts/verify-import.sh
#   bash scripts/verify-import.sh --skip-reimport        # 只跑 1–4，不改库
#   bash scripts/verify-import.sh --corpus-root "<dir>" --book-id 1
#   bash scripts/verify-import.sh --help
#
# 凭据只从环境变量读：POSTGRES_PASSWORD 供连库，不写文件、不打印（M0-00 §6）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAG_DIR="$ROOT/services/rag"
PG_CONTAINER="omniread-postgres"
PG_USER="${POSTGRES_USER:-omniread}"
PG_DB="${POSTGRES_DB:-omniread}"
DEFAULT_CORPUS_ROOT="$ROOT/asset/《不时轻声地以俄语遮羞的邻座艾莉同学》"

COUNTS=("books" "volumes" "chapters" "chunks")

CORPUS_ROOT="$DEFAULT_CORPUS_ROOT"
BOOK_ID=1
SKIP_REIMPORT=0

usage() { sed -n '2,19p' "$0"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --corpus-root) CORPUS_ROOT="$2"; shift 2 ;;
    --book-id) BOOK_ID="$2"; shift 2 ;;
    --skip-reimport) SKIP_REIMPORT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

find_uv() {
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  local p="$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  [ -x "$p" ] && { echo "$p"; return; }
  echo "找不到 uv：装好 uv 或把 uv 加进 PATH 后重试" >&2; exit 2
}

psql_t() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "$1"; }

PASS=0
FAIL=0
step()      { printf '\n=== %s ===\n' "$1"; }
ok()        { printf '  OK   %s\n' "$1"; PASS=$((PASS + 1)); }
bad()       { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
check_eq()  { # label expected actual
  if [ "$2" = "$3" ]; then ok "$1 = $3"; else bad "$1：期望 $2，实际 $3"; fi
}
check_zero() { # label actual
  if [ "$2" = "0" ]; then ok "$1 = 0"; else bad "$1：期望 0，实际 $2"; fi
}

# ---------- 0 前置条件 ----------
step "0 前置条件"
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  echo "  失败：POSTGRES_PASSWORD 未注入。注入方式：keymgr run omniread bash scripts/verify-import.sh" >&2
  exit 2
fi
docker inspect --format '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true \
  || { echo "  失败：容器 $PG_CONTAINER 没在运行，先跑 bash scripts/dev-up.sh" >&2; exit 2; }
ok "PostgreSQL 容器在运行（$PG_CONTAINER）"

export POSTGRES_PASSWORD
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-55432}"
export POSTGRES_DB="$PG_DB"
export POSTGRES_USER="$PG_USER"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
UV="$(find_uv)"

# ---------- 1 行数与每章 chunk 数 ----------
step "1 行数与每章 chunk 数"
for table in "${COUNTS[@]}"; do
  ok "$table 行数 = $(psql_t "SELECT count(*) FROM $table;")"
done

STATS="$(psql_t "SELECT min(c) || '|' || percentile_disc(0.5) WITHIN GROUP (ORDER BY c) || '|' || max(c) FROM (SELECT count(*) AS c FROM chunks GROUP BY chapter_id) s;")"
IFS='|' read -r CH_MIN CH_MED CH_MAX <<<"$STATS"
ok "每章 chunk 数：min=$CH_MIN  中位=$CH_MED  max=$CH_MAX"
check_eq "章数" "$(psql_t "SELECT count(*) FROM chapters;")" "$(psql_t "SELECT count(DISTINCT chapter_id) FROM chunks;")"

# ---------- 2 无跨章 + 无悬空指针 ----------
step "2 无跨章 / 无悬空指针"
check_zero "next 指向别章的 chunk 数" \
  "$(psql_t "SELECT count(*) FROM chunks c JOIN chunks n ON n.chunk_key = c.next_chunk_key WHERE n.chapter_id <> c.chapter_id;")"
check_zero "prev 指向别章的 chunk 数" \
  "$(psql_t "SELECT count(*) FROM chunks c JOIN chunks p ON p.chunk_key = c.prev_chunk_key WHERE p.chapter_id <> c.chapter_id;")"
check_zero "next_chunk_key 悬空数" \
  "$(psql_t "SELECT count(*) FROM chunks c WHERE c.next_chunk_key IS NOT NULL AND NOT EXISTS (SELECT 1 FROM chunks n WHERE n.chunk_key = c.next_chunk_key);")"
check_zero "prev_chunk_key 悬空数" \
  "$(psql_t "SELECT count(*) FROM chunks c WHERE c.prev_chunk_key IS NOT NULL AND NOT EXISTS (SELECT 1 FROM chunks p WHERE p.chunk_key = c.prev_chunk_key);")"

# ---------- 3 prev/next 闭环 ----------
step "3 prev/next 闭环"
FORWARD_BAD="$(psql_t "
WITH RECURSIVE walk AS (
  SELECT chunk_key, chapter_id, 1 AS depth FROM chunks WHERE prev_chunk_key IS NULL
  UNION ALL
  SELECT c.chunk_key, c.chapter_id, w.depth + 1 FROM chunks c JOIN walk w ON c.prev_chunk_key = w.chunk_key
)
SELECT count(*) FROM (
  SELECT w.chapter_id, max(w.depth) AS walked,
         (SELECT count(*) FROM chunks c2 WHERE c2.chapter_id = w.chapter_id) AS total
  FROM walk w GROUP BY w.chapter_id
) t WHERE t.walked <> t.total;")"
check_zero "沿 next 正向走，长度≠该章 chunk 数的章数" "$FORWARD_BAD"

BACKWARD_BAD="$(psql_t "
WITH RECURSIVE walk AS (
  SELECT chunk_key, chapter_id, 1 AS depth FROM chunks WHERE next_chunk_key IS NULL
  UNION ALL
  SELECT c.chunk_key, c.chapter_id, w.depth + 1 FROM chunks c JOIN walk w ON c.next_chunk_key = w.chunk_key
)
SELECT count(*) FROM (
  SELECT w.chapter_id, max(w.depth) AS walked,
         (SELECT count(*) FROM chunks c2 WHERE c2.chapter_id = w.chapter_id) AS total
  FROM walk w GROUP BY w.chapter_id
) t WHERE t.walked <> t.total;")"
check_zero "沿 prev 反向走，长度≠该章 chunk 数的章数" "$BACKWARD_BAD"

check_eq "首块（prev IS NULL）数" "$(psql_t "SELECT count(*) FROM chapters;")" "$(psql_t "SELECT count(*) FROM chunks WHERE prev_chunk_key IS NULL;")"
check_eq "末块（next IS NULL）数" "$(psql_t "SELECT count(*) FROM chapters;")" "$(psql_t "SELECT count(*) FROM chunks WHERE next_chunk_key IS NULL;")"
check_eq "正向走覆盖的 chunk 数" "$(psql_t "SELECT count(*) FROM chunks;")" "$(psql_t "
WITH RECURSIVE walk AS (
  SELECT chunk_key FROM chunks WHERE prev_chunk_key IS NULL
  UNION ALL
  SELECT c.chunk_key FROM chunks c JOIN walk w ON c.prev_chunk_key = w.chunk_key
) SELECT count(DISTINCT chunk_key) FROM walk;")"

# ---------- 4 token_count 抽查（需要 tokenizer） ----------
step "4 token_count 抽查（真跑 TokenCounter）"
if "$UV" run --directory "$RAG_DIR" python - "$BOOK_ID" <<'PY'
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from omniread.domain.text import chapter_content_hash
from omniread.infrastructure.db.models import Chunk
from omniread.infrastructure.db.session import create_engine_from_env
from omniread.infrastructure.tokenizer import get_token_counter
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1

book_id = int(sys.argv[1])
engine = create_engine_from_env()
try:
    counter = get_token_counter()
    with Session(engine) as session:
        rows = session.execute(
            select(
                Chunk.chunk_key, Chunk.content, Chunk.token_count, Chunk.content_hash
            )
            .where(Chunk.book_id == book_id)
            .order_by(Chunk.chunk_key)
        ).all()

    total = len(rows)
    step = max(1, total // 20)
    sample = rows[::step][:20]
    token_bad = [r.chunk_key for r in sample if counter.count(r.content) != r.token_count]
    hash_bad = [r.chunk_key for r in sample if chapter_content_hash(r.content) != r.content_hash]
    over = [r.chunk_key for r in rows if r.token_count > M0_PLACEHOLDER_V1.max_chunk_tokens]
    max_tokens = max(r.token_count for r in rows)

    print(
        f"  total={total}  sampled={len(sample)}  "
        f"token_count_mismatch={len(token_bad)}  content_hash_mismatch={len(hash_bad)}  "
        f"max_token_count={max_tokens}  over_600={len(over)}"
    )
    if token_bad:
        print("  token_count 不符样本：", token_bad[:5], file=sys.stderr)
    if hash_bad:
        print("  content_hash 不符样本：", hash_bad[:5], file=sys.stderr)
    if over:
        print("  超过 600 的 chunk：", over[:5], file=sys.stderr)
    sys.exit(1 if (token_bad or hash_bad or over) else 0)
finally:
    engine.dispose()
PY
then
  ok "抽查行 count(content)==token_count、content_hash 一致、全表 ≤600"
else
  bad "token_count / hash / 上限校验未通过（见上）"
fi

# ---------- 5 幂等：再导入一次 ----------
step "5 幂等：同一份语料再导入一次"
before_counts="$(for table in "${COUNTS[@]}"; do printf '%s=%s;' "$table" "$(psql_t "SELECT count(*) FROM $table WHERE $([ "$table" = books ] && echo "id=$BOOK_ID" || echo "book_id=$BOOK_ID");")"; done)"
before_keys="$(psql_t "SELECT md5(string_agg(chunk_key, ',' ORDER BY chunk_key)) FROM chunks WHERE book_id=$BOOK_ID;")"
echo "  导入前：$before_counts chunk_keys_md5=$before_keys"

if [ "$SKIP_REIMPORT" -eq 1 ]; then
  echo "  （--skip-reimport：跳过再导入）"
else
  "$UV" run --directory "$RAG_DIR" python -m omniread.pipelines.importing \
    --corpus-root "$CORPUS_ROOT" --book-id "$BOOK_ID" >/dev/null
  after_counts="$(for table in "${COUNTS[@]}"; do printf '%s=%s;' "$table" "$(psql_t "SELECT count(*) FROM $table WHERE $([ "$table" = books ] && echo "id=$BOOK_ID" || echo "book_id=$BOOK_ID");")"; done)"
  after_keys="$(psql_t "SELECT md5(string_agg(chunk_key, ',' ORDER BY chunk_key)) FROM chunks WHERE book_id=$BOOK_ID;")"
  echo "  导入后：$after_counts chunk_keys_md5=$after_keys"
  check_eq "重导后行数快照" "$before_counts" "$after_counts"
  check_eq "重导后 chunk_key 集合" "$before_keys" "$after_keys"
fi

# ---------- 汇总 ----------
printf '\n=== 汇总：%d 通过，%d 失败 ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
