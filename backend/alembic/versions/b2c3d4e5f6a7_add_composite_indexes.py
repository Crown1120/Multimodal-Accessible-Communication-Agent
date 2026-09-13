"""add composite indexes for history and run recovery

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-13 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """历史消息按会话+时间读取、卡死运行按状态+时间回收，补复合索引。"""
    op.create_index(
        'ix_messages_session_created', 'messages', ['session_id', 'created_at']
    )
    op.create_index(
        'ix_agent_runs_status_created', 'agent_runs', ['status', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_agent_runs_status_created', table_name='agent_runs')
    op.drop_index('ix_messages_session_created', table_name='messages')
