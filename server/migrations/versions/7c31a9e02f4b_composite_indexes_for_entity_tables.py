"""composite indexes for entity tables

针对两条高频查询模式补复合索引（单列索引已存在于 sid/status，此处优化组合查询）：
- (sid, status)：数据权限 scope 过滤 + 状态统计 —— 辅导员/院长看板、综测测算、审核中心按人过滤
- (status, createdAt)：状态筛选 + createdAt 倒序 —— 审核中心列表页

Revision ID: 7c31a9e02f4b
Revises: aecfe72dfde6
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c31a9e02f4b'
down_revision: Union[str, Sequence[str], None] = 'aecfe72dfde6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENTITY_TABLES = (
    "practices", "voluntarys", "honors", "certificates",
    "organizations", "parties", "innovations",
)


def upgrade() -> None:
    for t in ENTITY_TABLES:
        op.create_index(f"ix_{t}_sid_status", t, ["sid", "status"])
        op.create_index(f"ix_{t}_status_created", t, ["status", "createdAt"])


def downgrade() -> None:
    for t in ENTITY_TABLES:
        op.drop_index(f"ix_{t}_status_created", table_name=t)
        op.drop_index(f"ix_{t}_sid_status", table_name=t)
