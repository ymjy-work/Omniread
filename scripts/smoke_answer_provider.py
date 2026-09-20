#!/usr/bin/env python
"""M0-5 回答链冒烟：prompt 组装 + chat provider 的 complete / stream。

默认用假 chat provider，**不发任何真实调用**；只有显式传 `--real` 才构造 GLM 适配器走
BigModel（需要 `GLM_API_KEY`，经 `keymgr run` 注入）。真实冒烟由用户单独批准后执行。

用法（仓库根执行）：
    uv run --directory services/rag python scripts/smoke_answer_provider.py
    # 真实调用（需先批准并注入凭据）：
    keymgr run glm-rag uv run --directory services/rag python scripts/smoke_answer_provider.py --real
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from omniread.infrastructure.providers import (
    GLM_ANSWER_MODEL,
    ChatModel,
    FakeChatModel,
    GlmChatAdapter,
    ProviderConfigError,
)
from omniread.pipelines.answering import (
    ContextPassage,
    answer_prompt_version,
    build_answer_messages,
)

QUESTION = "政近为什么离开周防家？"

PASSAGES = [
    ContextPassage(chapter_index=17, text="政近向艾莉说明了自己离开周防家的原因。"),
    ContextPassage(chapter_index=45, text="艾莉把那封信读完了。"),
]


async def _run(model: ChatModel, *, label: str) -> int:
    messages = build_answer_messages(QUESTION, PASSAGES)

    print(f"[{label}] model={model.model}")
    print(f"[{label}] prompt_version={answer_prompt_version()}")
    print(f"[{label}] system 长度={len(messages[0].content)} 字符")
    print(f"[{label}] user 长度={len(messages[1].content)} 字符")

    response = await model.complete(messages)
    print(f"[{label}] complete 正文：{response.text}")
    if response.reasoning:
        print(f"[{label}] complete reasoning 已单独存放，长度={len(response.reasoning)}")

    pieces = [chunk.text async for chunk in model.stream(messages)]
    streamed = "".join(pieces)
    print(f"[{label}] stream 分片数={len(pieces)}，拼接结果：{streamed}")
    if streamed != response.text:
        print(
            f"[{label}] 失败：流式拼接与 complete 正文不一致",
            file=sys.stderr,
        )
        return 1
    print(f"[{label}] 通过：流式逐块产出且与 complete 一致")
    return 0


async def _main(real: bool) -> int:
    if not real:
        return await _run(FakeChatModel(answer="政近是因为家族安排才离开的 [C17]。"), label="fake")

    try:
        adapter = GlmChatAdapter()
    except ProviderConfigError as exc:
        print(f"失败：{exc.message}", file=sys.stderr)
        print(
            "真实冒烟需要 GLM_API_KEY：用 keymgr run glm-rag 注入后重试。",
            file=sys.stderr,
        )
        return 2
    print(f"[real] 真实调用 {GLM_ANSWER_MODEL}（会消耗额度）")
    try:
        return await _run(adapter, label="real")
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本要把失败原样报出来
        print(f"[real] 调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await adapter.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="M0-5 回答链冒烟（默认假 provider）")
    parser.add_argument(
        "--real",
        action="store_true",
        help="走真实 GLM provider（需 GLM_API_KEY，且需用户明确批准）",
    )
    args = parser.parse_args()
    return asyncio.run(_main(args.real))


if __name__ == "__main__":
    raise SystemExit(main())
