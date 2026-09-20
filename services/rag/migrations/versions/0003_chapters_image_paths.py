"""chapters.image_paths：按章的图片相对路径（M0-3 补齐）

Revision ID: 0003_chapters_image_paths
Revises: 0002_chunks_embedding_nullable
Create Date: 2026-09-19

`index.jsonl[].images` 形如 `images/01_第1卷/007.jpg`，M0-02 §2 要求按章落库。
落库后目录接口才能重建 `marker → url` 映射：正文里是 `[插图007]`，
没有这份映射前端只能把标记原样显示出来。

类型选 `text[]` 而不是 jsonb：这份数据只整组读、不做键查询，jsonb 的查询能力用不上；
`text[]` 还能把元素类型钉死为 text，写入非字符串会直接失败，不必在应用层再校验一遍。

可空性：NOT NULL + 默认空数组。空数组与「这一章没有插图」同义，不用 NULL 再表达一次
「无值」——多一种缺失表示只会让消费方多一个分支。`server_default` 让既有行在 ALTER
时直接得到空数组，之后导入会显式写入真实路径；缺省保留，行插入漏写该列时也有确定值。

downgrade 直接删列。图片路径可由 `index.jsonl` 重导入恢复，不需要先做数据搬迁。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_chapters_image_paths"
down_revision: str | None = "0002_chunks_embedding_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_ARRAY = sa.text("'{}'::text[]")


def upgrade() -> None:
    op.add_column(
        "chapters",
        sa.Column(
            "image_paths",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=_EMPTY_ARRAY,
        ),
    )


def downgrade() -> None:
    op.drop_column("chapters", "image_paths")
