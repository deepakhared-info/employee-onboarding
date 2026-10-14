"""create skills and employee skills

Revision ID: a1c4e9d27b30
Revises: 77618429a265
Create Date: 2026-10-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e9d27b30'
down_revision: Union[str, Sequence[str], None] = '77618429a265'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('skill',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_skill_name'), 'skill', ['name'], unique=True)
    op.create_table('employeeskill',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('proficiency', sa.Enum('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT', name='proficiency', native_enum=False, length=20), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skill.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id', 'skill_id')
    )
    op.create_index(op.f('ix_employeeskill_employee_id'), 'employeeskill', ['employee_id'], unique=False)
    op.create_index(op.f('ix_employeeskill_skill_id'), 'employeeskill', ['skill_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_employeeskill_skill_id'), table_name='employeeskill')
    op.drop_index(op.f('ix_employeeskill_employee_id'), table_name='employeeskill')
    op.drop_table('employeeskill')
    op.drop_index(op.f('ix_skill_name'), table_name='skill')
    op.drop_table('skill')
