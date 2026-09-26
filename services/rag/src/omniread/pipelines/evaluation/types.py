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

from collections.abc import Callable, Mapping
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
    evidence_total: int
    evidence_hit: int
    # 映射成功的 evidence 数。与 evidence_total 的差即「没映射上」，
    # 单列出来是为了让分母不随映射结果塌缩（M0-02 §6.2），
    # 也为了让「切片没对上」与「检索没召回到」分得开。
    evidence_mapped: int

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
        """从 `retrieval.scores.jsonl` 的一行还原。"""
        return cls(**_coerce_from_payload(cls, payload))

    @property
    def leak_total(self) -> int:
        return (
            self.leak_dense
            + self.leak_kw
            + self.leak_fused
            + self.leak_rerank
            + self.leak_assembled
        )


#: 注解词汇 → 取值检查。布尔是 `int` 的子类，所以 `int` / `float` 都要显式排掉 bool，
#: 否则 `True` 会被当成合法的整数收下。
_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "str": lambda value: isinstance(value, str),
    "int": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "bool": lambda value: isinstance(value, bool),
    "float": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
}

_OPTIONAL_SUFFIX = " | None"


def _coerce_from_payload(cls: type, payload: Mapping[str, Any]) -> dict[str, Any]:
    """按注解校验 payload 的形状，并还原成 dataclass 的取值；坏形状即抛，不静默猜。

    两半校验是同一件事，缺一不可：

    - **元组字段**：JSON 没有元组，读回来是 list。元素必须是字符串——只写
      `tuple(value)` 的话，一个误写成字符串的指针列会被拆成一串单字符元组，
      不报错、下游 `set(...)` 也照样跑，只是判定悄悄变错。
    - **标量字段**：dataclass 构造不做任何类型检查，`evidence_hit="1"`（字符串）
      会被原样收下，而它进的是分子——指标算出来是个说不清来源的数；`leak="0"`
      则会在汇总求和时抛 TypeError。这正是给元组加校验的同一条理由，标量字段不能漏掉。

    哪些字段是元组、哪个字段是什么类型，全部由**注解本身**决定，不另维护名单——
    新加字段时不会漏。
    """
    data: dict[str, Any] = dict(payload)
    for item in fields(cls):
        if item.name not in data:
            continue
        annotation = str(item.type)
        value = data[item.name]

        if annotation.startswith("tuple["):
            if not isinstance(value, (list, tuple)) or not all(
                isinstance(element, str) for element in value
            ):
                raise ValueError(
                    f"{item.name} 应为字符串列表，收到 {type(value).__name__}"
                )
            data[item.name] = tuple(value)
            continue

        optional = annotation.endswith(_OPTIONAL_SUFFIX)
        if optional and value is None:
            continue
        base = annotation[: -len(_OPTIONAL_SUFFIX)] if optional else annotation
        check = _TYPE_CHECKS.get(base)
        # 认不出的注解（如 `dict[str, object]`）跳过：那类字段由 guard_payload 的
        # 递归长度检查兜底，不在这里假装能校验。
        if check is not None and not check(value):
            raise ValueError(
                f"{item.name} 应为 {base}，收到 {type(value).__name__}：{value!r}"
            )
    return data
