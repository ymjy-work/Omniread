#!/usr/bin/env python
"""扫描 `eval/runs/` 下的全部 run 产物，核对入库红线（M0-02 §7.1）。

规格要求「CI 检查 JSONL 内任一字符串字段长度上限 500 字符」，但仓库里既没有 CI
也没有实现这条检查的脚本——本文件就是那个载体。

检查三件事，缺一不可：

1. **文件白名单**：run 目录只准出现 `ALLOWED_RUN_FILES` 里的文件，且不得有子目录。
   多出来的 `debug.txt`、`raw/`、请求响应 dump 都不受任何字段规则约束，
   是整章语料入库最现实的路径。
2. **字符串长度**：JSON / JSONL 内任一字符串字段 ≤ 500 字符，递归到嵌套对象与数组。
   长度限制防的是「整段整章搬运」——它拦不住 evidence 尺度的短片段，
   所以第 3 条不能省。
3. **正文兜底**（有语料时）：产物里不得出现任何一章正文的长片段。
   没有语料的环境（公共 CI）跳过这条并显式说明，不静默当作通过。

用法（仓库根执行）：
    python scripts/verify_artifacts.py
    python scripts/verify_artifacts.py --runs-dir eval/runs --min-overlap 60
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from omniread.pipelines.mapping.artifacts import check_run_dir  # noqa: E402

DEFAULT_CORPUS_ROOT = REPO_ROOT / "asset" / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
# 连续多少字符与语料重合即判为夹带正文。Golden 的 evidence 最长约百字，
# 取 60 能在不误伤短片段的前提下抓住「整段搬运」。
DEFAULT_MIN_OVERLAP = 60


def load_corpus_shingles(corpus_root: Path, width: int) -> set[int]:
    """把每章正文切成 width 字符的滑窗，返回其哈希集合，作为「这些文字来自语料」的判据。

    **逐字符滑动，不能用固定步长**：两侧都按 30 字符步长切的话，落在网格之间的片段
    永远对不上——把 200 字正文粘进产物、起点只要不是 30 的整数倍就有完整盲区，
    检查会一路报 OK。这是「机制看着在工作、其实测不到」的典型形态，所以两侧都按 1 滑动。

    存哈希而非字符串：语料约百万字符，逐字符滑窗存原文要吃几百 MB，
    存 int 只要几十 MB。哈希只在本进程内比对，不需要跨进程稳定。
    逐章独立切窗，不跨章拼接——否则会造出语料里并不存在的片段。
    """
    index_path = corpus_root / "index.jsonl"
    if not index_path.is_file():
        return set()
    shingles: set[int] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        text = json.loads(line)["text"]
        for start in range(len(text) - width + 1):
            shingles.add(hash(text[start : start + width]))
    return shingles


def scan_run(run_dir: Path, shingles: set[int], width: int) -> list[str]:
    problems = list(check_run_dir(run_dir))
    if not shingles:
        return problems
    for entry in sorted(run_dir.glob("*")):
        if not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8", errors="replace")
        hit = next(
            (
                start
                for start in range(len(text) - width + 1)
                if hash(text[start : start + width]) in shingles
            ),
            None,
        )
        if hit is not None:
            problems.append(
                f"{entry.name}: 第 {hit} 字符起有 {width} 字与语料逐字重合，判定为夹带正文"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eval/ 产物入库红线扫描")
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "eval" / "runs")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--min-overlap", type=int, default=DEFAULT_MIN_OVERLAP)
    args = parser.parse_args(argv)

    if not args.runs_dir.is_dir():
        print(f"没有 run 目录：{args.runs_dir}（尚未跑过评测，属正常）")
        return 0

    run_dirs = sorted(path for path in args.runs_dir.iterdir() if path.is_dir())
    if not run_dirs:
        print(f"{args.runs_dir} 下还没有 run（尚未跑过评测，属正常）")
        return 0

    shingles = load_corpus_shingles(args.corpus_root, args.min_overlap)
    if shingles:
        print(f"语料滑窗：{len(shingles)} 段（宽度 {args.min_overlap} 字符）")
    else:
        print(
            "NOTE 读不到仓库内语料，跳过「与语料比对」这一条；"
            "只校验文件白名单与字段长度。要完整校验请在含 asset/ 的环境运行。"
        )
    print()

    total = 0
    for run_dir in run_dirs:
        problems = scan_run(run_dir, shingles, args.min_overlap)
        if problems:
            total += len(problems)
            print(f"[FAIL] {run_dir.name}")
            for problem in problems:
                print(f"         {problem}")
        else:
            print(f"[ OK ] {run_dir.name}")

    print()
    if total:
        print(f"结果：不通过（{total} 处问题）。eval/ 进 git，产物一旦 push 只能重写历史。")
        return 1
    print(f"结果：通过（{len(run_dirs)} 个 run 目录）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
