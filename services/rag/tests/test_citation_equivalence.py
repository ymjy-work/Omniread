"""引用正则的三方等价守卫：权威定义 ↔ Python 实现 ↔ TS 实现。

引用正则在「评测 runner / 客户端渲染 / schema 校验」三处共用同一份口径，但 Python 与
TypeScript 无法共用同一个文件，所以实现各写各的、口径只有一份：仓库根
`citation-format.json`。本测试拿定义里的同一批样本同时喂给两侧，断言：

1. Python 侧声明的正则源码与定义逐字相同；
2. Python 侧的识别结果与定义里的期望值一致；
3. TS 侧（`web/scripts/citation-samples.ts`，跑的是 `web/src/citation.ts`）在同样本上
   识别出的引用集合与违规集合，与 Python 侧完全一致。

第 3 条是必需的：正则在两个语言里各自实现，只有行为比对能发现漂移。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from omniread.domain.citation import (
    CANDIDATE_PATTERN,
    CITATION_PATTERN,
    find_citations,
    find_violations,
)


def _repository_root() -> Path:
    """向上找到仓库根：以 `contracts/openapi/` 为锚（与契约等价性测试同一套定位法）。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "contracts" / "openapi" / "frontend-api-v1.yaml").is_file():
            return parent
    raise RuntimeError("向上找不到 contracts/openapi/frontend-api-v1.yaml，无法定位仓库根")


ROOT = _repository_root()
DEFINITION_PATH = ROOT / "citation-format.json"
TS_RUNNER = ROOT / "web" / "scripts" / "citation-samples.ts"


def _load_definition() -> dict[str, Any]:
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def _python_view(text: str) -> dict[str, Any]:
    """把 Python 侧结果收敛成与样本期望、TS runner 输出同形的结构。"""
    return {
        "citations": [
            {"chapter_index": hit.chapter_index, "text": hit.text} for hit in find_citations(text)
        ],
        "violations": find_violations(text),
    }


def test_definition_matches_python_impl() -> None:
    definition = _load_definition()
    assert definition["pattern"] == CITATION_PATTERN
    assert definition["candidate_pattern"] == CANDIDATE_PATTERN

    for sample in definition["samples"]:
        expected = {"citations": [], "violations": sample["violations"]}
        expected["citations"] = [
            {"chapter_index": index, "text": f"[C{index}]"} for index in sample["citations"]
        ]
        assert _python_view(sample["text"]) == expected, f"样本 {sample['name']} 与期望不符"


def test_python_and_typescript_agree_on_samples() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("PATH 里没有 node，跳过与 TS 实现的行为比对")

    definition = _load_definition()
    completed = subprocess.run(
        [node, str(TS_RUNNER), str(DEFINITION_PATH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, f"TS runner 退出码 {completed.returncode}：{completed.stderr}"

    ts_output = json.loads(completed.stdout)
    assert ts_output["pattern"] == CITATION_PATTERN
    assert ts_output["candidate_pattern"] == CANDIDATE_PATTERN

    ts_by_name = {sample["name"]: sample for sample in ts_output["samples"]}
    samples = definition["samples"]
    assert len(ts_by_name) == len(samples), "TS runner 漏跑了样本"

    for sample in samples:
        expected = _python_view(sample["text"])
        assert ts_by_name[sample["name"]]["citations"] == expected["citations"], (
            f"样本 {sample['name']}：引用集合两侧不一致"
        )
        assert ts_by_name[sample["name"]]["violations"] == expected["violations"], (
            f"样本 {sample['name']}：违规集合两侧不一致"
        )
