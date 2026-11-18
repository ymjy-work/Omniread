from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.db.models import Chunk

SYSTEM_PROMPT_PLACEHOLDER = (
    "你是 Omniread 的阅读助手，帮助读者理解正在阅读的小说。"
    "你的任务是依据提供的原文证据回答问题，而不是讲述记忆中的剧情或自行推断后续发展。\n\n"
    "回答规则：\n"
    "1. 只使用下方证据块中出现的信息作答；证据没有写到的内容一律不补充、不推测、不编造。\n"
    "2. 需要标注来源的句子，在句末紧接输出 `[[chunk:ID]]`，ID 只能取自证据块的 "
    "<evidence id=\"...\">。多个来源可连续标注，例如 `[[chunk:12]][[chunk:15]]`；"
    "不得编造 id，也不得引用未列出的章节。\n"
    "3. 证据不足以支撑回答，或只能提供背景而无法回答问题的核心事实（如具体顺序、结果、"
    "人物身份、数字等）时，必须只回复「根据已读内容无法回答。」；"
    "不得用「未提及」「文中没有」等方式作答，也不得给出部分背景或推测。\n"
    "4. past 模式下只能依据阅读进度之前的章节，不得透露进度之后才发生的情节、人物结局或反转；"
    "full 模式可依据全书内容。无论哪种模式，都不要超出证据本身进行延伸。\n"
    "5. 用简洁、自然的中文小说阅读语境作答，直接回应用户所问；不复述无关剧情，"
    "不堆砌原文，不做与问题无关的长篇总结。\n"
    "6. 如果问题与本书无关，或证据与问题并不匹配，同样按第 3 条拒答。\n"
    "7. 正文中不要用「证据 505」「chunk N」等内部编号指代来源，只用自然语言说明；"
    "引用信息只通过句末的 `[[chunk:ID]]` 标记给出。回答保持简洁，不复述大段原文。\n"
    "8. 涉及人物姓氏、全名或人物关系时，必须严格按 evidence 原文表述，"
    "不得自行配对、补全或加括号解释；不确定就省略。"
)
USER_PROMPT_PLACEHOLDER = (
    "下面是与问题相关的原文证据片段，每块都带有 id、所属章节和标题。"
    "请先通读证据，确认其中是否有足够信息回答问题，再依据证据组织答案；"
    "不要依赖证据之外的知识。"
)
EVIDENCE_HEADER_PLACEHOLDER = (
    "证据块格式：<evidence id=\"chunk 的整数 id\" chapter_id=\"章节 id\" "
    "chapter_index=\"章节序号\" title=\"章节标题\">，标签内为原文片段；"
    "引用时使用 id 的数值。"
)

CITATION_PROTOCOL = (
    "引用协议：只能引用下方证据块给出的 id；在需要标注来源的句子末尾输出 "
    "`[[chunk:ID]]`，ID 必须是证据块中的整数 id。"
)


def build_evidence_block(chunk: Chunk) -> str:
    return (
        f"<evidence id=\"{chunk.id}\" chapter_id=\"{chunk.chapter_id}\" "
        f"chapter_index=\"{chunk.chapter_index}\" title=\"{chunk.title}\">\n"
        f"{chunk.text}\n"
        "</evidence>"
    )


def build_messages(question: str, chunks: list[Chunk]) -> list[BaseMessage]:
    evidence = "\n\n".join(build_evidence_block(chunk) for chunk in chunks)
    system = f"{SYSTEM_PROMPT_PLACEHOLDER}\n\n{CITATION_PROTOCOL}"
    human = (
        f"{USER_PROMPT_PLACEHOLDER}\n\n"
        f"{EVIDENCE_HEADER_PLACEHOLDER}\n\n"
        f"{evidence}\n\n"
        f"问题：{question}"
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]
