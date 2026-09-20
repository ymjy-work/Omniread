"""`prompt_version` 必须覆盖**全部**模型可见文本，不只是模板文件。

M0-01 §5.5 的判据是「是否改变模型可见文本或判据」，不是「模板文件是否变化」。
材料段的标题格式、段间分隔与空材料占位句都写在 `prompt.py` 的代码里，
它们同样是模型看到的内容——漏掉任何一个，都会让「改了格式却不换版本」成立，
于是两份不同的 prompt 在 run 记录里并列成同一个版本。
"""

from __future__ import annotations

from typing import Any

import pytest

from omniread.pipelines.answering import prompt as prompt_module
from omniread.pipelines.answering.prompt import prompt_version

# 用固定字符串而不是真模板：这条测试只关心「代码侧常量是否进版本输入」，
# 与模板文件内容无关，这样模板以后怎么改都不会让这条测试失效。
_TEMPLATE = "占位模板"


@pytest.mark.parametrize(
    "constant",
    ["_PASSAGE_HEADER", "_PASSAGE_SEPARATOR", "_EMPTY_CONTEXT"],
)
def test_version_changes_when_render_format_changes(
    monkeypatch: pytest.MonkeyPatch, constant: str
) -> None:
    before = prompt_version(_TEMPLATE)
    original: Any = getattr(prompt_module, constant)
    monkeypatch.setattr(prompt_module, constant, original + "改")
    assert prompt_version(_TEMPLATE) != before, f"{constant} 变了但 prompt_version 没变"


def test_version_changes_when_template_changes() -> None:
    assert prompt_version("甲") != prompt_version("乙")


def test_version_is_stable_for_same_input() -> None:
    assert prompt_version(_TEMPLATE) == prompt_version(_TEMPLATE)
