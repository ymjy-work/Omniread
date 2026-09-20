"""答案 prompt 单测：模板全文、消息组装、`prompt_version` 的稳定性与内容敏感性。

模板以仓库内文件 `answering/prompts/answer.md` 存在；这里直接读真实文件，顺便校验
它确实包含验收要求的四条纪律。
"""

from __future__ import annotations

import pytest

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

PASSAGES = [
    ContextPassage(chapter_index=17, text="政近在机场对艾莉说了那番话。"),
    ContextPassage(chapter_index=45, text="艾莉把围巾还了回去。"),
]


def test_template_file_carries_the_required_disciplines() -> None:
    prompt = load_answer_prompt()

    assert "只使用「材料」中明确写到的内容作答" in prompt.system
    assert "禁止使用材料之外的任何知识" in prompt.system
    assert "[C17]" in prompt.system
    assert "不得写成 Markdown 链接" in prompt.system
    assert "没有找到能回答这个问题的内容" in prompt.system


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
