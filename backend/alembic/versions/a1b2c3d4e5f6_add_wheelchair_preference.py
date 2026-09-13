"""add wheelchair preference

Revision ID: a1b2c3d4e5f6
Revises: 17324cf663f8
Create Date: 2026-09-13 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '17324cf663f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增轮椅模式偏好列（存量行默认 false）。"""
    op.add_column(
        'user_preferences',
        sa.Column('wheelchair_mode', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """回滚轮椅模式偏好列。"""
    op.drop_column('user_preferences', 'wheelchair_mode')
