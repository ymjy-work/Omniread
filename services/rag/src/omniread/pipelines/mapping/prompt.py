"""映射兜底路径的 prompt 与其版本（M0-02 §6.3）。

`mapper_prompt_version` 是 `chunk_mappings` 五元组主键的分量，改 prompt 即整体失效。
因此版本串必须覆盖**模型能看到的全部文本**——模板正文之外，还包括候选 chunk 的渲染格式
（键名怎么标、条目之间怎么分隔）。只哈希模板正文的话，把渲染格式从 `chunk_key: content`
改成 `content (chunk_key)` 这种改动不会换版本，旧映射会被静默复用。

确定性主路径不使用本模块（`NO_PROMPT_VERSION` 是它的占位取值）；
这里的存在只服务「evidence 不是原文精确子串」的兜底情形。
"""

from __future__ import annotations

from collections.abc import Sequence

from omniread.domain.text import sha256_hex
from omniread.pipelines.mapping.types import MapperCandidate

PROMPT_VERSION_LENGTH = 16

# 末行按源码宽度折成两段字面量拼接；拼出来的字符串与 M0-02 §6.3 的原文逐字一致。
MAPPING_PROMPT_TEMPLATE = (
    "你是一个精确的文本定位助手。给定一段证据文本和一组 chunk，"
    "找出与证据文本重叠度最高的 chunk。\n"
    "证据文本：{evidence_content}\n"
    "候选 chunk：{chunks_with_keys}\n"
    "请输出 JSON：matched_chunk_key / confidence / overlap_reason / alternative_chunk_key\n"
    "要求：只输出 JSON；confidence < 0.5 时必须提供 alternative；"
    "证据被多个 chunk 覆盖时选覆盖率最高的。\n"
)

# 候选 chunk 的渲染格式：每条一行 `chunk_key\t正文`。改这里必须换 prompt 版本——
# 它同样是模型可见文本，只是不在模板字符串里。
CANDIDATE_SEPARATOR = "\n"
CANDIDATE_FIELD_SEPARATOR = "\t"


def render_candidates(candidates: Sequence[MapperCandidate]) -> str:
    return CANDIDATE_SEPARATOR.join(
        f"{candidate.chunk_key}{CANDIDATE_FIELD_SEPARATOR}{candidate.content}"
        for candidate in candidates
    )


def render_mapping_prompt(
    evidence_content: str, candidates: Sequence[MapperCandidate]
) -> str:
    return MAPPING_PROMPT_TEMPLATE.format(
        evidence_content=evidence_content,
        chunks_with_keys=render_candidates(candidates),
    )


def mapper_prompt_version() -> str:
    """模板正文 + 渲染格式常量一起取哈希；任一处变即换版本。"""
    payload = CANDIDATE_SEPARATOR.join(
        (
            MAPPING_PROMPT_TEMPLATE,
            CANDIDATE_FIELD_SEPARATOR,
            CANDIDATE_SEPARATOR,
        )
    )
    return sha256_hex(payload)[:PROMPT_VERSION_LENGTH]


MAPPING_PROMPT_VERSION = mapper_prompt_version()
