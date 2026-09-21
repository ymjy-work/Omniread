#!/usr/bin/env python
"""M0-9 生成层评测：跑 Golden 86 题，产出逐题判定、汇总与 run 记录。

用法（仓库根执行；用 venv 的 python——`temp/local-env.sh` 只注入环境变量、不激活 venv）：

    # 真实评测（需要 GLM_API_KEY；本机可用 keymgr run omniread 注入）
    source temp/local-env.sh && keymgr run omniread \\
      services/rag/.venv/Scripts/python.exe scripts/run_generation_eval.py --write-db

    # 只验链路结构（假回答模型；产物会写明不可作为基线）
    ... --fake-providers --limit 3

    # 中途断了接着跑（已答过的题不重花调用）
    ... --resume

**两条产物分家**：`temp/run.gen.jsonl` 放模型看到与写出的全部文本（回答正文、材料正文），
`eval/runs/<run_id>/generation.scores.jsonl` 只放指针与标量。`eval/` 进 git，
所以后者的字段集由 `GenerationScoreRecord` 定死——那里没有放过正文的位置。

**这个 run 与检索层基线是两个 run**：`run_id` 是 `rag_runs` 的主键，用同一个 id 会把
检索层那份基线 upsert 掉，产物目录也会被整体重写。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from omniread.application.query_service import AnsweringRunner  # noqa: E402
from omniread.infrastructure.db.context import PgContextSource  # noqa: E402
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
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
)
from omniread.infrastructure.providers.glm import GlmChatAdapter  # noqa: E402
from omniread.pipelines.answering.prompt import answer_prompt_version  # noqa: E402
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1  # noqa: E402
from omniread.pipelines.evaluation import MEMBERSHIP_KEY  # noqa: E402
from omniread.pipelines.evaluation.artifacts import write_eval_run_dir  # noqa: E402
from omniread.pipelines.evaluation.generation_runner import (  # noqa: E402
    FAKE_GENERATION_TRUST_NOTE,
    TRANSCRIPT_FILENAME,
    CapturingContextSource,
    load_transcripts,
    run_generation_eval,
)
from omniread.pipelines.evaluation.runner import load_golden_questions  # noqa: E402
from omniread.pipelines.mapping.artifacts import check_run_dir  # noqa: E402
from omniread.pipelines.mapping.runner import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN_DIR,
    DEFAULT_RUNS_DIR,
    golden_dataset_hash,
    golden_schema_version,
)
from omniread.pipelines.params import M0_PARAMS, retrieval_params_record  # noqa: E402
from omniread.pipelines.retrieval.dense import PgVectorDenseIndex  # noqa: E402
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline  # noqa: E402
from omniread.pipelines.retrieval.store import PgChunkStore  # noqa: E402

#: 生成层基线 run 的固定 id。与检索层基线 `2026-09-20-m0-baseline` **必须不同**：
#: `run_id` 是 `rag_runs` 主键，同名会把那份基线覆盖掉。
BASELINE_RUN_ID = "2026-09-21-m0-generation"

#: 中间产物默认落 `temp/`（已 gitignore）。它是全仓唯一允许放正文的地方。
DEFAULT_TEMP_DIR = REPO_ROOT / "temp" / "generation"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M0-9 生成层评测")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--temp-dir", type=Path, default=DEFAULT_TEMP_DIR)
    parser.add_argument("--run-id", default=BASELINE_RUN_ID)
    parser.add_argument(
        "--fake-providers",
        action="store_true",
        help="生成与检索都用假 provider；产物会标注不可作为基线",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="跳过中间产物里已有答案的题（那些题的真实调用已经花过）",
    )
    parser.add_argument("--write-db", action="store_true", help="把 run 记录写进 rag_runs")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只跑前 N 题。用于先拿真 provider 验链路，再放开全量",
    )
    return parser.parse_args(argv)


def build_runner(
    args: argparse.Namespace,
) -> tuple[AnsweringRunner, CapturingContextSource, str, str]:
    """装配问答链；返回 (runner, 捕获材料的 context, 回答 provider 名, 回答模型名)。

    `CapturingContextSource` 要**同时**给 runner 与评测编排——前者用它取材料，
    后者用它把「模型当时看到的是什么」留档。
    """
    session_factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
    if args.fake_providers:
        embedder, reranker, chat = (
            FakeEmbeddingModel(),
            FakeRerankModel(),
            FakeChatModel(),
        )
        provider = "fake"
    else:
        embedder, reranker, chat = (
            AliEmbeddingAdapter(),
            AliRerankAdapter(),
            GlmChatAdapter(),
        )
        provider = "glm"
    pipeline = RetrievalPipeline(
        store=PgChunkStore(session_factory),
        dense=PgVectorDenseIndex(session_factory),
        embedder=embedder,
        reranker=reranker,
    )
    context = CapturingContextSource(PgContextSource(session_factory))
    runner = AnsweringRunner(
        retrieval=pipeline,
        context=context,
        chat=chat,
        answer_provider=provider,
    )
    return runner, context, provider, chat.model


async def main_async(args: argparse.Namespace) -> int:
    corpus = read_corpus(args.corpus_root, book_id=args.book_id)
    manifest_hash = str(build_checksums(corpus)["corpus_manifest_hash"])

    questions = load_golden_questions(args.golden_dir)
    if args.limit is not None:
        questions = questions[: args.limit]

    runner, context, provider, answer_model = build_runner(args)
    transcript_path = args.temp_dir / args.run_id / TRANSCRIPT_FILENAME

    done_before = len(load_transcripts(transcript_path)) if args.resume else 0

    def progress(index: int, total: int, note: str) -> None:
        print(f"  [{index:3d}/{total}] {note}", flush=True)

    result = await run_generation_eval(
        run_id=args.run_id,
        questions=questions,
        runner=runner,
        context=context,
        transcript_path=transcript_path,
        dataset_hash=golden_dataset_hash(args.golden_dir),
        dataset_version=golden_schema_version(args.golden_dir),
        corpus_manifest_hash=manifest_hash,
        chunking_version=M0_PLACEHOLDER_V1.profile_id,
        tokenizer_id=M0_PLACEHOLDER_V1.tokenizer_id,
        answer_provider=provider,
        retrieval_provider="fake" if args.fake_providers else "ali",
        embedding_provider="fake" if args.fake_providers else "dashscope",
        embedding_model="fake" if args.fake_providers else "qwen3.7-text-embedding",
        embedding_dim=EMBEDDING_DIM,
        rerank_provider="fake" if args.fake_providers else "dashscope",
        rerank_model="fake" if args.fake_providers else "qwen3.7-text-rerank",
        retrieval_params=retrieval_params_record(M0_PARAMS),
        book_id=args.book_id,
        resume=args.resume,
        trust_note=FAKE_GENERATION_TRUST_NOTE if args.fake_providers else "",
        on_progress=progress,
    )

    run_dir = args.runs_dir / args.run_id
    write_eval_run_dir(
        run_dir,
        config=result.config,
        generation_records=result.records,
        summary=result.summary,
        failures=result.failures,
    )

    print()
    print(f"run_id   : {args.run_id}（{'假 provider' if args.fake_providers else '真实 provider'}）")
    print(f"产物目录 : {run_dir}")
    print(f"中间产物 : {transcript_path}（含正文，不进 git）")
    if done_before:
        print(f"          其中 {done_before} 题来自上次运行，未重复调用")
    print(f"回答模型 : {answer_model}；prompt_version {answer_prompt_version()}")
    print()
    denominator = result.summary["citation_membership_denominator"]
    print(f"  {'题目数':20s} {result.summary['question_count']}")
    print(f"  {MEMBERSHIP_KEY:20s} {result.summary[MEMBERSHIP_KEY]:.4f}（分母 {denominator}）")
    print(f"  {'generation_failed':20s} {result.summary['generation_failed']}")
    print(f"  {'越界引用合计':20s} {result.summary['citation_out_of_range_total']}")
    print(f"  {'非规范写法合计':20s} {result.summary['citation_malformed_total']}")
    print()
    print("按难度分列：")
    for difficulty, values in result.summary["per_difficulty"].items():  # type: ignore[union-attr]
        print(
            f"  {difficulty:8s} 题数 {values['questions']:3d} "
            f"成员性 {values[MEMBERSHIP_KEY]:.4f} "
            f"失败 {values['generation_failed']}"
        )
    print()
    print("judge 指标：未执行（judge 未校准，M0-04 §6 规定只报告、不作结论）")
    print(f"失败样本 {len(result.failures)} 条；阶段计数 "
          f"{_count_stages(result.failures)}")

    if problems := check_run_dir(run_dir):
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


def _count_stages(failures: tuple[dict[str, object], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in failures:
        stage = str(item.get("stage", ""))
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
