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
    - **标量字段**：dataclass 构造不做任何类型检查，`citation_membership_ok="no"`
      （字符串）会被原样收下，而它是个**真值**——门禁的分子照收，失败题被算成通过；
      `point_coverage="0.9"` 则会在汇总求和时抛 TypeError。这正是给元组加校验的
      同一条理由，标量字段不能漏掉。

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


#: 生成层的回答状态。`generation_failed` 是**独立的一种**，绝不并进拒答：
#: provider 故障记成拒答会让 `refusal_correct` 悄悄失真（M0-02 §8.3）。
STATUS_ANSWERED = "answered"
STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
STATUS_GENERATION_FAILED = "generation_failed"


@dataclass(frozen=True, slots=True)
class GenerationScoreRecord:
    """生成层逐题记录；`generation.scores.jsonl` 的一行。

    **字段集就是 `eval/` 允许携带的全部内容**（M0-02 §7.1：`question_id` + judge 指标
    + `answer_model` / `judge_model` / `request_id`）。回答原文、材料正文、judge 的
    `reason` / `rationale` 与整个 `LLMTestCase` 都**没有地方可放**——这不是纪律，是
    类型里就没有那个字段。

    这是生成层唯一的自动防线：`verify_artifacts.py` 的「与语料逐字重合」比对只认
    语料原文，**对模型写的文本天然失效**，而 500 字符长度上限拦不住一段 300 字回答。

    越界引用只记**标记本身**（`[C45]` 这种短 token），且由解析出的章号**重新拼出**、
    不是从答案里切下来的：`CANDIDATE_PATTERN` 是 `\\[[Cc]\\d[^\\]]*\\]`，那个
    `[^\\]]*` 能一路吃到下一个 `]`，照抄就是整整一段正文。
    """

    question_id: str
    question_type: str
    difficulty: str
    expect_refusal: bool

    # ── 确定性判定：不依赖 judge，M0 就能算，可以进门禁 ──
    status: str
    citation_count: int
    #: 两条件都满足（M0-04 §5.2）：① 引用全在允许集内 ② 非拒答题至少一条引用
    citation_membership_ok: bool
    #: 越界引用，形如 `[C45]`；由章号重拼，不是原文切片
    citation_out_of_range: tuple[str, ...]
    #: 非规范写法（`[c17]` / `[C017]` / `[C1 说明]`）的**条数**。只记数不记原文：
    #: 那类片段里可能裹着正文，要看内容请去 `temp/run.gen.jsonl`
    citation_malformed_count: int

    # ── 指针 ──
    request_id: str
    answer_provider: str
    answer_model: str
    prompt_version: str
    judge_provider: str
    judge_model: str

    # ── judge 指标：M0-8 校准完成前恒为 None ──
    #: None 是「未执行」，不是「得 0 分」。这两者混起来会让「还没跑」看起来像「跑了全错」。
    point_coverage: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    answer_boundary_violation: float | None = None
    citation_supported: float | None = None

    #: 合法的 `status`。写成集合而不是靠 `str` 注解兜住：它驱动 `generation_failed`
    #: 的计数，一个拼错的取值会让「这次 run 带故障」这件事从产物里消失。
    _STATUSES = frozenset({STATUS_ANSWERED, STATUS_INSUFFICIENT_EVIDENCE, STATUS_GENERATION_FAILED})

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GenerationScoreRecord:
        """从 `generation.scores.jsonl` 的一行还原。"""
        data = _coerce_from_payload(cls, payload)
        status = data.get("status")
        if status is not None and status not in cls._STATUSES:
            raise ValueError(f"status 取值非法：{status!r}，应属于 {sorted(cls._STATUSES)}")
        return cls(**data)
