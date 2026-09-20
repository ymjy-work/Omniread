"""把尚未嵌入的 chunk 批量写入 `chunks.embedding`（真实调用阿里百炼）。

这是 M0 里唯一一处对全部 chunk 的批量向量化，会真实计费，所以设计成：

- **只处理 `embedding IS NULL` 的行**：中断后重跑即可续，不会重复计费；
- `--dry-run` 只报待嵌入数量与预计请求数，不发任何请求；
- `--limit N` 可先跑一小批验证链路，再放开全量；
- 每批提交一次事务，进程被杀只丢最后一批。

密钥经 keymgr 注入（`keymgr run <profile> ...`），本脚本只读环境变量，不打印不落盘。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from omniread.infrastructure.db.models import Chunk
from omniread.infrastructure.db.session import create_engine_from_env
from omniread.infrastructure.providers.ali import EMBEDDING_DIM, AliEmbeddingAdapter

# 每次从库里取多少行交给适配器；适配器内部还会再按 10 条切批。
DB_BATCH = 100


async def run(*, dry_run: bool, limit: int | None, book_id: int) -> int:
    engine = create_engine_from_env()
    with Session(engine) as session:
        pending = session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.book_id == book_id, Chunk.embedding.is_(None))
        )
        total = session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.book_id == book_id)
        )
        print(f"book_id={book_id}：chunk 共 {total}，待嵌入 {pending}")

        if dry_run:
            requests = -(-pending // 10)  # 向上取整，适配器的批量是 10
            print(f"[dry-run] 预计 {requests} 次请求，未发出任何调用。")
            return 0
        if not pending:
            print("没有待嵌入的行，无需调用。")
            return 0
        if not os.environ.get("DASHSCOPE_API_KEY"):
            print("DASHSCOPE_API_KEY 未注入；用 keymgr run 注入后再跑。", file=sys.stderr)
            return 2

        adapter = AliEmbeddingAdapter()
        done = 0
        target = pending if limit is None else min(limit, pending)
        try:
            while done < target:
                rows = session.execute(
                    select(Chunk.chunk_key, Chunk.content)
                    .where(Chunk.book_id == book_id, Chunk.embedding.is_(None))
                    .order_by(Chunk.chunk_key)
                    .limit(min(DB_BATCH, target - done))
                ).all()
                if not rows:
                    break
                vectors = await adapter.embed_documents([content for _, content in rows])
                if len(vectors) != len(rows):
                    print(f"返回条数不符：要 {len(rows)} 条，得 {len(vectors)} 条", file=sys.stderr)
                    return 1
                for (key, _), vector in zip(rows, vectors, strict=True):
                    if len(vector) != EMBEDDING_DIM:
                        print(
                            f"{key} 的维度是 {len(vector)}，期望 {EMBEDDING_DIM}；"
                            "维度不符会让向量列建不起来，停在这里。",
                            file=sys.stderr,
                        )
                        return 1
                    session.execute(
                        update(Chunk).where(Chunk.chunk_key == key).values(embedding=vector)
                    )
                session.commit()
                done += len(rows)
                print(f"  已嵌入 {done}/{target}", flush=True)
        finally:
            await adapter.aclose()

    with Session(engine) as session:
        remaining = session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.book_id == book_id, Chunk.embedding.is_(None))
        )
    print(f"完成：本次嵌入 {done} 条，剩余未嵌入 {remaining} 条。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量回填 chunks.embedding（真实调用）")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="只报数量，不发请求")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条，用于先验小批")
    args = parser.parse_args(argv)
    return asyncio.run(run(dry_run=args.dry_run, limit=args.limit, book_id=args.book_id))


if __name__ == "__main__":
    sys.exit(main())
