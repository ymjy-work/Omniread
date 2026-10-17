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
from collections.abc import Sequence
from dataclasses import fields, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

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
from omniread.infrastructure.providers.base import ChatModel  # noqa: E402
from omniread.infrastructure.providers.fake import (  # noqa: E402
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
)
from omniread.infrastructure.providers.deepseek import DeepSeekChatAdapter  # noqa: E402
from omniread.infrastructure.providers.glm import GlmChatAdapter  # noqa: E402
from omniread.pipelines.answering import answer_prompt_version  # noqa: E402
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1  # noqa: E402
from omniread.pipelines.evaluation import (  # noqa: E402
    FAKE_ANSWER_TRUST_NOTE,
    FAKE_JUDGE_TRUST_NOTE,
    FAKE_TRUST_NOTE,
    AnswerOutcome,
    GenerationScoreRecord,
    JudgedAnswer,
    JudgingEvalResult,
    RecordedRetrieval,
    fmt_ratio,
    load_golden_questions,
    run_generation_eval,
    run_judging_eval,
    run_retrieval_eval,
    write_eval_run_dir,
    write_judging_artifact,
)
from omniread.pipelines.judging import (  # noqa: E402
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNCERTAIN,
    AnswerJudge,
    FakeAnswerJudge,
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
from sqlalchemy.orm import sessionmaker  # noqa: E402

# 基线 run 的固定 id：后续 run 的回归门禁按它取基线值（M0-04 §6）。
BASELINE_RUN_ID = "2026-09-20-m0-baseline"

#: 留出题集（holdout）的标注。它进 `config.json` 的 `trust_note`，因为**它改变了
#: 数字的可比性**：题集不同即 `dataset_hash` 不同，这些数不能与 Golden 基线并列，
#: 只能用来回答「基线里有多少是过拟合」。
HOLDOUT_TRUST_NOTE = (
    "本次题集不满交付数量目标（--allow-incomplete）：dataset_hash 与 Golden 不同，"
    "数字不可与 Golden 基线并列，只用于留出验证。"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M0-9 检索层评测")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--run-id",
        default=BASELINE_RUN_ID,
        help=(
            "产物目录名。**默认值是 M0 基线目录**，所以覆盖式重跑默认落在它头上——"
            "离线冒烟（--fake-providers）必须显式给一个别的 id（下面会拦）"
        ),
    )
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
    parser.add_argument(
        "--only",
        default="",
        help=(
            "只跑题号含这些子串的题，逗号分隔（如 spoiler 或 alias-001,cross-002）。"
            "用来先小批验证：答案层的拒答标记是模型行为，跑满 86 题之前先拿十几题看它认不认"
        ),
    )
    parser.add_argument(
        "--answers-to",
        type=Path,
        default=None,
        help=(
            "把逐题回答原文写到这个路径（jsonl）。**必须落在 run 目录之外**——"
            "run 目录进 git，回答原文只落 temp/（M0-02 §7.1）。"
            "人工抽检与「拒答标记没被认出来」的排查都要看它"
        ),
    )
    parser.add_argument(
        "--answer-layer",
        action="store_true",
        help=(
            "同一个 run 里接着跑答案层（M1-2）：逐题让问答链作答，判定引用越界与"
            "拒答正确性。每题多 1 次回答模型调用；检索结果回放上面那一遍，不再重跑"
        ),
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help=(
            "答案层之后再跑一遍裁判（需 --answer-layer）：逐题把「材料 + 问题 + 回答」"
            "交给裁判模型，产出三态判定。**旁挂，不作门禁**（M0-04 §6），"
            "数字只落 --judge-out，不进 run 目录"
        ),
    )
    parser.add_argument(
        "--judge-out",
        type=Path,
        default=None,
        help=(
            "裁判结果写到这里（JSON：聚合 + 逐题，含 reason 自由文本）。"
            "**必须落在 run 目录之外**——裁判的 reason 会逐字引用材料。"
            "不传时默认写 temp/judge-<run-id>.json"
        ),
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "题集不满数量目标（总量 ≥60 / 单桶 ≥8 / 拒答 ≥10）时仍然放行。"
            "给留出题集用：它刻意只抽 30 题，结构与命名都合规，但达不到交付口径。"
            "**结构与命名一条不放松**，降级的只有数量"
        ),
    )
    args = parser.parse_args(argv)
    if args.judge and not args.answer_layer:
        parser.error("--judge 需要 --answer-layer：没有回答就无从判起")
    # 默认 run_id 是 M0 基线目录，而基线产物是入库的留痕：`--fake-providers` 不带
    # `--run-id` 跑一次，就会把那份 86 题的基线换成 3 题的假 provider 结果
    # （2026-10-13 真的踩到过一次，靠 git checkout 还原）。这种组合直接拦下来。
    if args.fake_providers and args.run_id == BASELINE_RUN_ID:
        parser.error(
            "离线冒烟（--fake-providers）必须显式给 --run-id："
            f"默认值是 {BASELINE_RUN_ID}，照默认跑会覆盖基线产物"
        )
    return args


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


def build_chat(args: argparse.Namespace) -> tuple[ChatModel, str]:
    """装配回答模型；返回 (模型, provider 名)。

    跟着 `--fake-providers` 走而不是另立开关：一次 run 要么整体离线（假 embedding /
    rerank / 回答），要么整体真实。混着来会产出一个「检索数不可信、答案数也不可信」
    却看起来正常的 run，而 `trust_note` 只能写一句话。
    """
    if args.fake_providers:
        return FakeChatModel(), "fake"
    return GlmChatAdapter(), "glm"


def build_judge(args: argparse.Namespace) -> tuple[object, str, str]:
    """装配裁判；返回 (裁判, provider 名, 模型名)。

    跟着 `--fake-providers` 走，与 `build_chat` 同一条纪律：一次 run 要么整体离线、
    要么整体真实——混着来会产出「一半数字不可信」却看起来正常的 run。

    裁判**刻意用与回答不同的模型**（回答走 GLM、裁判走 DeepSeek）：同一个模型判自己
    写的东西会偏向自己，而那种偏差在数字上只表现为「通过率偏高」，看不出来。
    两者共用同一把 DeepSeek key（改写与摘要已经在用），不新增凭据。
    """
    if args.fake_providers:
        fake = FakeAnswerJudge()
        return fake, fake.provider, fake.model
    chat = DeepSeekChatAdapter()
    return AnswerJudge(chat), "deepseek", chat.model


def _report_progress(index: int, total: int, question_id: str) -> None:
    """逐题回显到 **stderr** 并立刻 flush。

    两个细节都是被一次 86 题的真跑逼出来的：stdout 是最后要读的报告，进度混进去会把它
    搅乱；而不管哪个流，**不 flush 就等于没有**——输出会攒在缓冲区里，人看到的是
    「半小时没有任何动静」。
    """
    print(f"  [{index}/{total}] {question_id}", file=sys.stderr, flush=True)


def _write_answers(
    path: Path,
    *,
    runs_dir: Path,
    questions: Sequence[dict],
    outcomes: Sequence[AnswerOutcome],
) -> None:
    """把逐题回答原文写成复核件；**拒绝写进 run 目录**。

    与 `attribute_eval.py` 同一道闸门：run 目录进 git，`ALLOWED_RUN_FILES` 是硬白名单，
    回答原文一旦落进去就是整段正文入库。所以这里不靠「记得别写错」，而是直接拒绝。
    """
    resolved = path.resolve()
    runs_root = runs_dir.resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise SystemExit(
            f"不能把回答原文写进 run 目录：{path}\n"
            "  run 目录只准出现 ALLOWED_RUN_FILES 里的文件，且回答原文只落 temp/。"
        )

    rows = [
        {
            "question_id": str(question["id"]),
            "status": outcome.status,
            "context_chapters": list(outcome.chapters),
            "answer": outcome.text,
        }
        for question, outcome in zip(questions, outcomes, strict=True)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _write_judgments(
    path: Path,
    *,
    runs_dir: Path,
    verdicts: Sequence[JudgedAnswer],
    summary: dict[str, object],
    provider: str,
    model: str,
    prompt_version: str,
) -> None:
    """把裁判结果写成复核件（聚合 + 逐题）；**拒绝写进 run 目录**。

    裁判的 `reason` / `issues` / `raw` 是自由文本、**会逐字引用材料**——与回答原文
    同一条红线（`M0-02` §7.1）。所以这里与 `_write_answers` 同一道闸门：不靠「记得
    别写错」，而是直接拒绝。聚合数字也一并落这里，而不是塞进 `summary.json`：
    run 目录是入库产物，而裁判**不作门禁**，它的数字不该与确定性指标并列成基线。
    """
    resolved = path.resolve()
    runs_root = runs_dir.resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise SystemExit(
            f"不能把裁判结果写进 run 目录：{path}\n"
            "  裁判的 reason 会逐字引用材料，只落 temp/；run 目录只准出现"
            " ALLOWED_RUN_FILES 里的文件。"
        )

    write_judging_artifact(
        path,
        verdicts=verdicts,
        summary=summary,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
    )


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
    if needles := [part.strip() for part in args.only.split(",") if part.strip()]:
        questions = [q for q in questions if any(n in q["id"] for n in needles)]
        if not questions:
            raise SystemExit(f"--only {args.only!r} 没匹配到任何题")
    if args.limit is not None:
        questions = questions[: args.limit]
    mapping_lookup = load_mapping_lookup(args.runs_dir, args.mapping_run)
    params = build_params(args.overrides)
    pipeline, provider, embedding_model, rerank_model = build_pipeline(args, params)

    trust_notes = [FAKE_TRUST_NOTE] if args.fake_providers else []
    if args.allow_incomplete:
        trust_notes.append(HOLDOUT_TRUST_NOTE)

    result = await run_retrieval_eval(
        run_id=args.run_id,
        questions=questions,
        pipeline=pipeline,
        mapping_lookup=mapping_lookup,
        dataset_hash=golden_dataset_hash(
            args.golden_dir, allow_incomplete=args.allow_incomplete
        ),
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
        trust_note=" ".join(trust_notes),
        neighbor_expand=args.neighbor_expand,
    )

    config = result.config
    summary = dict(result.summary)
    failures = list(result.failures)
    generation_records: tuple[GenerationScoreRecord, ...] = ()
    generation_summary: dict[str, object] | None = None
    judging_result: JudgingEvalResult | None = None
    judge_label: tuple[str, str] = ("", "")

    if args.answer_layer:
        # 检索结果回放上面那一遍（`RecordedRetrieval`），不重跑：同一次 run 里两层
        # 必须看同一份装配集，而 provider 那侧不保证两次采样一致。
        chat, answer_provider = build_chat(args)
        context_source = PgContextSource(
            sessionmaker(create_engine_from_env(), expire_on_commit=False)
        )
        runner = AnsweringRunner(
            retrieval=RecordedRetrieval(result.outcomes),
            context=context_source,
            chat=chat,
            answer_provider=answer_provider,
        )
        generation_result = await run_generation_eval(
            questions=questions,
            runner=runner,
            answer_provider=answer_provider,
            answer_model=chat.model,
            book_id=args.book_id,
            neighbor_expand=args.neighbor_expand,
            on_progress=_report_progress,
        )
        generation_records = generation_result.records
        generation_summary = generation_result.summary
        summary["generation"] = generation_summary
        failures.extend(generation_result.failures)
        if args.answers_to is not None:
            _write_answers(
                args.answers_to,
                runs_dir=args.runs_dir,
                questions=questions,
                outcomes=generation_result.outcomes,
            )
        if args.fake_providers:
            trust_notes.append(FAKE_ANSWER_TRUST_NOTE)

        if args.judge:
            # 裁判旁挂在确定性指标旁边（**不作门禁**，M0-04 §6）：它的材料从本次 run
            # 已算好的装配集回放，与回答看到的是同一份，所以判定描述的是「模型当时
            # 看到了什么」，而不是另一次检索。
            judge, judge_provider, judge_model = build_judge(args)
            judge_label = (judge_provider, judge_model)
            if args.fake_providers:
                trust_notes.append(FAKE_JUDGE_TRUST_NOTE)
            judging_result = await run_judging_eval(
                questions=questions,
                answers=generation_result.outcomes,
                retrieval=result.outcomes,
                context=context_source,
                judge=judge,
                book_id=args.book_id,
                neighbor_expand=args.neighbor_expand,
                on_progress=_report_progress,
            )
            judge_out = args.judge_out or (
                REPO_ROOT / "temp" / f"judge-{args.run_id}.json"
            )
            _write_judgments(
                judge_out,
                runs_dir=args.runs_dir,
                verdicts=judging_result.verdicts,
                summary=judging_result.summary,
                provider=judge_provider,
                model=judge_model,
                prompt_version=judge.prompt_version,  # type: ignore[attr-defined]
            )
            print(f"裁判复核件：{judge_out}", file=sys.stderr, flush=True)

        config = replace(
            config,
            kind="full",
            phase="retrieval+generation",
            answer_provider=answer_provider,
            answer_model=chat.model,
            prompt_version=answer_prompt_version(),
            # 这两个字段本来就为裁判留好了（M0-02 的 rag_runs 列，此前恒为
            # not-exercised）。裁判跑过就如实填，不跑就保持默认值。
            judge_provider=judge_label[0] or config.judge_provider,
            judge_model=judge_label[1] or config.judge_model,
            trust_note=" ".join(trust_notes),
        )

    run_dir = args.runs_dir / args.run_id
    write_eval_run_dir(
        run_dir,
        config=config,
        retrieval_records=result.records,
        generation_records=generation_records,
        summary=summary,
        failures=failures,
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
    print("按题型分列（只分列、不加权）：")
    for question_type, values in result.summary["per_type"].items():  # type: ignore[union-attr]
        # 分母紧挨着比率打印：0/0 也是 0.0000，两个数并排才不会读错。
        print(
            f"  {question_type:8s} 题数 {values['questions']:3d} "
            f"证据 {values['evidence_total']:4d} "
            f"evidence_recall {fmt_ratio(values['evidence_recall'], values['evidence_total'])} "
            f"leak {values['leak']}"
        )
    if generation_summary is not None:
        print()
        print("答案层（M1-2，确定性判定，不调模型判断）：")
        for label, key, denominator_key in (
            ("answered", "answered", "question_count"),
            ("citation_in_set", "citation_in_set", "citation_in_set_denominator"),
            ("refusal_correct", "refusal_correct", "refusal_denominator"),
        ):
            print(
                f"  {label:26s} "
                f"{fmt_ratio(generation_summary[key], generation_summary[denominator_key])}"
                f"（分母 {generation_summary[denominator_key]}）"
            )
        for label in (
            "answered_without_citation",
            "refusal_false_positive",
            "citation_out_of_range_total",
            "citation_malformed_total",
            "generation_failed",
        ):
            print(f"  {label:26s} {generation_summary[label]}")
        print(
            "  （`citation_in_set` 分母不含拒答与生成失败的题；"
            "`answered_without_citation` 必须与它并读——空集天然满足集合判定。）"
        )

    if judging_result is not None:
        values = judging_result.summary
        print()
        print(f"裁判层（{judge_label[0]}/{judge_label[1]}，三态判定，**旁挂、不作门禁**）：")
        for label in ("pass", "fail", "uncertain"):
            print(
                f"  {label:26s} {fmt_ratio(values[label], values['judged'])}"
                f"（分母 {values['judged']}）"
            )
        for label in (
            "judged",
            "judge_failed",
            "supported_false",
            "citations_invalid",
            "incomplete",
            "refusal_wrong",
        ):
            print(f"  {label:26s} {values[label]}")
        print(
            "  （判不出来的题不参与比率——`judge_failed` 与 `judged` 必须并读，"
            "否则「裁判坏了一半」会显示成一个偏低的通过率。）"
        )
        print("  按题型分列（只分列、不加权）：")
        for question_type, bucket in values["per_type"].items():  # type: ignore[union-attr]
            print(
                f"    {question_type:8s} 判 {bucket['judged']:3d} "
                f"通过 {bucket['pass']:3d} 不通过 {bucket['fail']:3d} "
                f"无法确定 {bucket['uncertain']:3d} 判失败 {bucket['judge_failed']:3d}"
            )

    print()
    print(f"失败样本 {len(failures)} 条；计数 {result.summary['failure_counts']}")

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
