#!/usr/bin/env python3
"""Omniread M0 Golden 数据集校验器（权威）。

职责
----
1. 校验单个题目文件是否符合 `schema.json`（结构规则）以及 schema 表达不了的跨字段规则；
2. 校验整个数据集目录：文件名 / id 约定、id 全局唯一、各桶数量与拒答题数量达标情况；
3. 计算并打印 `dataset_hash`。

只依赖 Python 标准库，不引入任何第三方依赖——数据集由另一个项目并行产出，
对方环境未必装有本仓库的依赖。

用法
----
    python scripts/validate_golden.py                 # 校验 eval/golden/*.json
    python scripts/validate_golden.py <目录>          # 校验指定数据集目录（对方项目用）
    python scripts/validate_golden.py <单个.json>     # 只校验单个题目文件（不查文件名约定与数量目标）

退出码：0 全部通过；1 存在校验问题；2 用法 / IO 错误。

dataset_hash 口径（定死，双方重算必须一致）
------------------------------------------
1. 只取符合 `<type>-<三位序号>.json` 命名、且能解析出 `id` 的题目文件；
2. 按 `id` 升序排序；
3. 逐个用 `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`
   规范化序列化；
4. 用 `"\\n"` 连接全部规范化结果；
5. 对连接后的字符串取 UTF-8 编码的 sha256 十六进制摘要。

口径必须定死，双方重算才能对齐；Ready Gate 通过时把该值写入并冻结。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量：与 schema.json 对齐
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "m0.1.0"
TYPES = ("fact", "alias", "cross", "foreshadow", "boundary", "spoiler")
DIFFICULTIES = ("easy", "medium", "hard")
LEVELS = ("past", "full")
BOOK_ID_M0 = 1
PROGRESS_MIN = 1
PROGRESS_MAX = 193
CHAPTER_INDEX_MIN = 1
CHAPTER_INDEX_MAX = 193

# 数量目标：整体统计，不是单文件校验
TOTAL_MIN = 60
PER_TYPE_MIN = 8
REFUSAL_MIN = 10

# 题目文件名约定：<type>-<三位序号>.json
DATASET_FILE_RE = re.compile(
    r"^(fact|alias|cross|foreshadow|boundary|spoiler)-(\d{3})\.json$"
)
# chapter_id 约定：book:{book_id}:chapter:{chapter_index}
# 用 ASCII [0-9] 而非 \d：Python 的 \d 默认也匹配全角与阿拉伯-印度数字，
# 而 int("١٧") == 17，会让这类章号在兜底路径上蒙混过关，与 schema pattern 的结论不一致。
# [1-9] 开头同时拒绝前导零（book:1:chapter:017）。
CHAPTER_ID_RE = re.compile(r"^book:([1-9][0-9]*):chapter:([1-9][0-9]*)$")

# 目录扫描时跳过的非题目文件（套件自带的 Schema 与示例）
AUX_FILES = {"schema.json", "golden.schema.json", "example.json"}
SCHEMA_CANDIDATES = ("schema.json", "golden.schema.json")

# schema.json 中受支持的 JSON Schema 关键字；未支持的关键字会被提示「未校验」
_SUPPORTED_KEYWORDS = {
    "$schema", "$id", "title", "description",
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "items", "minItems", "minLength", "minimum", "maximum", "pattern",
    "allOf", "if", "then", "else", "not",
}


# ---------------------------------------------------------------------------
# 报错收集
# ---------------------------------------------------------------------------


class Report:
    """收集校验过程中的错误与警告，错误决定退出码，警告不影响。"""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append((where or "(root)", msg))

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# 最小 JSON Schema 子集校验（draft 2020-12 中本 schema 实际用到的关键字）
# ---------------------------------------------------------------------------


def _is_int(inst: object) -> bool:
    """严格整数判断：bool 是 int 的子类，必须排除，否则 true 会被当成 1。"""
    return isinstance(inst, int) and not isinstance(inst, bool)


def _json_type_ok(inst: object, want: str) -> bool:
    if want == "object":
        return isinstance(inst, dict)
    if want == "array":
        return isinstance(inst, list)
    if want == "string":
        return isinstance(inst, str)
    if want == "integer":
        return _is_int(inst)
    if want == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if want == "boolean":
        return isinstance(inst, bool)
    if want == "null":
        return inst is None
    return True  # 未知 type 不拦


def _json_pattern_search(pattern: str, inst: str) -> bool:
    """按 JSON Schema（ECMA-262）语义匹配 pattern。

    ECMA 的 `$`（无 m 标志）只匹配整串末尾；Python 的 `$` 允许匹配末尾换行之前，
    直接用会漏掉 `"...\\n"` 这类尾随换行。把结尾处未转义的 `$` 换成 `\\Z` 后语义一致。
    """
    if pattern.endswith("$") and not pattern.endswith(r"\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.search(pattern, inst) is not None


def _child_path(path: str, key: str) -> str:
    return key if not path else f"{path}.{key}"


def _value_equal(a: object, b: object) -> bool:
    """严格相等：把 bool 与 int 区分开（Python 里 True == 1，直接比较会漏检）。"""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _matches(inst: object, schema: object) -> bool:
    """判断实例是否满足 schema（用于 if / not 的条件求值），忽略警告。"""
    probe = Report()
    _validate(inst, schema, "", probe)
    return probe.ok


def _validate(inst: object, schema: object, path: str, rep: Report) -> None:
    """以最小子集校验 instance 是否符合 schema。"""
    if not isinstance(schema, dict):
        return

    if "type" in schema:
        want = schema["type"]
        wants = want if isinstance(want, list) else [want]
        if not any(_json_type_ok(inst, w) for w in wants):
            rep.error(path, f"类型应为 {want}，实际为 {type(inst).__name__}")
            return  # 类型不符时后续关键字无意义

    if "const" in schema and not _value_equal(inst, schema["const"]):
        rep.error(path, f"取值必须为 {schema['const']!r}，实际为 {inst!r}")

    if "enum" in schema and not any(_value_equal(inst, e) for e in schema["enum"]):
        rep.error(path, f"取值必须属于 {schema['enum']}，实际为 {inst!r}")

    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            rep.error(path, f"长度不得小于 {schema['minLength']}（当前 {len(inst)}）")
        if "pattern" in schema and not _json_pattern_search(schema["pattern"], inst):
            rep.error(path, f"不匹配模式 {schema['pattern']!r}：{inst!r}")

    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            rep.error(path, f"不得小于 {schema['minimum']}（当前 {inst}）")
        if "maximum" in schema and inst > schema["maximum"]:
            rep.error(path, f"不得大于 {schema['maximum']}（当前 {inst}）")

    if isinstance(inst, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in inst:
                rep.error(_child_path(path, key), "缺少必填字段")
        for key, value in inst.items():
            if key in props:
                _validate(value, props[key], _child_path(path, key), rep)
                continue
            addl = schema.get("additionalProperties", True)
            if addl is False:
                rep.error(
                    _child_path(path, key),
                    f"不允许的字段（字段集不含 {key}）",
                )
            elif isinstance(addl, dict):
                _validate(value, addl, _child_path(path, key), rep)

    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            rep.error(path, f"元素个数不得少于 {schema['minItems']}（当前 {len(inst)}）")
        if "items" in schema:
            for i, item in enumerate(inst):
                _validate(item, schema["items"], f"{path}[{i}]", rep)

    for sub in schema.get("allOf", []):
        _validate(inst, sub, path, rep)

    if "if" in schema:
        if _matches(inst, schema["if"]):
            if "then" in schema:
                _validate(inst, schema["then"], path, rep)
        elif "else" in schema:
            _validate(inst, schema["else"], path, rep)

    if "not" in schema and _matches(inst, schema["not"]):
        rep.error(path, "命中了被禁止的取值组合")


def collect_unsupported_keywords(schema: object, found: set[str]) -> None:
    """递归收集 schema.json 里本校验器未支持的关键字，避免「以为校验了其实没校验」。"""
    if not isinstance(schema, dict):
        return
    for key in schema:
        if key.startswith("$"):
            continue
        if key not in _SUPPORTED_KEYWORDS:
            found.add(key)
    # properties 的键是字段名而不是关键字，只递归它的值
    props = schema.get("properties")
    if isinstance(props, dict):
        for sub in props.values():
            collect_unsupported_keywords(sub, found)
    for key in ("items", "additionalProperties", "if", "then", "else", "not"):
        value = schema.get(key)
        if isinstance(value, dict):
            collect_unsupported_keywords(value, found)
    for key in ("allOf", "anyOf", "oneOf"):
        value = schema.get(key)
        if isinstance(value, list):
            for item in value:
                collect_unsupported_keywords(item, found)


# ---------------------------------------------------------------------------
# 备用的原生结构校验（schema.json 缺失时使用）
# ---------------------------------------------------------------------------


def _validate_structure_native(obj: object, rep: Report) -> None:
    """schema.json 不可用时的兜底结构校验，规则与 schema.json 一致。"""
    if not isinstance(obj, dict):
        rep.error("", "题目必须是 JSON 对象")
        return
    required = [
        "schema_version", "id", "type", "difficulty", "book_id",
        "question", "reference_points", "level", "expect_refusal",
        "must_cite_groups",
    ]
    allowed = set(required) | {"reference_answer", "progress"}

    for key in required:
        if key not in obj:
            rep.error(key, "缺少必填字段")
    for key in obj:
        if key not in allowed:
            rep.error(key, f"不允许的字段（字段集不含 {key}）")

    if obj.get("schema_version") != SCHEMA_VERSION:
        rep.error("schema_version", f"必须为 {SCHEMA_VERSION!r}，实际为 {obj.get('schema_version')!r}")
    if "id" in obj and not (isinstance(obj["id"], str) and obj["id"]):
        rep.error("id", "必须是非空字符串")
    if obj.get("type") not in TYPES:
        rep.error("type", f"必须属于 {list(TYPES)}，实际为 {obj.get('type')!r}")
    if obj.get("difficulty") not in DIFFICULTIES:
        rep.error("difficulty", f"必须属于 {list(DIFFICULTIES)}，实际为 {obj.get('difficulty')!r}")
    book_id = obj.get("book_id")
    if not (_is_int(book_id) and book_id == BOOK_ID_M0):
        rep.error("book_id", f"M0 恒为 {BOOK_ID_M0}，实际为 {book_id!r}")
    if not (isinstance(obj.get("question"), str) and obj["question"]):
        rep.error("question", "必须是非空字符串")

    points = obj.get("reference_points")
    if not isinstance(points, list) or not points:
        rep.error("reference_points", "必须是非空数组")
    elif any(not (isinstance(p, str) and p) for p in points):
        rep.error("reference_points", "每个要点必须是非空字符串")

    if "reference_answer" in obj and not (
        isinstance(obj["reference_answer"], str) and obj["reference_answer"]
    ):
        rep.error("reference_answer", "存在时必须是非空字符串")

    level = obj.get("level")
    if level not in LEVELS:
        rep.error("level", f"必须属于 {list(LEVELS)}，实际为 {level!r}")
    has_progress = "progress" in obj
    if level == "past" and not has_progress:
        rep.error("progress", "level=past 时必填")
    if level == "full" and has_progress:
        rep.error("progress", "level=full 时必须缺省")
    if has_progress:
        p = obj["progress"]
        if not _is_int(p):
            rep.error("progress", "必须是整数")
        elif not (PROGRESS_MIN <= p <= PROGRESS_MAX):
            rep.error("progress", f"取值范围 {PROGRESS_MIN}..{PROGRESS_MAX}，实际为 {p}")

    if not isinstance(obj.get("expect_refusal"), bool):
        rep.error("expect_refusal", "必须是布尔值")
    if obj.get("type") == "spoiler" and obj.get("expect_refusal") is not True:
        rep.error("expect_refusal", "spoiler 桶必须 expect_refusal=true")

    groups = obj.get("must_cite_groups")
    if not isinstance(groups, list) or not groups:
        rep.error("must_cite_groups", "必须是非空数组（外层 AND）")
    else:
        for gi, group in enumerate(groups):
            if not isinstance(group, list) or not group:
                rep.error(f"must_cite_groups[{gi}]", "各组必须是非空数组（组内 OR）")
                continue
            for ei, ev in enumerate(group):
                leaf = f"must_cite_groups[{gi}][{ei}]"
                if not isinstance(ev, dict):
                    rep.error(leaf, "evidence 必须是对象")
                    continue
                extra = set(ev) - {"chapter_id", "content"}
                if extra:
                    rep.error(leaf, f"evidence 只允许 chapter_id + content，多出 {sorted(extra)}")
                if not (isinstance(ev.get("content"), str) and ev["content"]):
                    rep.error(f"{leaf}.content", "必须是非空字符串（原文片段）")
                if not (isinstance(ev.get("chapter_id"), str) and ev["chapter_id"]):
                    rep.error(f"{leaf}.chapter_id", "必须是非空字符串")
                elif not CHAPTER_ID_RE.fullmatch(ev["chapter_id"]):
                    rep.error(f"{leaf}.chapter_id", "格式必须为 book:{book_id}:chapter:{chapter_index}")


# ---------------------------------------------------------------------------
# 跨字段约束（JSON Schema 表达不了的部分）
# ---------------------------------------------------------------------------


def validate_cross_fields(obj: object, rep: Report) -> None:
    """level/progress 与 evidence chapter_index 的自洽性。"""
    if not isinstance(obj, dict):
        return

    level = obj.get("level")
    book_id = obj.get("book_id")
    progress = obj.get("progress")
    progress_ok = _is_int(progress)
    book_ok = _is_int(book_id)

    # level=full 时 progress 必须缺省：在 progress 字段上给出可定位的报错
    if level == "full" and "progress" in obj:
        rep.error("progress", f"level=full 时 progress 必须缺省，实际为 {progress!r}")

    groups = obj.get("must_cite_groups")
    if not isinstance(groups, list):
        return

    for gi, group in enumerate(groups):
        if not isinstance(group, list):
            continue
        for ei, ev in enumerate(group):
            if not isinstance(ev, dict):
                continue
            cid = ev.get("chapter_id")
            leaf = f"must_cite_groups[{gi}][{ei}].chapter_id"
            if not isinstance(cid, str):
                continue  # 结构校验已报「必须是字符串」
            m = CHAPTER_ID_RE.fullmatch(cid)
            if not m:
                # schema.json 的 pattern 更严（固定 book:1），这里只兜底格式错
                continue
            ev_book = int(m.group(1))
            ev_chapter = int(m.group(2))

            if book_ok and ev_book != book_id:
                rep.error(
                    leaf,
                    f"book 段为 {ev_book}，与本题 book_id={book_id} 不自洽",
                )
            if not (CHAPTER_INDEX_MIN <= ev_chapter <= CHAPTER_INDEX_MAX):
                rep.error(
                    leaf,
                    f"chapter_index={ev_chapter} 超出 {CHAPTER_INDEX_MIN}..{CHAPTER_INDEX_MAX}",
                )
            if level == "past" and progress_ok and ev_chapter > progress:
                rep.error(
                    leaf,
                    f"越界：evidence chapter_index={ev_chapter} > 本题 progress={progress}",
                )


# ---------------------------------------------------------------------------
# 文件 / 数据集校验
# ---------------------------------------------------------------------------


def load_json(path: Path, rep: Report) -> object | None:
    try:
        # utf-8-sig 兼容带 BOM 与不带 BOM 的文件（对方编辑器可能写入 BOM）
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        rep.error(str(path), f"无法读取：{exc}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        rep.error(str(path), f"JSON 解析失败：{exc}")
        return None


def load_schema(directory: Path, rep: Report) -> dict | None:
    schema_path = next(
        (directory / name for name in SCHEMA_CANDIDATES if (directory / name).is_file()),
        None,
    )
    if schema_path is None:
        rep.warn(
            f"{directory} 下未找到 {' 或 '.join(SCHEMA_CANDIDATES)}，"
            "改用内置结构规则校验（跨字段规则不受影响）"
        )
        return None
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        rep.warn(f"读取 {schema_path} 失败（{exc}），改用内置结构规则校验")
        return None
    # 只判键是否存在不够：{"properties": {}, "required": []} 这种空壳 schema 同样会让任何题目通过。
    # 要求两者都非空，否则一律视为不可用。
    if (
        not isinstance(schema, dict)
        or not isinstance(schema.get("properties"), dict)
        or not schema["properties"]
        or not isinstance(schema.get("required"), list)
        or not schema["required"]
    ):
        rep.warn(
            f"{schema_path} 未提供可用的 properties/required（空对象或空壳 schema 会让任何题目都通过），"
            "改用内置结构规则校验（跨字段规则不受影响）"
        )
        return None
    unsupported: set[str] = set()
    collect_unsupported_keywords(schema, unsupported)
    if unsupported:
        rep.warn(
            "schema 含本校验器未支持的关键字，相关规则未校验："
            + ", ".join(sorted(unsupported))
        )
    return schema


def validate_question(
    obj: object,
    rep: Report,
    schema: dict | None,
    filename: str | None = None,
) -> None:
    """校验单题；出错位置由调用方拼接文件名。"""
    if schema is not None:
        _validate(obj, schema, "", rep)
    else:
        _validate_structure_native(obj, rep)
    validate_cross_fields(obj, rep)

    file_match = DATASET_FILE_RE.fullmatch(filename) if filename is not None else None
    if file_match is not None:
        if not isinstance(obj, dict):
            return
        stem = filename[: -len(".json")]
        prefix = file_match.group(1)
        if obj.get("id") != stem:
            rep.error("id", f"id={obj.get('id')!r} 与文件名 {filename!r} 不一致")
        if obj.get("type") != prefix:
            rep.error(
                "type",
                f"type={obj.get('type')!r} 与文件名前缀 {prefix!r} 不一致",
            )


def validate_directory(target: Path) -> Report:
    rep = Report()
    schema = load_schema(target, rep)

    dataset_entries: list[tuple[str, object | None]] = []
    for path in sorted(target.glob("*.json")):
        name = path.name
        if name in AUX_FILES:
            continue
        if not DATASET_FILE_RE.fullmatch(name):
            rep.error(
                name,
                "文件名必须为 <type>-<三位序号>.json（type 取六桶之一），"
                "非题目文件请移出数据集目录",
            )
            continue
        dataset_entries.append((name, load_json(path, rep)))

    seen: dict[str, list[str]] = {}
    for name, obj in dataset_entries:
        before = len(rep.errors)
        validate_question(obj, rep, schema, filename=name)
        # 把本文件的错误挂上文件名，便于定位
        for i in range(before, len(rep.errors)):
            where, msg = rep.errors[i]
            rep.errors[i] = (f"{name} :: {where}", msg)
        if isinstance(obj, dict) and isinstance(obj.get("id"), str):
            seen.setdefault(obj["id"], []).append(name)

    # id 全局唯一
    for key, files in sorted(seen.items()):
        if len(files) > 1:
            rep.error(", ".join(files), f"id={key!r} 在数据集内重复出现")

    # 数量统计（按文件名前缀分桶；前缀与 type 的一致性已在单题校验中检查）
    per_type = {t: 0 for t in TYPES}
    refusal = 0
    for name, obj in dataset_entries:
        per_type[DATASET_FILE_RE.fullmatch(name).group(1)] += 1
        if isinstance(obj, dict) and obj.get("expect_refusal") is True:
            refusal += 1
    total = len(dataset_entries)

    print(f"== 数据集校验：{target} ==")
    print(f"题目文件数：{total}")
    print("-- 数量目标 --")
    _print_quota("总量", total, TOTAL_MIN)
    if total < TOTAL_MIN:
        rep.error("(数据集)", f"总量 {total} 未达目标 ≥{TOTAL_MIN}")
    for t in TYPES:
        _print_quota(f"  {t}", per_type[t], PER_TYPE_MIN)
        if per_type[t] < PER_TYPE_MIN:
            rep.error("(数据集)", f"类型 {t} 数量 {per_type[t]} 未达目标 ≥{PER_TYPE_MIN}")
    _print_quota("拒答题", refusal, REFUSAL_MIN)
    if refusal < REFUSAL_MIN:
        rep.error("(数据集)", f"拒答题数量 {refusal} 未达目标 ≥{REFUSAL_MIN}")

    print("-- dataset_hash --")
    print(f"dataset_hash: {dataset_hash(dataset_entries, rep)}")
    return rep


def _print_quota(label: str, value: int, target: int) -> None:
    mark = "OK " if value >= target else "FAIL"
    print(f"{mark} {label}: {value}（目标 ≥{target}）")


def dataset_hash(entries: list[tuple[str, object | None]], rep: Report) -> str:
    """按题 id 升序规范化序列化后取 sha256（口径见模块 docstring）。"""
    items: list[tuple[str, object]] = []
    for name, obj in entries:
        if isinstance(obj, dict) and isinstance(obj.get("id"), str):
            items.append((obj["id"], obj))
        else:
            rep.warn(f"{name} 缺少可用的 id，未计入 dataset_hash")
    if not items:
        return "(无题目文件，dataset_hash 未定义)"
    items.sort(key=lambda pair: pair[0])
    canonical = "\n".join(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for _id, obj in items
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_single_file(target: Path) -> Report:
    rep = Report()
    schema = load_schema(target.parent, rep)
    obj = load_json(target, rep)
    if obj is not None:
        validate_question(obj, rep, schema, filename=target.name)
    print(f"== 单文件校验：{target} ==")
    return rep


# ---------------------------------------------------------------------------
# 输出与入口
# ---------------------------------------------------------------------------


def _report(rep: Report) -> None:
    for where, msg in rep.errors:
        print(f"[ERROR] {where} :: {msg}")
    for msg in rep.warnings:
        print(f"[WARN] {msg}")
    if rep.errors:
        print(f"结果：不通过（{len(rep.errors)} 处问题）")
    else:
        print("结果：通过")


def _force_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，中文输出改成 UTF-8，避免对方项目读到乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str]) -> int:
    _force_utf8_stdout()
    if len(argv) > 2:
        print("用法：python validate_golden.py [目录或单个 .json]", file=sys.stderr)
        return 2

    if len(argv) == 2:
        target = Path(argv[1]).resolve()
    else:
        target = Path(__file__).resolve().parent.parent / "eval" / "golden"

    if not target.exists():
        print(f"[ERROR] 路径不存在：{target}", file=sys.stderr)
        return 2

    print("注意：evidence 的 content 是否为原文片段（非转述）无法机器判定，仍需人工/映射阶段复核。")
    if target.is_dir():
        rep = validate_directory(target)
    else:
        rep = validate_single_file(target)
    _report(rep)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
