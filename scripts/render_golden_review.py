#!/usr/bin/env python
"""生成 Golden 逐题复核件，供 Ready Gate 第 2、3 条人工签认（M0-04 §2.3）。

第 2 条要复核「类型 / 难度 / progress / expect_refusal」，第 3 条要确认
「`reference_points` 与 `reference_answer` 已重构完成」。这两条都没有机器判据，
但**复核件本身可以是可判的**：把每题的这六个字段摊平到一页，复核人不必逐个打开
86 个 JSON。

产物落 `temp/golden-review/questions.md`（含题面与参考答案，**不入 git**）。

用法（仓库根执行，不需要凭据）：
    python scripts/render_golden_review.py
    python scripts/render_golden_review.py --focus past   # 只看 level=past 的题
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = REPO_ROOT / "eval" / "golden"
DEFAULT_OUT = REPO_ROOT / "temp" / "golden-review"

_SKIP = {"schema.json", "example.json"}


def load(golden_dir: pathlib.Path) -> list[dict]:
    questions = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(golden_dir.glob("*.json"))
        if path.name not in _SKIP
    ]
    return sorted(questions, key=lambda q: q["id"])


def render(questions: list[dict], dataset_hash: str, focus: str | None) -> str:
    shown = [
        q for q in questions if focus is None or ("past" if q["level"] == "past" else "full") == focus
    ]
    by_type: dict[str, list[dict]] = {}
    for question in shown:
        by_type.setdefault(question["type"], []).append(question)

    difficulty = Counter(q["difficulty"] for q in shown)
    levels = Counter(q["level"] for q in shown)
    refusals = sum(1 for q in shown if q["expect_refusal"])

    lines = [
        "# Golden 逐题复核（Ready Gate 第 2、3 条）",
        "",
        f"- dataset_hash：`{dataset_hash}`",
        f"- 复核 {len(shown)} / {len(questions)} 题"
        + (f"（筛选：level={focus}）" if focus else ""),
        "",
        "## 要你判的四个字段",
        "",
        "| 字段 | 判什么 |",
        "| --- | --- |",
        "| `type` | 六桶归类对不对：`fact` 事实 / `alias` 别称 / `cross` 跨章 / `foreshadow` 伏笔 / `boundary` 边界 / `spoiler` 剧透 |",
        "| `difficulty` | `easy` / `medium` / `hard` 的档位是否合理 |",
        "| `level` + `progress` | `past` 的 progress 是否卡在「答案已在域内、剧透尚在域外」的位置；`full` 必须无 progress |",
        "| `expect_refusal` | 为 `true` 时，域内**确实没有答案**（不能把「我没找到」当拒答题） |",
        "",
        "第 3 条另需确认：`reference_points` 与 `reference_answer` 与题面匹配、且是重构后的版本。",
        "",
        f"分布：难度 {dict(sorted(difficulty.items()))}；"
        f"level {dict(sorted(levels.items()))}；拒答 {refusals} 题。",
        "",
    ]

    for question_type in sorted(by_type):
        items = by_type[question_type]
        lines.extend([f"## {question_type}（{len(items)} 题）", ""])
        for question in items:
            lines.extend(_render_question(question))
    return "\n".join(lines)


def _render_question(question: dict) -> list[str]:
    level = question["level"]
    scope = (
        f"`level=past` progress **{question['progress']}**"
        if level == "past"
        else "`level=full`（无 progress）"
    )
    refusal = "**expect_refusal = true**" if question["expect_refusal"] else "expect_refusal = false"
    evidence_count = sum(len(group) for group in question["must_cite_groups"])

    lines = [
        f"### {question['id']}　`{question['difficulty']}`　{scope}　{refusal}",
        "",
        f"**问：**{question['question']}",
        "",
    ]
    if question.get("reference_answer"):
        lines.extend(["**参考答案：**", "", question["reference_answer"], ""])
    points = question.get("reference_points") or []
    if points:
        lines.append("**评分点：**")
        lines.extend(f"- {point}" for point in points)
        lines.append("")

    groups = question["must_cite_groups"]
    lines.append(f"**必须引用**（{len(groups)} 组 AND、共 {evidence_count} 条 evidence）：")
    for index, group in enumerate(groups, start=1):
        chapters = "、".join(sorted({item["chapter_id"].rsplit(":", 1)[-1] for item in group}))
        lines.append(f"- 第 {index} 组（任一条命中即可，第 {chapters} 章，{len(group)} 条）")
    lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden 逐题复核件")
    parser.add_argument("--golden-dir", type=pathlib.Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--focus", choices=["past", "full"], default=None)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))
    from omniread.pipelines.mapping.runner import golden_dataset_hash

    questions = load(args.golden_dir)
    dataset_hash = golden_dataset_hash(args.golden_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "questions.md"
    target.write_text(
        render(questions, dataset_hash, args.focus), encoding="utf-8", newline="\n"
    )
    print(f"题目 {len(questions)} 道；dataset_hash {dataset_hash[:16]}…")
    print(f"复核件：{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
