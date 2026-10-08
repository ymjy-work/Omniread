"""检索链的冻结参数（当前为 **M1 新基线**，2026-10-08 冻结）。

一次定死的基线值：改其中任何一个都等于换基线，必须走 run 对比（M0-02 §7.3）。
检索与装配两个子包都从这里取参，不各自复制常量——两处各写一个数就会漂移。

**相对 M0 基线只动三个装配旋钮**，其余不动：

| 参数 | M0 | 当前 | 为什么 |
| --- | --- | --- | --- |
| `rerank_k` | 24 | **32** | 让 provider 多看 8 条候选，从中挑回同样的 24 条 |
| `ask_top_k` | 8 | **12** | 唯一能直接换回命中的旋钮，且无副作用 |
| `ask_chunks_per_chapter` | 2 | **4** | 主要瓶颈：跨章题需要同章的多段证据 |

依据是 `eval/runs/2026-10-08-m1-*` 的七组单变量对照（`docs/M1-装配瓶颈测评方案.md` 的方法）：
总体 `evidence_recall` 0.7003 → **0.8179**、`cross` 0.5417 → **0.6562**，`leak` 全程保持 0。
机理可解释：`ask_chunks_per_chapter=2` 时「未进装配的映射 key」里有 32 个是被每章上限
切掉的，提到 4 之后只剩 5 个——是逻辑上的改进，不是随机波动。

**这个数字带着未校正的选择偏差，引用时必须一起说**：连续 8 轮都在同一批 86 题上选参数，
`0.8179` 里有多少是对这 86 题的过拟合，**用现有数据分辨不出来**。
正确的翻案办法是拿新题验证（从同一本小说再抽题补 cross / boundary 两桶），
不是继续在这批题上调参。

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
    # M1 新基线：24 → 32。注意它只决定**送进去**几条候选，拿回来几条由 rerank_output 定，
    # 所以单抬它不会把装配池变大（实测 rerank_output 24→32 的召回变化为零）。
    rerank_k: int = 32
    rerank_output: int = 24
    ask_max_chapters: int = 8
    # M1 新基线：2 → 4。它同时是「每章几条 hit」的上限与「要不要补邻块」的开关
    # （`len(picked) < cap` 才补，每章只补一条），两个角色会一起动。
    ask_chunks_per_chapter: int = 4
    ask_top_k: int = 12
    # 下限 4800 = 8 段 × 600 token。当前 ask_top_k=12 时上界是 7200，**预算会真的截断**：
    # 实测这一档掉了 160+ 个 chunk（其中约 1 条是 evidence），逐出顺序是「先保 hit 再保 neighbor」。
    # 抬 ask_top_k 而不抬这个值，多吃的预算会把邻块全部逐出（实测 ask_top_k=16 时邻块 92 → 9）。
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


def retrieval_params_record(
    params: RetrievalParams = M0_PARAMS, *, neighbor_expand: bool = True
) -> dict[str, object]:
    """写进 `rag_runs.retrieval_params` 的记录。

    两个键不在 `RetrievalParams` 里，但同样是「改了就换基线」的旋钮：

    - `normalizer_id`：归一化口径是全链路的一环，换口径就是换基线；
    - `neighbor_expand`：邻块补位开关（`QueryRequest` 的字段）。它决定最终装配集里
      有没有邻居段——一次关掉它的实验 run 必须自证，否则它的 `config.json` 与开着的那次
      一模一样，两次 run 的差异就无处可查。
    """
    record: dict[str, object] = asdict(params)
    record["normalizer_id"] = NORMALIZER_ID
    record["neighbor_expand"] = neighbor_expand
    return record


__all__ = ["M0_PARAMS", "NORMALIZER_ID", "RetrievalParams", "retrieval_params_record"]
