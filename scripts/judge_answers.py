#!/usr/bin/env python
"""只重跑裁判：拿一次已落盘的 run 与它的回答复核件，换一版判据重判一遍。

用途是**换裁判提示词之后不必重花检索与回答的钱**。装配集从 run 产物的
`retrieval.scores.jsonl`（`assembled_keys`）回放，回答从 `--answers` 的 jsonl 读——
两者都是已经付过费的产物。30 题的一次重判只花 30 次裁判模型调用。

    python scripts/judge_answers.py --run-dir <run 目录> --answers <answers.jsonl> \
        --out temp/judge-<id>.json [--golden-dir <题集>] [--allow-incomplete] [--fake-providers]

**它不写 run 目录**：裁判的 `reason` 是自由文本、会逐字引用材料。

**它不重跑检索**，所以判的仍是「模型当时看到了什么」。材料正文按 `assembled_keys`
从库里取——与 `AnsweringRunner._load_context` 同一条路径、同一个顺序。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from omniread.infrastructure.db.context import PgContextSource  # noqa: E402
from omniread.infrastructure.db.session import create_engine_from_env  # noqa: E402
from omniread.infrastructure.providers.deepseek import DeepSeekChatAdapter  # noqa: E402
from omniread.pipelines.evaluation import (  # noqa: E402
    AnswerOutcome,
    build_query_request,
    fmt_ratio,
    load_golden_questions,
    run_judging_eval,
    write_judging_artifact,
)
from omniread.pipelines.judging import AnswerJudge, FakeAnswerJudge  # noqa: E402
from omniread.pipelines.mapping.runner import (  # noqa: E402
    DEFAULT_GOLDEN_DIR,
    DEFAULT_RUNS_DIR,
    GoldenError,
    golden_dataset_hash,
)
from sqlalchemy.orm import sessionmaker  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只重跑裁判（不重跑检索与回答）")
    parser.add_argument("--run-dir", type=Path, required=True, help="已有的 run 目录")
    parser.add_argument(
        "--answers",
        type=Path,
        required=True,
        help="该 run 的回答复核件（run_eval.py --answers-to 产出的那份 jsonl）",
    )
    parser.add_argument("--out", type=Path, required=True, help="裁判结果写到哪（JSON）")
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="题集不满数量目标时仍放行（留出题集用，口径同 run_eval.py）",
    )
    parser.add_argument(
        "--fake-providers",
        action="store_true",
        help="用确定性假裁判（零费用，产物不可作基线）",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="只判前 N 题，用于小批验证"
    )
    return parser.parse_args(argv)


def load_answers(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise SystemExit(f"找不到回答复核件：{path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["question_id"]: row for row in rows}


def load_assembled(run_dir: Path) -> dict[str, list[str]]:
    """从 run 产物读逐题装配集。**缺了即报错**，不静默退回空材料。"""
    path = run_dir / "retrieval.scores.jsonl"
    if not path.is_file():
        raise SystemExit(f"找不到检索产物：{path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["question_id"]: list(row["assembled_keys"]) for row in rows}


def check_dataset_matches(run_dir: Path, golden_dir: Path, allow_incomplete: bool) -> str:
    """挡住「拿 A 题集的回答去对 B 题集的装配集判」——那种错不会报错，只会静默失真。"""
    config_path = run_dir / "config.json"
    if not config_path.is_file():
        raise SystemExit(f"找不到 run 配置：{config_path}")
    recorded = json.loads(config_path.read_text(encoding="utf-8")).get("dataset_hash")
    actual = golden_dataset_hash(golden_dir, allow_incomplete=allow_incomplete)
    if recorded != actual:
        raise SystemExit(
            f"题集对不上：run 记录的是 {recorded}，--golden-dir 算出的是 {actual}\n"
            "  拒绝继续：拿另一份题集的回答去判，结果看着正常但没有意义。"
        )
    return actual


async def main_async(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    dataset_hash = check_dataset_matches(run_dir, args.golden_dir, args.allow_incomplete)

    questions = load_golden_questions(args.golden_dir)
    answers_by_id = load_answers(args.answers)
    assembled_by_id = load_assembled(run_dir)

    missing = [str(q["id"]) for q in questions if str(q["id"]) not in answers_by_id]
    if missing:
        raise SystemExit(f"回答复核件里缺少这些题：{'、'.join(missing[:5])}（共 {len(missing)}）")
    if args.limit is not None:
        questions = questions[: args.limit]

    # 逐题的装配集：只用到 `assembled[].chunk_key`，所以拿一个只有这一个属性的
    # 替身即可——不必重建 `RetrievalOutcome` 的其余字段（它们只在检索层有意义）。
    retrieval = {
        build_query_request(question, book_id=1): SimpleNamespace(
            assembled=[
                SimpleNamespace(chunk_key=key)
                for key in assembled_by_id[str(question["id"])]
            ]
        )
        for question in questions
    }
    answers = [
        AnswerOutcome(
            request_id=f"eval-{question['id']}",
            status=str(answers_by_id[str(question["id"])]["status"]),
            text=str(answers_by_id[str(question["id"])]["answer"]),
            chapters=tuple(answers_by_id[str(question["id"])].get("context_chapters", ())),
        )
        for question in questions
    ]

    if args.fake_providers:
        judge, provider, model = FakeAnswerJudge(), "fake", "fake-judge"
    else:
        chat = DeepSeekChatAdapter()
        judge, provider, model = AnswerJudge(chat), "deepseek", chat.model

    context = PgContextSource(sessionmaker(create_engine_from_env(), expire_on_commit=False))
    result = await run_judging_eval(
        questions=questions,
        answers=answers,
        retrieval=retrieval,
        context=context,
        judge=judge,
        on_progress=lambda index, total, qid: print(
            f"  [{index}/{total}] {qid}", file=sys.stderr, flush=True
        ),
    )

    # 与 run_eval.py 同一道闸门：run 目录进 git，裁判的 reason 只落 temp/。
    resolved = args.out.resolve()
    runs_root = args.runs_dir.resolve()
    if resolved == runs_root or runs_root in resolved.parents or run_dir in resolved.parents:
        raise SystemExit(f"不能把裁判结果写进 run 目录：{args.out}")

    write_judging_artifact(
        args.out,
        verdicts=result.verdicts,
        summary=result.summary,
        provider=provider,
        model=model,
        prompt_version=judge.prompt_version,
    )

    summary = result.summary
    print(f"题集      : {args.golden_dir}")
    print(f"dataset   : {dataset_hash}")
    print(f"来源 run  : {run_dir}")
    print(f"裁判      : {provider}/{model}（prompt_version {judge.prompt_version}）")
    print(f"产物      : {args.out}")
    print()
    for label in ("pass", "fail", "uncertain"):
        print(
            f"  {label:26s} {fmt_ratio(summary[label], summary['judged'])}"
            f"（分母 {summary['judged']}）"
        )
    for label in (
        "judged",
        "judge_failed",
        "supported_false",
        "citations_invalid",
        "incomplete",
        "refusal_wrong",
    ):
        print(f"  {label:26s} {summary[label]}")
    print()
    print("  不通过的题：")
    for item in result.verdicts:
        if item.verdict == "FAIL" or item.status == "failed":
            print(f"    {item.question_id:16s} {item.status:7s} {item.reason[:90]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except GoldenError as failure:
        raise SystemExit(str(failure)) from failure


if __name__ == "__main__":
    sys.exit(main())
