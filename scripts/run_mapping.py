#!/usr/bin/env python
"""M0-7b：跑 evidence→chunk 映射，产出 run 产物、人工复核件与（可选）落库。

用法（仓库根执行）：

    python scripts/run_mapping.py                      # 语料直读，不连库
    python scripts/run_mapping.py --source db          # 读真库冻结的 chunks（需凭据）
    python scripts/run_mapping.py --write-db           # 额外写 chunk_mappings
    keymgr run omniread python scripts/run_mapping.py --source db --write-db

产物分两处：

- `eval/runs/<run_id>/`：进 git 的审计副本，只带指针与指标值（M0-02 §7.1）。
- `temp/mapping-review/`：需要正文的人工复核件，**不进 git**——它含整段 chunk 正文。

`--source corpus` 与 `--source db` 走同一个区间还原函数，差别只在数据取自哪里：
前者按当前代码从语料重算，后者读导入时冻结进 `chapters` / `chunks` 的那份副本。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from omniread.infrastructure.db.session import create_engine_from_env  # noqa: E402
from omniread.infrastructure.objectstore.corpus import read_corpus  # noqa: E402
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1  # noqa: E402
from omniread.pipelines.mapping import (  # noqa: E402
    NO_PROMPT_VERSION,
    check_run_dir,
    slices_from_corpus,
    write_run_dir,
)
from omniread.pipelines.mapping.review import (  # noqa: E402
    build_review_rows,
    write_review,
)
from omniread.pipelines.mapping.runner import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN_DIR,
    DEFAULT_RUNS_DIR,
    load_golden_evidence,
    golden_dataset_hash,
    run_mapping,
)
from omniread.pipelines.mapping.sources import slices_from_db  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M0-7b evidence→chunk 映射")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument(
        "--source",
        choices=["corpus", "db"],
        default="corpus",
        help="corpus=从仓库内语料重算（默认，免凭据）；db=读真库冻结的 chunks",
    )
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--review-dir", type=Path, default=REPO_ROOT / "temp" / "mapping-review"
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="缺省为 <日期>-m0-mapping；同日重跑会整体覆盖该目录",
    )
    parser.add_argument(
        "--write-db", action="store_true", help="把结果 upsert 进 chunk_mappings"
    )
    parser.add_argument("--no-review", action="store_true", help="跳过人工复核件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = args.run_id or f"{datetime.now().strftime('%Y-%m-%d')}-m0-mapping"

    if args.source == "corpus":
        corpus = read_corpus(args.corpus_root, book_id=args.book_id)
        slices = slices_from_corpus(corpus)
        chunk_source = "corpus"
    else:
        from sqlalchemy.orm import sessionmaker

        factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        slices = slices_from_db(factory, args.book_id)
        chunk_source = "db"

    evidence = load_golden_evidence(args.golden_dir)
    dataset_hash = golden_dataset_hash(args.golden_dir)
    question_count = len({item.question_id for item in evidence})

    result = run_mapping(
        run_id=run_id,
        slices=slices,
        evidence=evidence,
        dataset_hash=dataset_hash,
        chunk_source=chunk_source,
        chunking_version=M0_PLACEHOLDER_V1.profile_id,
        tokenizer_id=M0_PLACEHOLDER_V1.tokenizer_id,
        mapper_prompt_version=NO_PROMPT_VERSION,
        golden_question_count=question_count,
    )

    run_dir = args.runs_dir / run_id
    write_run_dir(
        run_dir, config=result.config, records=result.records, summary=result.summary
    )

    problems = check_run_dir(run_dir)
    print(f"run_id      : {run_id}")
    print(f"chunk 来源  : {chunk_source}（章节 {len(slices)}，evidence {len(evidence)}）")
    print(f"dataset_hash: {dataset_hash}")
    print(f"产物目录    : {run_dir}")
    print()
    print("映射结果：")
    for status, count in result.summary["match_status"].items():  # type: ignore[union-attr]
        print(f"  {status:12s} {count}")
    print(f"  映射完整度   {result.summary['mapping_coverage']:.4%}")
    print()
    print("判据档位：")
    for tier, count in result.summary["decision_tiers"].items():  # type: ignore[union-attr]
        print(f"  {tier:16s} {count}")

    print()
    print("按难度分列（只分列、不加权）：")
    for difficulty, counts in result.summary["per_difficulty"].items():  # type: ignore[union-attr]
        detail = "、".join(f"{status} {count}" for status, count in counts.items())
        print(f"  {difficulty:8s} {detail}")

    if problems:
        print()
        print("产物红线检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print()
    print("产物红线检查：通过（文件白名单 + 字符串长度上限）")

    if not args.no_review:
        rows = build_review_rows(result.records, evidence, slices)
        write_review(args.review_dir, rows, dataset_hash)
        print(f"人工复核件  : {args.review_dir}（含正文，不入 git）")

    if args.write_db:
        from sqlalchemy.orm import sessionmaker

        from omniread.pipelines.mapping.store import verify_mappings, write_mappings

        factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        written = write_mappings(
            factory,
            result.records,
            chunking_version=M0_PLACEHOLDER_V1.profile_id,
            tokenizer_id=M0_PLACEHOLDER_V1.tokenizer_id,
        )
        folded = len(result.records) - written
        print(
            f"已写入 chunk_mappings：{written} 行"
            + (f"（{len(result.records)} 条 evidence 按唯一 hash 折叠掉 {folded} 行）" if folded else "")
        )

        # 写完立刻重放校验：确认库里每一行都还指向一个完整包含该证据的 chunk。
        # 这是五元组主键唯一覆盖不到的失效面（chunker 算法或分词库变更会移动边界而不改键）。
        stale = verify_mappings(
            factory,
            [(item.chapter_id, item.content) for item in evidence],
            slices,
        )
        if stale:
            print(f"读时校验：{len(stale)} 行已过期（chunk 边界移动或改题残留），需 purge 后重映射")
            for item in stale[:5]:
                print(f"  - {item.evidence_hash[:12]}… {item.reason}")
            return 1
        print("读时校验：库内映射全部通过重放（指向的 chunk 仍完整包含对应证据）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
