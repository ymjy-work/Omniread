"""评测产物的数据形状（M0-04 §5，M0-02 §7.1）。

每条逐题记录都是一个 **frozen dataclass**，字段集即允许进 git 的全部内容。
这不是风格选择：`eval/` 进 git，红线由「字段白名单 + 拒绝未知字段」实现，
而不是靠「实现者别写错」。散文表格约束不了任何东西——`M0-02` §7.1 对
`retrieval.scores.jsonl` 只写了「question_id + 指针 + 指标值」，
任何 runner 都能多写一个字段把正文带进去，唯一的闸门就只剩 500 字符长度检查。

**逐阶段指针不截断**（`M0-02` §8.7）：截断会让排名超出截断线的候选无法区分
「未召回」与「被截掉」，而这两件事的处置完全不同。指针是 chunk_key，
短且不含正文，全量列出不触红线。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalScoreRecord:
    """检索层逐题记录；`retrieval.scores.jsonl` 的一行。"""

    question_id: str
    question_type: str
    difficulty: str
    level: str
    # `level=full` 时为 None（schema 要求该键缺省）。
    progress: int | None
    expect_refusal: bool

    # ── 指标（全部标量，聚合时代数运算即可）──
    # 命中判定一律以 assembled 为准（M0-04 §5.1）：只有真正进入 prompt 的段才算命中。
    must_cite_hit: bool  # 组内 OR、组间 AND 全中
    groups_total: int
    groups_hit: int
    evidence_total: int
    evidence_hit: int
    # 映射成功的 evidence 数。与 evidence_total 的差即「没映射上」，
    # 单列出来是为了让分母不随映射结果塌缩（M0-02 §6.2）。
    evidence_mapped: int
    all_evidence_hit: bool  # 组内亦取 AND 的最严口径
    chapter_recall_hit: bool  # 兜底诊断：证据所在章是否出现在 assembled

    # ── 泄漏：逐阶段统计，任一阶段 >0 即红（M0-02 §8.7）──
    leak_dense: int
    leak_kw: int
    leak_fused: int
    leak_rerank: int
    leak_assembled: int

    # ── 指针：逐阶段完整、不截断 ──
    dense_keys: tuple[str, ...]
    kw_keys: tuple[str, ...]
    fused_keys: tuple[str, ...]
    rerank_keys: tuple[str, ...]
    assembled_keys: tuple[str, ...]
    # 被裁项，形如 `reason:chunk_key`；reason 是装配器的枚举字面量，不是自由文本。
    dropped: tuple[str, ...]
    # 映射到、但没进 assembled 的 chunk_key —— 「被截掉」的那批，失败定位用。
    mapped_not_assembled_keys: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RetrievalScoreRecord:
        """从 `retrieval.scores.jsonl` 的一行还原。

        JSON 没有元组，指针列读回来是 list；直接塞进 frozen dataclass 会让再次
        `asdict` 出来的形状与首次落盘时不同。哪些字段是元组由注解本身决定，
        不另维护一份名单——新加元组字段时不会漏。
        """
        data: dict[str, Any] = dict(payload)
        for item in fields(cls):
            if not str(item.type).startswith("tuple[") or item.name not in data:
                continue
            value = data[item.name]
            # 必须是「字符串序列」。只写 `tuple(value)` 的话，一个误写成字符串的
            # 指针列会被拆成一串单字符元组：不报错，下游 `set(record.rerank_keys)`
            # 也照样跑，只是判定悄悄变错（`_failure_stage` 会把「装配截掉」判成
            # 「根本没召回」）。这种错不会以异常的形式出现，所以要在这里拦住。
            if not isinstance(value, (list, tuple)) or not all(
                isinstance(element, str) for element in value
            ):
                raise ValueError(
                    f"{item.name} 应为字符串列表，收到 {type(value).__name__}"
                )
            data[item.name] = tuple(value)
        return cls(**data)

    @property
    def leak_total(self) -> int:
        return (
            self.leak_dense
            + self.leak_kw
            + self.leak_fused
            + self.leak_rerank
            + self.leak_assembled
        )
