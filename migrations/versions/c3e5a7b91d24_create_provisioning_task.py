"""create provisioning task

Revision ID: c3e5a7b91d24
Revises: b7d3f1a85c42
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e5a7b91d24'
down_revision: Union[str, Sequence[str], None] = 'b7d3f1a85c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('provisioningtask',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('service', sa.Enum('HR_OPERATIONS', 'IT_SERVICES', 'ACCESS_PROVISION', name='provisioningservice', native_enum=False, length=30), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', name='provisioningstatus', native_enum=False, length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id', 'service')
    )
    op.create_index(op.f('ix_provisioningtask_employee_id'), 'provisioningtask', ['employee_id'], unique=False)
    op.create_index('ix_provisioningtask_status_next_run_at', 'provisioningtask', ['status', 'next_run_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_provisioningtask_status_next_run_at', table_name='provisioningtask')
    op.drop_index(op.f('ix_provisioningtask_employee_id'), table_name='provisioningtask')
    op.drop_table('provisioningtask')
