"""两份契约的漂移守卫：共享 schema 结构等价，单侧 schema 只有登记过的那几个。

`rag-internal-v1.yaml` 与 `frontend-api-v1.yaml` 各自复制定义（不用跨文件 `$ref`），
所以形状漂移只能靠比对发现。比对忽略 description / example 这类说明文字，
只看语义：字段名、类型、required、enum 取值、数值边界、数组元素。

只属于一侧的 schema 必须显式登记；出现清单外的新单侧 schema 即失败。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# 仅外部契约有：进度端点在 Java 侧持久化，Python 不暴露（M0-01 §1）。
EXTERNAL_ONLY = {"Progress", "ProgressWrite"}
# 仅内部契约有：检索逐阶段明细只给评测 runner。
INTERNAL_ONLY = {"RetrievalOnlyResponse", "ScoredChunks"}

# 说明文字与文档字段不参与结构比较。
_IGNORED_KEYS = frozenset(
    {"description", "example", "examples", "title", "summary", "externalDocs"}
)

_SCHEMA_REF_PREFIX = "#/components/schemas/"


def _repository_root() -> Path:
    """向上找到仓库根：以 `contracts/openapi/` 为锚，测试在 services/rag 下跑。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "contracts" / "openapi" / "rag-internal-v1.yaml").is_file():
            return parent
    raise RuntimeError("向上找不到 contracts/openapi/rag-internal-v1.yaml，无法定位仓库根")


def _load_schemas(file_name: str) -> dict[str, Any]:
    path = _repository_root() / "contracts" / "openapi" / file_name
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    assert isinstance(schemas, dict) and schemas
    return schemas


EXTERNAL_SCHEMAS = _load_schemas("frontend-api-v1.yaml")
INTERNAL_SCHEMAS = _load_schemas("rag-internal-v1.yaml")
SHARED_SCHEMA_NAMES = sorted(set(EXTERNAL_SCHEMAS) & set(INTERNAL_SCHEMAS))


def _normalize(node: Any, schemas: dict[str, Any], resolving: frozenset[str]) -> Any:
    """把 schema 归一到可比较的形式：解引用、丢说明文字、required 排序。"""
    if isinstance(node, list):
        return [_normalize(item, schemas, resolving) for item in node]
    if not isinstance(node, dict):
        return node
    if _SCHEMA_REF_PREFIX in str(node.get("$ref", "")):
        name = str(node["$ref"])[len(_SCHEMA_REF_PREFIX) :]
        assert name in schemas, f"引用不存在的 schema：{name}"
        assert name not in resolving, f"schema 引用成环：{name}"
        return _normalize(schemas[name], schemas, resolving | {name})

    normalized: dict[str, Any] = {}
    for key in sorted(node):
        if key in _IGNORED_KEYS:
            continue
        value = node[key]
        if key == "required":
            value = sorted(value)
        normalized[key] = _normalize(value, schemas, resolving)
    return normalized


def _first_difference(path: str, left: Any, right: Any) -> str | None:
    """返回第一处差异的可读描述，没有差异则返回 None。"""
    if type(left) is not type(right):
        return f"{path}: 类型不同 {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return (
                f"{path}: 字段集合不同，仅外部 {sorted(set(left) - set(right))}，"
                f"仅内部 {sorted(set(right) - set(left))}"
            )
        for key in left:
            difference = _first_difference(f"{path}.{key}", left[key], right[key])
            if difference is not None:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: 列表长度不同 {len(left)} != {len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            difference = _first_difference(f"{path}[{index}]", left_item, right_item)
            if difference is not None:
                return difference
        return None
    if left != right:
        return f"{path}: 取值不同 {left!r} != {right!r}"
    return None


def test_shared_schema_set_is_not_empty() -> None:
    # 防止两边都读空时下面的断言变成平凡成立。
    assert len(SHARED_SCHEMA_NAMES) >= 10


@pytest.mark.parametrize("name", SHARED_SCHEMA_NAMES)
def test_shared_schema_is_structurally_equivalent(name: str) -> None:
    external = _normalize(EXTERNAL_SCHEMAS[name], EXTERNAL_SCHEMAS, frozenset({name}))
    internal = _normalize(INTERNAL_SCHEMAS[name], INTERNAL_SCHEMAS, frozenset({name}))

    difference = _first_difference(name, external, internal)
    assert difference is None, f"共享 schema {difference}"


def test_single_sided_schemas_match_registered_lists() -> None:
    assert set(EXTERNAL_SCHEMAS) - set(INTERNAL_SCHEMAS) == EXTERNAL_ONLY
    assert set(INTERNAL_SCHEMAS) - set(EXTERNAL_SCHEMAS) == INTERNAL_ONLY
