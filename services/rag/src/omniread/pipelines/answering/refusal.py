"""模型级拒答标记（M0-02 §8.3）：让「有上下文但模型答不了」可被确定性识别。

§8.3 规定拒答响应里 `context_chapters` **非空**即表示模型级拒答（检索为空导致的拒答
它是 `[]`），并写明「有证据但模型答不出」要确定性识别**需让模型输出结构化标记**。
本模块是那个标记的唯一真相源：模板 `prompts/answer.md` 必须逐字包含它
（`test_answer_prompt.py` 钉住），服务端按它判定。

标记写成 `[INSUFFICIENT]` 有三个理由：

- **不与引用扫描撞车**。`CANDIDATE_PATTERN` 是 `\\[[Cc]\\d[^\\]]*\\]`——要求 `[C` / `[c]`
  后面紧跟数字。标记以 `[I` 开头，既不会被算成引用，也不会被算成违规写法。
- **不是自由文本**。判据是「剥掉前导空白后以标记开头」这个字符串比较，不调模型、
  不认语义，因此可复现。
- **服务端据此改写答案**（把整条回答换成固定话术）是 §8.3 明文允许的：
  拒答话术由服务端填充，避免模型在里头夹带域外信息。

**只认开头**：中段出现标记不算拒答，也不会被删掉——与引用同一条口径，
扫描是扫描，不改写模型输出（M0-04 §4）。误判的代价是这条回答被换成拒答话术，
而按模板要求标记只在拒答时出现。

判定要边收边判：流式回答不能等全文到齐才决定要不要吐给客户端，所以这里给的是
一个**逐块喂入的前缀状态机**（`scan_prefix`），不是「拿全文判一次」。
"""

from __future__ import annotations

#: 模型级拒答标记。改它必须同时改模板 `prompts/answer.md`（测试会两边对不上就红）。
REFUSAL_MARKER = "[INSUFFICIENT]"

#: 允许的前导空白上限。模型常先吐一个换行；给够余量，但不能无限等——
#: 超过这个数还没出现非空白字符，这段输出就不可能是「以标记开头」了。
MAX_LEADING_WHITESPACE = 8

#: `scan_prefix` 的三种结论。
PREFIX_PENDING = "pending"
PREFIX_REFUSAL = "refusal"
PREFIX_ANSWER = "answer"


def scan_prefix(pending: str) -> str:
    """对已缓冲的首部做判定，返回 `PREFIX_*` 之一。

    三种结论互斥且穷尽：

    - `PREFIX_REFUSAL`：剥掉前导空白后已经以标记开头——判定完成，不会再变；
    - `PREFIX_PENDING`：目前还是标记的前缀（含「只有空白」），继续收；
    - `PREFIX_ANSWER`：已经不可能成为标记开头，可以按普通回答放行。

    `MAX_LEADING_WHITESPACE` 只在**还没匹配上**时起作用：它决定「不再等了」，
    而不是「空白太多就不算拒答」——已经匹配上的照样判 `PREFIX_REFUSAL`。

    **调用方在流结束时必须以 `PREFIX_ANSWER` 收尾**：流断在半截标记上
    （模型吐了 `[INSUF` 就停了）不是拒答，压着的文本要照常吐出去。
    """
    stripped = pending.lstrip()
    if stripped.startswith(REFUSAL_MARKER):
        return PREFIX_REFUSAL
    if len(pending) - len(stripped) > MAX_LEADING_WHITESPACE:
        return PREFIX_ANSWER
    return PREFIX_PENDING if REFUSAL_MARKER.startswith(stripped) else PREFIX_ANSWER


__all__ = [
    "MAX_LEADING_WHITESPACE",
    "PREFIX_ANSWER",
    "PREFIX_PENDING",
    "PREFIX_REFUSAL",
    "REFUSAL_MARKER",
    "scan_prefix",
]
