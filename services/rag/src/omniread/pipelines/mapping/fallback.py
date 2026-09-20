"""映射的兜底路径：确定性判定不成立时，才把这条交给模型（M0-02 §6.2、§6.3）。

主路径是区间包含，走不到这里——本项目 357 条 evidence 全部由主路径解决。兜底存在的理由
是「改题或重导后可能出现转述式 evidence」：那时区间包含直接不成立，没有兜底就只能记 unmatched。

三条约束写在实现里，因为它们都是「不写就会静默出错」的地方：

- `temperature=0`（M0-04 §3）。批次映射要求同一输入同一结果，采样温度是唯一的随机源。
- **模型返回的 chunk_key 必须在候选集合内**。模型编造一个不存在的键是完全可能的，
  照单全收会让 `chunk_mappings` 指向一个不存在的 chunk，且这个错误在评测里表现为「未命中」，
  查不出根因。不在集合内即整条作废、退回 unmatched，并把原因写进 `overlap_reason`。
- 模型输出的 `reasoning`（若 provider 返回）**不进任何产物**：思维链会复述候选 chunk 正文，
  而 `eval/` 进 git。落盘的只有四字段。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace

from omniread.infrastructure.providers.base import (
    ChatMessage,
    ChatModel,
    ChatOptions,
    MapperCandidate,
    MapperModel,
    MapperResult,
)
from omniread.pipelines.mapping.prompt import render_mapping_prompt
from omniread.pipelines.mapping.types import (
    MATCH_LOW_CONF,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    MappingOutcome,
)

# 批次映射要可复现，采样温度必须是 0（M0-04 §3）。
MAPPER_TEMPERATURE = 0.0

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_REQUIRED_KEYS = ("matched_chunk_key", "confidence", "overlap_reason", "alternative_chunk_key")


class MapperParseError(ValueError):
    """模型输出不是可用的四字段 JSON。"""


class ChatMapperModel:
    """把问答模型适配成 mapper：渲染 prompt → `temperature=0` → 解析四字段 JSON。"""

    def __init__(self, chat: ChatModel, model_name: str | None = None) -> None:
        self._chat = chat
        self.model = model_name or chat.model

    async def map_evidence(
        self, evidence_content: str, candidates: Sequence[MapperCandidate]
    ) -> MapperResult:
        prompt = render_mapping_prompt(evidence_content, candidates)
        response = await self._chat.complete(
            [ChatMessage(role="user", content=prompt)],
            ChatOptions(temperature=MAPPER_TEMPERATURE),
        )
        return parse_mapper_output(response.text, model=self.model)


def parse_mapper_output(raw: str, *, model: str) -> MapperResult:
    """解析模型输出；**不**回显原文到异常里，避免语料随报错进日志。"""
    matched = _JSON_BLOCK_RE.search(raw)
    if matched is None:
        raise MapperParseError("输出里找不到 JSON 对象")
    try:
        payload = json.loads(matched.group(0))
    except json.JSONDecodeError as exc:
        raise MapperParseError(f"JSON 解析失败：{exc.msg}") from exc
    if not isinstance(payload, dict):
        raise MapperParseError("JSON 顶层不是对象")

    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise MapperParseError(f"缺少字段：{'、'.join(missing)}")

    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise MapperParseError("confidence 不是数值")
    reason = payload["overlap_reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise MapperParseError("overlap_reason 为空")

    return MapperResult(
        matched_chunk_key=_optional_str(payload["matched_chunk_key"]),
        confidence=float(confidence),
        overlap_reason=reason,
        alternative_chunk_key=_optional_str(payload["alternative_chunk_key"]),
        model=model,
    )


async def apply_fallback(
    outcomes: Sequence[MappingOutcome],
    evidence_texts: Sequence[str],
    candidate_lists: Sequence[Sequence[MapperCandidate]],
    mapper: MapperModel,
) -> list[MappingOutcome]:
    """对未命中的条目逐条调用兜底模型；已命中的原样返回。

    三个序列一一对应：`evidence_texts` 是证据原文，`candidate_lists` 是该条 evidence
    所在章的候选 chunk。原文**不在 `MappingOutcome` 里**——那个结构对应 `chunk_mappings`
    的落库行，刻意不带正文；让一个能装语料的类型流经产物写入器，迟早有人把它写进 `eval/`。

    单条失败**不中断整批**：记 unmatched 并保留原因——批次映射里一条 provider 抖动
    不该让另外几百条白跑，但失败必须留痕。
    """
    results: list[MappingOutcome] = []
    for outcome, text, candidates in zip(
        outcomes, evidence_texts, candidate_lists, strict=True
    ):
        if outcome.match_status == MATCH_MATCHED:
            results.append(outcome)
            continue
        results.append(await _map_one(outcome, text, candidates, mapper))
    return results


async def _map_one(
    outcome: MappingOutcome,
    evidence_content: str,
    candidates: Sequence[MapperCandidate],
    mapper: MapperModel,
) -> MappingOutcome:
    keys = {candidate.chunk_key for candidate in candidates}
    if not candidates:
        return replace(
            outcome,
            match_status=MATCH_UNMATCHED,
            matched_chunk_key=None,
            confidence=0.0,
            overlap_reason="本章无候选 chunk，兜底路径无从选择",
            alternative_chunk_key=None,
        )

    try:
        result = await mapper.map_evidence(evidence_content, candidates)
    except Exception as exc:  # provider 抖动或输出不可解析：留痕，不静默
        return replace(
            outcome,
            match_status=MATCH_UNMATCHED,
            matched_chunk_key=None,
            confidence=0.0,
            overlap_reason=f"兜底映射失败（{type(exc).__name__}）：{_safe(exc)}",
            alternative_chunk_key=None,
            mapper_model=mapper.model,
        )

    if result.matched_chunk_key is None:
        return replace(
            outcome,
            match_status=MATCH_UNMATCHED,
            matched_chunk_key=None,
            confidence=0.0,
            overlap_reason=f"兜底模型判定无匹配：{_safe_text(result.overlap_reason)}",
            alternative_chunk_key=None,
            mapper_model=mapper.model,
        )

    # 模型编造键：整条作废，不落一个指向不存在 chunk 的映射。
    if result.matched_chunk_key not in keys:
        return replace(
            outcome,
            match_status=MATCH_UNMATCHED,
            matched_chunk_key=None,
            confidence=0.0,
            overlap_reason="兜底模型返回的 chunk_key 不在候选集合内，已作废",
            alternative_chunk_key=None,
            mapper_model=mapper.model,
        )

    alternative = result.alternative_chunk_key
    if alternative is not None and alternative not in keys:
        alternative = None

    return replace(
        outcome,
        match_status=MATCH_LOW_CONF if result.confidence < 0.5 else MATCH_MATCHED,
        matched_chunk_key=result.matched_chunk_key,
        confidence=float(result.confidence),
        overlap_reason=_safe_text(result.overlap_reason),
        alternative_chunk_key=alternative,
        mapper_model=mapper.model,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MapperParseError("chunk_key 不是字符串或 null")
    stripped = value.strip()
    return stripped or None


def _safe_text(text: str) -> str:
    return " ".join(text.split())[:200]


def _safe(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:200]
