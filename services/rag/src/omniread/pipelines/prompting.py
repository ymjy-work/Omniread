"""几条 prompt 共用的**模型可见文本**渲染。

改写与摘要都要把一段对话渲染成模型能读的文本。它看起来只是「拼几行字符串」，
但**格式本身就是模型看到的内容**——所以各 pipeline 的 `prompt_version` 必须把这些常量
一起算进 hash（判据是「是否改变模型可见文本」，不是「模板文件是否变化」）。
定义在一处，两个版本号才会跟着同一个格式一起变。

放这里而不是放在某一个 pipeline 里：改写与摘要是两条独立的链，谁 import 谁都会让
改一条链的时候看见另一条。
"""

from __future__ import annotations

from collections.abc import Sequence

from omniread.domain.models import HistoryMessage

SPEAKER_USER = "用户"

SPEAKER_ASSISTANT = "助手"

# 一条对话在模型可见文本里的形状。它不在模板文件里，因此必须单独进版本输入。
DIALOGUE_LINE = "【{speaker}】{content}"

DIALOGUE_SEPARATOR = "\n"

_SPEAKERS = {"user": SPEAKER_USER, "assistant": SPEAKER_ASSISTANT}

# 空输入时的占位句。正常路径到不了（改写没有历史就不跑、摘要的 messages 有 minItems:1），
# 但它是**模型可见文本**，所以同样进版本输入。
EMPTY_DIALOGUE = "（没有对话内容）"

# 各 pipeline 拼 `prompt_version` 输入时用同一个分隔符：避免「模板尾 + 格式头」凑出
# 与另一组合相同的字节串。
VERSION_INPUT_SEPARATOR = "\x00"


def render_dialogue(messages: Sequence[HistoryMessage]) -> str:
    """按时间顺序渲染一段对话，每条一行。"""
    if not messages:
        return EMPTY_DIALOGUE
    return DIALOGUE_SEPARATOR.join(
        DIALOGUE_LINE.format(speaker=_SPEAKERS[message.role], content=message.content)
        for message in messages
    )


__all__ = [
    "DIALOGUE_LINE",
    "DIALOGUE_SEPARATOR",
    "EMPTY_DIALOGUE",
    "SPEAKER_ASSISTANT",
    "SPEAKER_USER",
    "VERSION_INPUT_SEPARATOR",
    "render_dialogue",
]
