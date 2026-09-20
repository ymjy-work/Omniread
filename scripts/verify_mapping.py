#!/usr/bin/env python
"""M0-7b 映射链验证：确定性主路径 + 兜底路径 smoke + 产物红线，全程无真实 API 调用。

覆盖内容：

1. 语料直读能还原出 193 章的 chunk 区间，且区间可由正文重建。
2. 357 条 evidence 全部命中，无 unmatched / low_conf。
3. 判据档位分布与实测一致，多归属条目都记了备选 chunk。
4. 章内重复出现的证据被逐位置扫描，不是只看第一次出现。
5. 兜底路径 smoke：假 provider 跑通「渲染 → 解析四字段 → 校验键 → 落结论」，已命中不重复调用。
6. 兜底模型编造 chunk_key 时整条作废；输出不可解析、provider 抖动都留痕不中断。
7. 产物红线：run 目录只含白名单文件、字段不夹带 evidence 原文、超长字段写入前即被拒。
8. 同一输入两次运行产出逐条一致的产物。

用法（仓库根执行，无需凭据）：

    python scripts/verify_mapping.py
    bash scripts/verify-mapping.sh
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "rag" / "src"))

from omniread.infrastructure.objectstore.corpus import read_corpus  # noqa: E402
from omniread.infrastructure.providers.base import MapperCandidate  # noqa: E402
from omniread.infrastructure.providers.fake import FakeMapperModel  # noqa: E402
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1  # noqa: E402
from omniread.pipelines.mapping import (  # noqa: E402
    NO_PROMPT_VERSION,
    ArtifactRedlineError,
    check_run_dir,
    slices_from_corpus,
    spans_from_contents,
    write_run_dir,
)
from omniread.pipelines.mapping.artifacts import MappingRecord  # noqa: E402
from omniread.pipelines.mapping.deterministic import (  # noqa: E402
    TIER_INTRODUCER,
    TIER_MAX_COVERAGE,
    TIER_UNIQUE_COVER,
)
from omniread.pipelines.mapping.fallback import (  # noqa: E402
    MapperParseError,
    apply_fallback,
    parse_mapper_output,
)
from omniread.pipelines.mapping.prompt import render_mapping_prompt  # noqa: E402
from omniread.pipelines.mapping.runner import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN_DIR,
    golden_dataset_hash,
    golden_schema_version,
    load_golden_evidence,
    run_mapping,
)
from omniread.pipelines.mapping.types import (  # noqa: E402
    DETERMINISTIC_MAPPER_MODEL,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    MappingOutcome,
)

# 构造一条「确定性路径没命中」的样例，专门喂给兜底路径。
_NOMATCH = MappingOutcome(
    evidence_hash="0" * 64,
    chapter_id="book:1:chapter:1",
    match_status=MATCH_UNMATCHED,
    matched_chunk_key=None,
    confidence=0.0,
    overlap_reason="构造的未命中样例",
    alternative_chunk_key=None,
    mapper_model=DETERMINISTIC_MAPPER_MODEL,
    mapper_prompt_version=NO_PROMPT_VERSION,
)

_CANDIDATES = [
    MapperCandidate(chunk_key="book:1:chapter:1#c0", content="前一段正文。"),
    MapperCandidate(chunk_key="book:1:chapter:1#c1", content="含目标证据的正文片段。"),
]


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, message: str) -> None:
        print(f"  OK   {message}")
        self.passed += 1

    def bad(self, message: str, detail: str) -> None:
        print(f"  FAIL {message}\n       {detail}")
        self.failed += 1

    def check(self, condition: bool, message: str, detail: str = "") -> None:
        if condition:
            self.ok(message)
        else:
            self.bad(message, detail)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


class FailingMapper:
    """provider 抖动的假实现：验证单条失败被留痕而不是中断整批。"""

    model = "fake-failing"

    async def map_evidence(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provider 抖动")


async def check_fallback(checker: Checker) -> None:
    section("5 兜底路径 smoke（假 provider，无真实调用）")

    prompt = render_mapping_prompt("含目标证据", _CANDIDATES)
    checker.check(
        "含目标证据" in prompt and "#c1" in prompt,
        "prompt 渲染带上了证据与候选键",
        "渲染结果缺少证据或候选键",
    )

    mapper = FakeMapperModel()
    outcome = (await apply_fallback([_NOMATCH], ["含目标证据"], [_CANDIDATES], mapper))[0]
    checker.check(
        outcome.match_status == MATCH_MATCHED
        and outcome.matched_chunk_key == "book:1:chapter:1#c1",
        "兜底后命中包含证据的候选",
        f"实际 status={outcome.match_status} key={outcome.matched_chunk_key}",
    )
    checker.check(
        outcome.alternative_chunk_key == "book:1:chapter:1#c0",
        "未被选中的候选记为备选",
        f"实际 {outcome.alternative_chunk_key}",
    )
    checker.check(
        outcome.mapper_model == mapper.model,
        "mapper_model 记录了实际模型型号",
        f"实际 {outcome.mapper_model}",
    )

    before = len(mapper.calls)
    already = replace(outcome, match_status=MATCH_MATCHED)
    await apply_fallback([already], ["含目标证据"], [_CANDIDATES], mapper)
    checker.check(
        len(mapper.calls) == before,
        "已命中的条目不进入兜底路径（不重复花钱）",
        f"已命中却调用了模型 {len(mapper.calls) - before} 次",
    )


async def check_fallback_failures(checker: Checker) -> None:
    section("6 兜底路径的失败面")

    fabricated = FakeMapperModel(fabricate_key="book:1:chapter:999#c7")
    outcome = (await apply_fallback([_NOMATCH], ["证据"], [_CANDIDATES], fabricated))[0]
    checker.check(
        outcome.match_status == MATCH_UNMATCHED and outcome.matched_chunk_key is None,
        "编造的 chunk_key 被作废，未落进映射",
        f"实际 status={outcome.match_status} key={outcome.matched_chunk_key}",
    )
    checker.check(
        "不在候选集合内" in outcome.overlap_reason,
        "作废原因写进 overlap_reason，不静默",
        f"实际 reason={outcome.overlap_reason}",
    )

    bad_outputs = [
        "完全不是 JSON",
        '{"matched_chunk_key": "x"}',
        '{"matched_chunk_key": "x", "confidence": "高", "overlap_reason": "y", "alternative_chunk_key": null}',
        '{"matched_chunk_key": "x", "confidence": 0.5, "overlap_reason": "  ", "alternative_chunk_key": null}',
    ]
    rejected = 0
    for payload in bad_outputs:
        try:
            parse_mapper_output(payload, model="fake")
        except MapperParseError:
            rejected += 1
    checker.check(
        rejected == len(bad_outputs),
        f"{len(bad_outputs)} 种非法输出全部被拒绝",
        f"只拒绝了 {rejected} 种",
    )

    outcome = (await apply_fallback([_NOMATCH], ["证据"], [_CANDIDATES], FailingMapper()))[0]
    checker.check(
        outcome.match_status == MATCH_UNMATCHED and "兜底映射失败" in outcome.overlap_reason,
        "provider 抖动被留痕，且不中断整批",
        f"实际 {outcome.overlap_reason}",
    )

    outcome = (await apply_fallback([_NOMATCH], ["证据"], [[]], FakeMapperModel()))[0]
    checker.check(
        outcome.match_status == MATCH_UNMATCHED and "无候选" in outcome.overlap_reason,
        "本章无候选时如实记 unmatched",
        f"实际 {outcome.overlap_reason}",
    )


def check_redline(checker: Checker, result, evidence) -> None:
    section("7 产物红线")
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        write_run_dir(
            run_dir, config=result.config, records=result.records, summary=result.summary
        )
        problems = check_run_dir(run_dir)
        checker.check(not problems, "run 目录通过文件白名单与长度检查", "；".join(problems[:3]))

        longest, offender = 0, ""
        for line in (run_dir / "mappings.jsonl").read_text(encoding="utf-8").splitlines():
            for key, value in json.loads(line).items():
                if isinstance(value, str) and len(value) > longest:
                    longest, offender = len(value), key
        checker.check(
            longest <= 500,
            f"mappings.jsonl 最长字符串字段 {longest} 字符（{offender}），远低于 500 上限",
            f"最长 {longest} 字符（{offender}）",
        )

        contents = [item.content for item in evidence]
        leaks = [
            line[:60]
            for line in (run_dir / "mappings.jsonl").read_text(encoding="utf-8").splitlines()
            if any(content in line for content in contents)
        ]
        checker.check(not leaks, "产物中不含任何 evidence 原文", f"泄漏 {len(leaks)} 行")

        (run_dir / "debug.txt").write_text("多余文件", encoding="utf-8")
        checker.check(
            bool(check_run_dir(run_dir)),
            "白名单外的文件会被拦下",
            "多出的 debug.txt 未被检出",
        )
        (run_dir / "debug.txt").unlink()

    section("7b 超长字段在写入前被拒")
    # 600 字符，明确越过 M0-02 §7.1 的 500 上限；写成乘法是为了让意图一眼可见，
    # 而不是让人去数字符。
    long_record = replace(result.records[0], overlap_reason="理由" * 300)
    target = Path(tempfile.mkdtemp()) / "run"
    try:
        write_run_dir(
            target, config=result.config, records=[long_record], summary={"run_id": "x"}
        )
    except ArtifactRedlineError:
        checker.ok("超长字段在写入前即被拒绝，坏产物不会落盘")
    else:
        checker.bad("超长字段未被拒绝", f"{len(long_record.overlap_reason)} 字符的字段被写了进去")

    section("7c 未命中条目必须出现在 mapping_failures")
    unmatched = [r for r in result.records if r.match_status != MATCH_MATCHED]
    checker.check(
        not unmatched,
        "本次全量映射没有未命中条目（mapping_failures.jsonl 为空是事实，不是漏写）",
        f"存在 {len(unmatched)} 条未命中",
    )


def main() -> int:
    checker = Checker()

    section("0 语料与 Golden")
    corpus = read_corpus(DEFAULT_CORPUS_ROOT, book_id=1)
    slices = slices_from_corpus(corpus)
    evidence = load_golden_evidence(DEFAULT_GOLDEN_DIR)
    dataset_hash = golden_dataset_hash(DEFAULT_GOLDEN_DIR)
    print(
        f"  章节 {len(corpus.chapters)}；evidence {len(evidence)}；"
        f"dataset_hash {dataset_hash[:16]}…"
    )
    checker.check(
        len(corpus.chapters) == 193 and len(evidence) == 357,
        "语料 193 章、evidence 357 条",
        f"实际 {len(corpus.chapters)} 章 / {len(evidence)} 条",
    )

    section("1 区间还原")
    broken = []
    for chapter_id, chapter in slices.items():
        rebuilt = spans_from_contents(
            chapter_id,
            chapter.text,
            [chapter.text[span.start : span.end] for span in chapter.spans],
        )
        if [span.chunk_key for span in rebuilt] != [span.chunk_key for span in chapter.spans]:
            broken.append(chapter_id)
    checker.check(
        not broken,
        f"{len(slices)} 章的 chunk 区间可由正文重建且键序一致",
        f"不一致：{broken[:3]}",
    )

    run_args = {
        "run_id": "verify-mapping",
        "slices": slices,
        "evidence": evidence,
        "dataset_hash": dataset_hash,
        "dataset_version": golden_schema_version(DEFAULT_GOLDEN_DIR),
        "chunk_source": "corpus",
        "chunking_version": M0_PLACEHOLDER_V1.profile_id,
        "tokenizer_id": M0_PLACEHOLDER_V1.tokenizer_id,
        "mapper_prompt_version": NO_PROMPT_VERSION,
        "golden_question_count": len({item.question_id for item in evidence}),
    }
    result = run_mapping(**run_args)  # type: ignore[arg-type]

    section("2 全量映射")
    status = Counter(record.match_status for record in result.records)
    checker.check(
        status == {"matched": 357},
        "357 条 evidence 全部命中，无 unmatched / low_conf",
        f"实际分布 {dict(status)}",
    )

    section("3 判据档位")
    tiers = Counter(record.decision_tier for record in result.records)
    print(f"  {dict(tiers)}")
    checker.check(
        tiers.get(TIER_INTRODUCER, 0) == 19,
        "跨块边界的 19 条由「唯一引入者」定主次",
        f"实际 {tiers.get(TIER_INTRODUCER, 0)}",
    )
    checker.check(
        tiers.get(TIER_UNIQUE_COVER, 0)
        + tiers.get(TIER_INTRODUCER, 0)
        + tiers.get(TIER_MAX_COVERAGE, 0)
        == len(result.records),
        "全部落在这三档，未退到兜底规则",
        f"实际 {dict(tiers)}",
    )
    multi = [r for r in result.records if r.alternative_chunk_key]
    checker.check(
        len(multi) == tiers.get(TIER_INTRODUCER, 0) + tiers.get(TIER_MAX_COVERAGE, 0),
        f"多归属的 {len(multi)} 条都记了备选 chunk",
        f"实际 {len(multi)} 条有备选",
    )

    section("4 章内重复出现")
    repeated = [r for r in result.records if r.decision_tier == TIER_MAX_COVERAGE]
    checker.check(
        len(repeated) >= 1
        and all("完整包含" in r.overlap_reason for r in repeated),
        f"{len(repeated)} 条章内重复出现的证据被逐位置扫描"
        "（只看首次出现会误判为唯一覆盖）",
        f"实际 {len(repeated)} 条",
    )

    asyncio.run(check_fallback(checker))
    asyncio.run(check_fallback_failures(checker))
    check_redline(checker, result, evidence)

    section("8 可复现")
    second = run_mapping(**run_args)  # type: ignore[arg-type]
    checker.check(
        list(second.records) == list(result.records),
        "两次运行的产物逐条一致",
        "两次运行结果不同",
    )
    checker.check(
        MappingRecord.from_outcome("x", _NOMATCH).overlap_reason != "",
        "未命中条目的 overlap_reason 非空（列不可空）",
        "未命中理由为空",
    )

    print(f"\n=== 汇总：{checker.passed} 项通过，{checker.failed} 项失败 ===")
    if checker.failed == 0:
        print("M0-7b 映射链验证通过（兜底路径由假 provider 覆盖，无真实调用）。")
    return 1 if checker.failed else 0


if __name__ == "__main__":
    sys.exit(main())
