"""裁判（评测专用）：判「回答是否忠实于材料」，补确定性指标看不到的语义错。

**不在请求路径上**：回答、改写、摘要三份 prompt 挂在线上链路，这一份只在评测里跑。
判定**不作门禁**，只旁挂在确定性指标旁边。

判据全文在 `prompts/judge.md`，组装与版本规则见 `prompt.py`；
调用与判据解析（从严、不剥围栏）见 `judge.py`。
"""

from __future__ import annotations

from omniread.pipelines.judging.judge import (
    JUDGE_OPTIONS,
    JUDGE_VERDICTS,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNCERTAIN,
    AnswerJudge,
    FakeAnswerJudge,
    JudgeError,
    JudgeVerdict,
    parse_verdict,
)
from omniread.pipelines.judging.prompt import (
    PROMPT_VERSION_LENGTH,
    JudgePrompt,
    build_judge_messages,
    judge_prompt_version,
    load_judge_prompt,
    parse_judge_prompt,
    prompt_version,
    read_judge_template,
)

__all__ = [
    "JUDGE_OPTIONS",
    "JUDGE_VERDICTS",
    "PROMPT_VERSION_LENGTH",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNCERTAIN",
    "AnswerJudge",
    "FakeAnswerJudge",
    "JudgeError",
    "JudgePrompt",
    "JudgeVerdict",
    "build_judge_messages",
    "judge_prompt_version",
    "load_judge_prompt",
    "parse_judge_prompt",
    "parse_verdict",
    "prompt_version",
    "read_judge_template",
]
