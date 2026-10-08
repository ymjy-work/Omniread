#!/usr/bin/env python
"""未命中 evidence 的逐条归因：离线、零费用、不连库、不调模型。

它回答的是「这一条 evidence 是在哪一阶段丢的」，用来决定该拧哪个参数——
是装配 cap、重排窗口、融合段数，还是召回通道的候选深度。

**它比 `resummarize_eval.py` 多要两路输入**（Golden 题面 + 映射 run 的
`mappings.jsonl`），因为逐题记录里只有**去重后的 chunk_key**，而一条 key 可能承
多条 evidence（同一段原文被多道题复用）。要按 evidence 计数——那才是与
`evidence_recall` 同单位的量——就得把 evidence 列表拿回来。口径由
`attribution.attribute_losses` 里的闸门保证：算出的命中数必须逐题等于记录里的
`evidence_hit`，否则抛错，不出一份与头条数字对不上的报告。

两个加载函数都**直接复用既有实现**，不另抄一份：逐题记录读 `resummarize_eval.load_records`，
映射表读 `run_eval.load_mapping_lookup`。抄一份就等于给自己留一条分叉的路。

用法（仓库根执行）：

    python scripts/attribute_eval.py --run-id 2026-09-20-m0-baseline
    python scripts/attribute_eval.py --run-id <id> --out temp/attribution-<id>.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))
# 两个脚本模块：加载函数的单一实现在它们那里，这里不重抄。
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from omniread.pipelines.evaluation.attribution import (  # noqa: E402
    attribute_losses,
    render_attribution,
)
from omniread.pipelines.evaluation.runner import load_golden_questions  # noqa: E402
from omniread.pipelines.mapping.runner import DEFAULT_GOLDEN_DIR, DEFAULT_RUNS_DIR  # noqa: E402
from resummarize_eval import load_records  # noqa: E402
from run_eval import load_mapping_lookup  # noqa: E402

DEFAULT_MAPPING_RUN = "2026-09-20-m0-mapping"
#: run 目录只准出现 `ALLOWED_RUN_FILES` 里的文件（CI 第 12 步全量扫 `eval/runs/`），
#: 所以归因报告一律写 `temp/`——它是复核件，不是 run 的产物。
RUNS_SUBDIR = "runs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="未命中 evidence 的逐条归因")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mapping-run", default=DEFAULT_MAPPING_RUN)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="写到文件（默认只打印）。**不许落在 eval/runs/ 下**，那里有文件白名单",
    )
    return parser.parse_args(argv)


def _refuse_run_dir(path: Path, runs_dir: Path) -> None:
    """拒绝把报告写进 run 目录：那里进 git，且白名单是硬门。"""
    resolved = path.resolve()
    runs_root = runs_dir.resolve()
    if resolved == runs_root or runs_root in resolved.parents:
        raise SystemExit(
            f"不能写到 run 目录下：{path}\n"
            "  run 目录只准出现 ALLOWED_RUN_FILES 里的文件（CI 会全量扫）。\n"
            "  归因报告是复核件，请写 temp/。"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.runs_dir / args.run_id
    if not run_dir.is_dir():
        raise SystemExit(f"run 目录不存在：{run_dir}")

    records = load_records(run_dir)
    questions = load_golden_questions(args.golden_dir)
    mapping_lookup = load_mapping_lookup(args.runs_dir, args.mapping_run)

    attribution = attribute_losses(questions, mapping_lookup, records)
    report = render_attribution(attribution, run_id=args.run_id)

    print(f"run_id    : {args.run_id}")
    print(f"逐题记录  : {len(records)} 条")
    print(f"映射来源  : eval/runs/{args.mapping_run}/mappings.jsonl")
    print(f"Golden    : {args.golden_dir}")
    print()
    print(report)

    if args.out is not None:
        _refuse_run_dir(args.out, args.runs_dir)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"\n已写出：{args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
