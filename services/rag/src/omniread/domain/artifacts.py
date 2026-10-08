"""`eval/` 产物的入库红线（M0-02 §7.1）。

`eval/` 进 git，一段正文 push 出去就只能重写历史。红线由两半组成，**两半都要**：

- **字段白名单**（结构性）：每类产物用一个 frozen dataclass 定死字段集，字段外一律拒绝。
  这是主防线——它管的是「不该出现的东西根本没地方写」。
- **长度上限**（兜底）：任一字符串字段 ≤ 500 字符（M0-02 §7.1 的 CI 口径）。

长度上限**不能单独承担防线**：它拦的是「整段整章搬运」，拦不住一段三百字的自由文本。
产物里唯一可能夹带正文的是映射侧的自由文本列（`overlap_reason`），它另有截断压平。

本模块只放不依赖具体产物的规则；各产物自己的字段集在各自的 `artifacts.py` 里定。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# M0-02 §7.1：CI 检查 JSONL 内任一字符串字段长度上限 500 字符，超限即视为夹带了正文。
MAX_STRING_FIELD = 500

# 自由文本列（模型产出的理由、解释）再收紧一档。截断只是收敛、不是内容控制——
# 真要禁止正文进入该列，只能靠「不让模型产出自由文本」或字段白名单。
MAX_FREE_TEXT_CHARS = 200

# run 目录**只准**出现这些文件。多出来的文件（debug.txt、raw/、请求响应 dump、
# 某个库自己在 cwd 落的缓存）都不受任何字段规则约束，是整章语料入库最现实的路径，
# 所以以「白名单 + 目录校验」来管。
ALLOWED_RUN_FILES = frozenset(
    {
        "config.json",
        "summary.json",
        "summary.md",
        "retrieval.scores.jsonl",
        "generation.scores.jsonl",
        "mappings.jsonl",
        "mapping_failures.jsonl",
        "failures.md",
    }
)


class ArtifactRedlineError(ValueError):
    """产物违反入库红线：字段超长、出现正文、或目录里有白名单外的文件。"""


def clamp_text(text: str, limit: int = MAX_FREE_TEXT_CHARS) -> str:
    """压平自由文本：换行折成空格、按上限截断。

    模型可能把它看到的原文粘进理由里，截断是这里唯一能做的确定性收敛。
    """
    return " ".join(text.split())[:limit]


def check_strings(
    name: str, payload: Any, index: int = 0, prefix: str = ""
) -> list[str]:
    """递归检查任一字符串字段是否超长；返回问题清单（空即通过）。

    必须递归：JSONL 的一行里可能有嵌套对象与数组，候选列表天然是数组，
    长正文能藏在元素里逃过只查顶层的检查。
    """
    problems: list[str] = []
    if isinstance(payload, str):
        if len(payload) > MAX_STRING_FIELD:
            problems.append(
                f"{name}[{index}]{prefix} 字符串长度 {len(payload)} 超上限 {MAX_STRING_FIELD}"
            )
    elif isinstance(payload, Mapping):
        for key, value in payload.items():
            problems.extend(check_strings(name, value, index, f"{prefix}.{key}"))
    elif isinstance(payload, Iterable) and not isinstance(payload, (bytes, bytearray)):
        for position, value in enumerate(payload):
            problems.extend(check_strings(name, value, index, f"{prefix}[{position}]"))
    return problems


def guard_payload(name: str, payload: Any) -> None:
    """写盘前守卫：超长即抛，坏产物不落盘。"""
    problems = check_strings(name, payload)
    if problems:
        raise ArtifactRedlineError("；".join(problems))


def check_markdown(path_name: str, text: str) -> list[str]:
    """Markdown 不受 JSONL 长度检查的结构保护，单独兜一道。

    逐行查上限只是「不让单行超长」，**不能**阻止把一段回答折成多行写进去；
    所以调用方必须从源头限制 markdown 只写指针与计数，不写自由文本段。
    """
    return [
        f"{path_name}:{number} 单行超过 {MAX_STRING_FIELD} 字符"
        for number, line in enumerate(text.splitlines(), start=1)
        if len(line) > MAX_STRING_FIELD
    ]
