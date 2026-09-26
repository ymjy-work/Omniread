#!/usr/bin/env python
"""离线重算评测 run 的汇总产物：不连库、不调模型、零费用。

`summary.json` / `summary.md` / `failures.md` 都是 `retrieval.scores.jsonl` 的
**确定性函数**，所以改口径时不必重跑检索——重跑要再花一遍真实调用，还会把同一个
`run_id` 的数字换成另一次采样的结果，那样两次口径就再也分不开了。

**逐题记录本身不改写**：它是这次 run 的证据，汇总只是它的一种读法。所以这里
不把 records 传给 `write_eval_run_dir`。

落盘前有三道闸门，都是为了让「重算」不会在用户不知情时改坏一个已落盘的 run：

1. **题数闸门**。逐题记录没被改过，汇总的题数就不该变。变了几乎只有一种可能：
   `retrieval.scores.jsonl` 被截断或换过。照写会得到一份题数更少、数字看着
   仍然合理的汇总，而退出码与红线检查都报成功。确实要按当前记录重算，
   得显式加 `--allow-question-count-change`。
2. **config.json 键集闸门**。`write_eval_run_dir` 会**无条件**重写 config.json
   （与传不传 records 无关）。产物里出现本版本不认识的键即拒绝——那说明产物比代码新。
   反过来，产物**缺**字段是正常的：新加的字段带默认值，旧的 run 自然没有它们。
   （不做「取值往返比对」：`EvalRunConfig(**payload)` 原样收下再原样吐回，那种比对恒真。）
3. **config.json 字节闸门**。值相同不代表字节相同（缩进、转义、外部手工编辑过的表示）。
   落盘后按字节核一遍，不同就还原——放在 `finally` 里，落盘中途抛错也会还原。

**一处已知限制**：`summary.md` 的头部是从内存里那份 config（= 产物 ∪ 代码默认值）渲染的，
它**没有**字节闸门（它本来就该被重写）。所以若将来给一个会被渲染的字段改默认值，
旧产物的 `summary.md` 头部会冒出那个新默认值，而 config.json 已被还原、两者对不上。
今天不可达：带默认值且被渲染的字段只有 `trust_note`，其默认值是空串、渲染时整段跳过。


用法（仓库根执行）：

    python scripts/resummarize_eval.py --run-id 2026-09-20-m0-baseline --dry-run
    python scripts/resummarize_eval.py --run-id 2026-09-20-m0-baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from omniread.pipelines.evaluation.artifacts import (  # noqa: E402
    EvalRunConfig,
    write_eval_run_dir,
)
from omniread.pipelines.evaluation.metrics import aggregate, summarize_counts  # noqa: E402
from omniread.pipelines.evaluation.runner import failure_rows  # noqa: E402
from omniread.pipelines.evaluation.types import RetrievalScoreRecord  # noqa: E402
from omniread.pipelines.mapping.artifacts import check_run_dir  # noqa: E402
from omniread.pipelines.mapping.runner import DEFAULT_RUNS_DIR  # noqa: E402

_HEADLINE = (
    "question_count",
    "evidence_recall",
    "evidence_total",
    "evidence_mapped",
    "leak",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线重算评测 run 的汇总产物")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true", help="只打印新旧差异，不落盘")
    parser.add_argument(
        "--allow-question-count-change",
        action="store_true",
        help="允许重算出的题数与已落盘 summary 不一致时仍然落盘（默认拒绝）",
    )
    return parser.parse_args(argv)


def load_config(run_dir: Path) -> EvalRunConfig:
    """读回配置快照，并钉住「往返一致」——不一致就拒绝覆盖。"""
    path = run_dir / "config.json"
    if not path.is_file():
        raise SystemExit(f"找不到配置快照：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    known = {item.name for item in fields(EvalRunConfig)}
    if unknown := sorted(set(payload) - known):
        raise SystemExit(
            f"config.json 里有本版本不认识的字段 {unknown}——产物比代码新，先更新代码再重算"
        )
    try:
        config = EvalRunConfig(**payload)
    except TypeError as exc:
        raise SystemExit(
            f"config.json 与本版本的 EvalRunConfig 对不上：{exc}\n"
            "  拒绝继续：照当前默认值补字段会把这次 run 的参数快照改掉。"
        ) from exc
    # 这里**不做**「往返一遍比对取值」：那是个恒真的检查，写了等于没写。
    # `EvalRunConfig(**payload)` 把 payload 的值原样收下（dataclass 不做类型转换，
    # 也没有 `__post_init__`），`asdict` 再原样吐回，所以「已记录的字段被换成了别的值」
    # 根本不可能被这道检查发现——它真正拦得住的只有「payload 缺键」，而缺键在新字段
    # 带默认值之后本就是正常的（旧产物没有生成层那几个字段）。
    #
    # 于是 config.json 只剩两道**各自有效**的闸门：
    #   1. 键集闸门（上面）：payload 出现本版本不认识的键 → 拒绝，产物比代码新；
    #   2. 字节闸门（main 里）：落盘后逐字节比对并还原，一个字节都不许动。
    return config


def load_records(run_dir: Path) -> tuple[RetrievalScoreRecord, ...]:
    path = run_dir / "retrieval.scores.jsonl"
    if not path.is_file():
        raise SystemExit(f"找不到逐题记录：{path}")
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not rows:
        raise SystemExit(f"{path} 是空的——没有记录可重算，不做「汇总成 0 题」这种事")
    return tuple(RetrievalScoreRecord.from_payload(row) for row in rows)


def _brief(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 240 else f"{text[:237]}..."


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.runs_dir / args.run_id
    if not run_dir.is_dir():
        raise SystemExit(f"run 目录不存在：{run_dir}")

    config = load_config(run_dir)
    records = load_records(run_dir)
    summary = aggregate(records)
    summary["failure_counts"] = summarize_counts(records)
    failures = failure_rows(records)

    old_path = run_dir / "summary.json"
    old: dict[str, Any] = (
        json.loads(old_path.read_text(encoding="utf-8")) if old_path.is_file() else {}
    )

    print(f"run_id  : {config.run_id}")
    print(f"逐题记录 : {len(records)} 条")
    print()
    print("=== 汇总字段差异（≠≠ 为变化项）===")
    changed = 0
    for key in sorted(set(old) | set(summary)):
        before, after = old.get(key), summary.get(key)
        if before == after:
            print(f"  =  {key}")
            continue
        changed += 1
        print(f"  ≠≠ {key}")
        print(f"       旧 {_brief(before)}")
        print(f"       新 {_brief(after)}")
    print(f"（变化 {changed} 个字段）")

    print()
    print("=== 头条指标 ===")
    for key in _HEADLINE:
        if key in summary:
            print(f"  {key:32s} {summary[key]}")
    print(f"  {'failures 条数':32s} {len(failures)}")

    if args.dry_run:
        print()
        print("--dry-run：未落盘。")
        return 0

    # 逐题记录没被改过，汇总的题数就不该变。变了几乎只有一种可能：产物被截断或换过。
    # 照写就会用一份题数不同的汇总覆盖掉已落盘的 run，而退出码与红线检查全都报成功——
    # 那样「在用户不知情时改坏一个已落盘的 run」正是这个工具最该防住的事。
    old_count = old.get("question_count")
    new_count = summary["question_count"]
    if old_count is not None and old_count != new_count:
        brief = (
            f"逐题记录条数对不上：summary.json 记的是 {old_count}，"
            f"retrieval.scores.jsonl 读出来 {new_count}。"
        )
        if not args.allow_question_count_change:
            raise SystemExit(
                f"{brief}\n"
                "  拒绝落盘：照写会用一份题数不同的汇总覆盖掉已落盘的 run。\n"
                "  确认要按当前记录重算，再加 --allow-question-count-change。"
            )
        print(f"警告：{brief}（--allow-question-count-change 已给出，继续）")

    # `write_eval_run_dir` 会顺手重写 config.json，这一步与传不传 records 无关。
    # 内容已由上面的往返守卫保证是同一份，这里再按字节复核并还原：已落盘 run 的
    # 参数快照不该因为一次重算而动，哪怕只是缩进或转义被规范化了。
    config_path = run_dir / "config.json"
    config_bytes = config_path.read_bytes()

    # 只写 summary 与 failures；records 不传，逐题记录原样保留。
    #
    # 还原放在 `finally` 里：`write_eval_run_dir` 在写完 config.json 之后还可能抛错
    # （超长字段、渲染异常），那时若不还原，磁盘上就留下一份「参数快照被悄悄加上
    # 新默认字段」的半成品，而这次运行看起来是失败的、没人会去查它。
    try:
        write_eval_run_dir(run_dir, config=config, summary=summary, failures=failures)
    finally:
        if config_path.read_bytes() != config_bytes:
            config_path.write_bytes(config_bytes)
            print(f"注意：config.json 被重写且字节有变化，已还原为原内容：{config_path}")

    print()
    print(f"已重写：{old_path}")
    print(f"        {run_dir / 'summary.md'}")
    print(f"        {run_dir / 'failures.md'}")

    if problems := check_run_dir(run_dir):
        print()
        print("产物红线检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("产物红线检查：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
