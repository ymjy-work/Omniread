from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.db.models import Chunk

SYSTEM_PROMPT_PLACEHOLDER = "[SYSTEM_PROMPT_PLACEHOLDER]"
USER_PROMPT_PLACEHOLDER = "[USER_PROMPT_PLACEHOLDER]"
EVIDENCE_HEADER_PLACEHOLDER = "[EVIDENCE_HEADER_PLACEHOLDER]"

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
