"""检索链的冻结参数（M0-00 §5）。

一次定死的基线值：改其中任何一个都等于换基线，必须走 run 对比（M0-02 §7.3）。
检索与装配两个子包都从这里取参，不各自复制常量——两处各写一个数就会漂移。

`__post_init__` 把参数表里写明的两条关系做成硬约束：
`ask_top_k <= ask_max_chapters * ask_chunks_per_chapter`（否则最终截断先于章上限生效，
章上限永不参与计算），`prompt_token_budget >= 4800`（8 段 × 600 token 的安全阀下限）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# 查询归一化口径标识，写入 `rag_runs.retrieval_params.normalizer_id`。
NORMALIZER_ID = "nfc-trim-collapse-space"

# token budget 的下限：8 段 × 单段上限 600 token（M0-00 §5）。
_MIN_PROMPT_TOKEN_BUDGET = 4800


@dataclass(frozen=True, slots=True)
class RetrievalParams:
    """查询链与装配的全部旋钮，默认值即 M0 基线。"""

    rrf_k: int = 60
    dense_k: int = 60
    kw_k: int = 60
    rerank_k: int = 24
    rerank_output: int = 24
    ask_max_chapters: int = 8
    ask_chunks_per_chapter: int = 2
    ask_top_k: int = 8
    prompt_token_budget: int = 6000
    # 邻块补位的行为不在这里：固定一跳、先取 prev、只在同章内、不递归，
    # 这些都写死在 assembly 里（见该模块 docstring）。它们不是可调参数，
    # 列成参数再校验成唯一合法值，只会得到一个不参与计算的旋钮。
    #
    # 这里没有 neighbor_radius / neighbor_dir 两个字段是刻意的，不要加回来。

    def __post_init__(self) -> None:
        if self.ask_top_k > self.ask_max_chapters * self.ask_chunks_per_chapter:
            raise ValueError("ask_top_k 不得超过 ask_max_chapters × ask_chunks_per_chapter")
        if self.prompt_token_budget < _MIN_PROMPT_TOKEN_BUDGET:
            raise ValueError(f"prompt_token_budget 不得低于 {_MIN_PROMPT_TOKEN_BUDGET}")
        for name in ("rrf_k", "dense_k", "kw_k", "rerank_k", "rerank_output", "ask_top_k"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} 必须为正整数")


# M0 基线实例；调用方直接用这个，不要现场构造。
M0_PARAMS = RetrievalParams()


def retrieval_params_record(params: RetrievalParams = M0_PARAMS) -> dict[str, object]:
    """写进 `rag_runs.retrieval_params` 的记录。

    含 `normalizer_id`：归一化口径是全链路的一环，换口径就是换基线，
    不记进 run 记录就没法解释两次 run 的差异。
    """
    record: dict[str, object] = asdict(params)
    record["normalizer_id"] = NORMALIZER_ID
    return record


__all__ = ["M0_PARAMS", "NORMALIZER_ID", "RetrievalParams", "retrieval_params_record"]
