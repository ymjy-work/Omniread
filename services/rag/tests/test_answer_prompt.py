"""答案 prompt 单测：模板全文、消息组装、`prompt_version` 的稳定性与内容敏感性。

模板以仓库内文件 `answering/prompts/answer.md` 存在；这里直接读真实文件，顺便校验
它确实包含验收要求的四条纪律。
"""

from __future__ import annotations

import pytest

from omniread.infrastructure.providers.base import ChatMessage
from omniread.pipelines.answering import (
    PROMPT_VERSION_LENGTH,
    ContextPassage,
    answer_prompt_version,
    build_answer_messages,
    load_answer_prompt,
    parse_answer_prompt,
    prompt_version,
    read_answer_template,
)
from omniread.pipelines.answering.refusal import REFUSAL_MARKER

PASSAGES = [
    ContextPassage(chapter_index=17, text="政近在机场对艾莉说了那番话。"),
    ContextPassage(chapter_index=45, text="艾莉把围巾还了回去。"),
]


def test_template_file_carries_the_required_disciplines() -> None:
    prompt = load_answer_prompt()

    assert "只使用用户问题中提供的材料作答" in prompt.system
    assert "不得使用材料之外的知识" in prompt.system
    assert "[C17]" in prompt.system
    assert "不得写成 Markdown 链接" in prompt.system
    # 拒答走结构化标记，不靠模型自述那句话——话术由服务端填。
    # 标记的另一半真相源是 `refusal.REFUSAL_MARKER`，两边对不上就是口径分叉的开始。
    assert REFUSAL_MARKER in prompt.system


def test_prompt_version_is_the_short_hash_of_the_template_text() -> None:
    text = read_answer_template()

    assert answer_prompt_version() == prompt_version(text)
    assert len(answer_prompt_version()) == PROMPT_VERSION_LENGTH
    assert load_answer_prompt().version == answer_prompt_version()


def test_prompt_version_is_stable_and_follows_content() -> None:
    text = read_answer_template()
    changed = text.replace("[C17]", "[C18]")

    assert prompt_version(text) == prompt_version(text)
    assert prompt_version(text) != prompt_version(changed)


def test_build_messages_puts_discipline_in_system_and_material_in_user() -> None:
    messages = build_answer_messages("政近为什么离开周防家？", PASSAGES)

    assert [message.role for message in messages] == ["system", "user"]
    system, user = messages
    assert "只依据" in system.content or "只使用" in system.content
    # material 块按入参顺序渲染，问题最后出现。
    assert user.content.index("【第 17 章】") < user.content.index("【第 45 章】")
    assert "政近在机场对艾莉说了那番话。" in user.content
    assert user.content.index("【第 45 章】") < user.content.index("政近为什么离开周防家？")


def test_build_messages_renders_a_placeholder_for_empty_material() -> None:
    _, user = build_answer_messages("问题", [])

    assert "本次没有可用材料" in user.content
    assert "问题" in user.content


def test_render_context_keeps_every_passage() -> None:
    prompt = load_answer_prompt()
    rendered = prompt.render_user("问题", PASSAGES)

    assert "【第 17 章】\n政近在机场对艾莉说了那番话。" in rendered
    assert "【第 45 章】\n艾莉把围巾还了回去。" in rendered
    assert "{{CONTEXT}}" not in rendered
    assert "{{QUESTION}}" not in rendered


def test_parse_rejects_missing_section_or_placeholder() -> None:
    with pytest.raises(ValueError):
        parse_answer_prompt("<user>\n{{CONTEXT}} {{QUESTION}}\n</user>")
    with pytest.raises(ValueError):
        parse_answer_prompt("<system>纪律</system>\n<user>只有材料没有占位符</user>")


# ── 多轮：摘要与近轮的插入位置──


def test_multi_turn_order_is_fixed() -> None:
    """固定顺序：system → 会话摘要 → 近轮对话 → 本轮装配集 + 当前问题。

    顺序错了不会报错，只会让模型看到一段顺序不对的对话——而「这轮回答怎么扯到别处去了」
    是最难倒查的那类症状。
    """
    messages = build_answer_messages(
        "那她后来呢？",
        PASSAGES,
        summary="前情：政近离开了周防家。",
        history=[
            ChatMessage(role="user", content="政近为什么离开？"),
            ChatMessage(role="assistant", content="因为家里出了事[C17]。"),
        ],
    )

    assert [message.role for message in messages] == [
        "system",
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1].content == "前情：政近离开了周防家。"
    assert messages[2].content == "政近为什么离开？"
    assert messages[3].content == "因为家里出了事[C17]。"
    # 本轮的问题与装配集仍在最后那一条 user 里，历史在它之前。
    assert "那她后来呢？" in messages[-1].content
    assert "【第 17 章】" in messages[-1].content


def test_single_turn_is_still_exactly_two_messages() -> None:
    """没有历史也没有摘要时，输出与「只有 system / user 两段」逐字节相同。

    86 题评测走的正是这条路——只要它逐字节不变，答案层的基线就仍然可比。
    """
    prompt = load_answer_prompt()
    messages = build_answer_messages("问题", PASSAGES)

    assert [message.role for message in messages] == ["system", "user"]
    assert messages[0].content == prompt.system
    assert messages[1].content == prompt.render_user("问题", PASSAGES)


def test_context_rides_as_data_without_adding_any_framing_text() -> None:
    """摘要与历史只作为**数据**进消息，没有引入新的固定文本——所以 `prompt_version` 不变。

    这条钉的是「没有中间层」：一旦有人给摘要加一句「【会话摘要】」这样的段头，
    模型可见文本就变了，而 `prompt_version` 只吃模板与渲染格式常量，**不会跟着变**——
    于是两份不同的 prompt 在 run 记录里并列成同一个版本，两边都不报错。
    加段头就必须同时把它并进 `prompt_version` 的输入。
    """
    before = answer_prompt_version()
    messages = build_answer_messages(
        "问题",
        PASSAGES,
        summary="摘要原文",
        history=[ChatMessage(role="user", content="上一问原文")],
    )

    assert messages[1].content == "摘要原文"
    assert messages[2].content == "上一问原文"
    assert answer_prompt_version() == before
