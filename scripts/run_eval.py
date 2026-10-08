#!/usr/bin/env python
"""M0-9 检索层评测：跑 Golden 86 题，产出逐题分数、汇总与 run 记录。

用法（仓库根执行）：

    # 真实评测（需要 DASHSCOPE_API_KEY；诚实线：本机可用 keymgr run codex 注入）
    keymgr run codex python scripts/run_eval.py --run-id 2026-09-20-m0-baseline

    # 只验链路结构（假 embedding/rerank，产物会写明不可作为基线）
    keymgr run codex python scripts/run_eval.py --fake-providers --run-id 2026-09-20-smoke

    # 顺带写 rag_runs
    keymgr run omniread python scripts/run_eval.py --write-db

**为什么必须连库**：检索链的 dense 一路指向 `chunks.embedding` 列，语料直读没有向量列。
用假 embedding 也能跑通，但那是「假查询向量 × 真文档向量」——两个向量空间不匹配，
排名是确定性噪声，会一路污染到 `evidence_recall`。所以假 provider 模式产出的 run
会在 `config.json` 里带 `trust_note`，明确标注不可作为基线。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import fields, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from omniread.infrastructure.db.session import create_engine_from_env  # noqa: E402
from omniread.infrastructure.objectstore.corpus import (  # noqa: E402
    build_checksums,
    read_corpus,
)
from omniread.infrastructure.providers.ali import (  # noqa: E402
    EMBEDDING_DIM,
    AliEmbeddingAdapter,
    AliRerankAdapter,
)
from omniread.infrastructure.providers.fake import (  # noqa: E402
    FakeEmbeddingModel,
    FakeRerankModel,
)
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1  # noqa: E402
from omniread.pipelines.evaluation import (  # noqa: E402
    FAKE_TRUST_NOTE,
    fmt_ratio,
    load_golden_questions,
    run_retrieval_eval,
    write_eval_run_dir,
)
from omniread.pipelines.mapping.artifacts import check_run_dir  # noqa: E402
from omniread.pipelines.mapping.runner import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN_DIR,
    DEFAULT_RUNS_DIR,
    golden_dataset_hash,
    golden_schema_version,
)
from omniread.pipelines.mapping.types import MATCH_MATCHED  # noqa: E402
from omniread.pipelines.params import (  # noqa: E402
    M0_PARAMS,
    RetrievalParams,
    retrieval_params_record,
)
from omniread.pipelines.retrieval.dense import PgVectorDenseIndex  # noqa: E402
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline  # noqa: E402
from omniread.pipelines.retrieval.store import PgChunkStore  # noqa: E402

# 基线 run 的固定 id：后续 run 的回归门禁按它取基线值（M0-04 §6）。
BASELINE_RUN_ID = "2026-09-20-m0-baseline"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M0-9 检索层评测")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--run-id", default=BASELINE_RUN_ID)
    parser.add_argument(
        "--mapping-run",
        default="2026-09-20-m0-mapping",
        help="从哪个映射 run 读 evidence→chunk 映射（eval/runs/<id>/mappings.jsonl）",
    )
    parser.add_argument(
        "--fake-providers",
        action="store_true",
        help="用假 embedding/rerank；产物会标注不可作为基线",
    )
    parser.add_argument("--write-db", action="store_true", help="把 run 记录写进 rag_runs")
    parser.add_argument(
        "--no-neighbor",
        dest="neighbor_expand",
        action="store_false",
        help=(
            "关掉邻块补位（QueryRequest.neighbor_expand，默认开）。只影响装配补不补邻块，"
            "不改任何上限；会随 retrieval_params 记进 config.json"
        ),
    )
    parser.add_argument(
        "--set",
        dest="overrides",
        default="",
        help=(
            "单变量实验的参数覆盖，形如 rerank_k=32 或 dense_k=100,rrf_k=100；"
            "不传即 M0 基线。一次只改一个——同时改两个就分不清是谁起的作用"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只跑前 N 题。用于先拿真 provider 验链路（每题 2 次请求），再放开全量",
    )
    return parser.parse_args(argv)


def build_params(spec: str) -> RetrievalParams:
    """把 `k=v,k=v` 解析成参数对象；不传即 M0 基线。

    **刻意不改 `params.py`**：那是单向门，改它就是换基线，而一次实验不该动基线。
    实际生效的值会随 run 落进 `config.json`，所以每个 run 自证用了什么参数；
    选定配置要成为新基线时，再单独、显式地改 `params.py`。

    取值合法性由 `RetrievalParams.__post_init__` 把关（例如
    `ask_top_k <= ask_max_chapters * ask_chunks_per_chapter`），这里不重写一遍。
    """
    known = {field.name for field in fields(RetrievalParams)}
    overrides: dict[str, int] = {}
    for item in filter(None, (chunk.strip() for chunk in spec.split(","))):
        name, separator, raw = item.partition("=")
        name = name.strip()
        if separator == "" or name not in known:
            raise SystemExit(f"--set 用法是 名字=整数，不认识这一段：{item!r}")
        try:
            overrides[name] = int(raw)
        except ValueError:
            raise SystemExit(f"--set {name} 的值不是整数：{raw!r}") from None
    try:
        return replace(M0_PARAMS, **overrides)
    except ValueError as exc:
        raise SystemExit(f"--set 的参数不合法：{exc}") from exc


def build_pipeline(
    args: argparse.Namespace, params: RetrievalParams
) -> tuple[RetrievalPipeline, str, str, str]:
    """装配检索链；返回 (pipeline, provider 名, embedding 型号, rerank 型号)。"""
    factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
    if args.fake_providers:
        embedder, reranker = FakeEmbeddingModel(), FakeRerankModel()
        provider = "fake"
    else:
        embedder, reranker = AliEmbeddingAdapter(), AliRerankAdapter()
        provider = "ali"
    pipeline = RetrievalPipeline(
        store=PgChunkStore(factory),
        dense=PgVectorDenseIndex(factory),
        embedder=embedder,
        reranker=reranker,
        params=params,
    )
    return pipeline, provider, embedder.model, reranker.model


def load_mapping_lookup(runs_dir: Path, mapping_run: str) -> dict[str, str | None]:
    """读映射 run 的 `mappings.jsonl`，折成 evidence_hash → chunk_key。

    只读 run 产物、不查库：映射的权威副本在 run 目录里，`chunk_mappings` 表是缓存。
    产物缺了就报错，不静默退回「全部未映射」——那会让所有 recall 变成 0 却看不出原因。

    只认 `matched`：`low_conf` 虽然带 chunk_key，但它表示「没有块完整包含该证据」，
    当成命中会让指标虚高。
    """
    path = runs_dir / mapping_run / "mappings.jsonl"
    if not path.is_file():
        raise SystemExit(
            f"找不到映射产物：{path}\n"
            f"      先跑 python scripts/run_mapping.py（--run-id {mapping_run}）"
        )
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return {
        row["evidence_hash"]: (
            row["matched_chunk_key"] if row["match_status"] == MATCH_MATCHED else None
        )
        for row in rows
    }


async def main_async(args: argparse.Namespace) -> int:
    corpus = read_corpus(args.corpus_root, book_id=args.book_id)
    manifest_hash = str(build_checksums(corpus)["corpus_manifest_hash"])

    questions = load_golden_questions(args.golden_dir)
    if args.limit is not None:
        questions = questions[: args.limit]
    mapping_lookup = load_mapping_lookup(args.runs_dir, args.mapping_run)
    params = build_params(args.overrides)
    pipeline, provider, embedding_model, rerank_model = build_pipeline(args, params)

    result = await run_retrieval_eval(
        run_id=args.run_id,
        questions=questions,
        pipeline=pipeline,
        mapping_lookup=mapping_lookup,
        dataset_hash=golden_dataset_hash(args.golden_dir),
        dataset_version=golden_schema_version(args.golden_dir),
        corpus_manifest_hash=manifest_hash,
        chunk_source="db",
        chunking_version=M0_PLACEHOLDER_V1.profile_id,
        tokenizer_id=M0_PLACEHOLDER_V1.tokenizer_id,
        retrieval_provider=provider,
        embedding_provider="dashscope" if provider == "ali" else "fake",
        embedding_model=embedding_model,
        # 维度直接取常量，不问 provider：换维度是单向门，探索针会白花一次真实调用，
        # 而返回值的类型/长度本来也不该决定记录口径。
        embedding_dim=EMBEDDING_DIM,
        rerank_provider="dashscope" if provider == "ali" else "fake",
        rerank_model=rerank_model,
        retrieval_params=retrieval_params_record(params, neighbor_expand=args.neighbor_expand),
        book_id=args.book_id,
        trust_note=FAKE_TRUST_NOTE if args.fake_providers else "",
        neighbor_expand=args.neighbor_expand,
    )

    run_dir = args.runs_dir / args.run_id
    write_eval_run_dir(
        run_dir,
        config=result.config,
        retrieval_records=result.records,
        summary=result.summary,
        failures=result.failures,
    )

    print(f"run_id   : {args.run_id}（{'假 provider' if args.fake_providers else '真实 provider'}）")
    print(f"产物目录 : {run_dir}")
    print(f"映射来源 : eval/runs/{args.mapping_run}/mappings.jsonl")
    print()
    evidence_total = result.summary["evidence_total"]
    for key in ("question_count", "evidence_recall", "evidence_total", "evidence_mapped", "leak"):
        # 与产物走同一条渲染规则（`fmt_ratio`），不在这里另写一套。
        value = (
            fmt_ratio(result.summary[key], evidence_total)
            if key == "evidence_recall"
            else result.summary[key]
        )
        print(f"  {key:20s} {value}")
    print()
    print("按难度分列（只分列、不加权）：")
    for difficulty, values in result.summary["per_difficulty"].items():  # type: ignore[union-attr]
        # 分母紧挨着比率打印：0/0 也是 0.0000，两个数并排才不会读错。
        print(
            f"  {difficulty:8s} 题数 {values['questions']:3d} "
            f"证据 {values['evidence_total']:4d} "
            f"evidence_recall {fmt_ratio(values['evidence_recall'], values['evidence_total'])} "
            f"leak {values['leak']}"
        )
    print()
    print(f"失败样本 {len(result.failures)} 条；计数 {result.summary['failure_counts']}")

    problems = check_run_dir(run_dir)
    if problems:
        print()
        print("产物红线检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("产物红线检查：通过")

    if args.write_db:
        from omniread.infrastructure.db.runs import build_run_row, utc_now, write_run

        factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        now = utc_now()
        write_run(
            factory,
            build_run_row(
                result.config,
                artifact_dir=str(run_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
                started_at=now,
                finished_at=now,
            ),
        )
        print(f"已写入 rag_runs：{args.run_id}")

    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
