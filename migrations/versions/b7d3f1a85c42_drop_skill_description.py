"""drop skill description

Revision ID: b7d3f1a85c42
Revises: a1c4e9d27b30
Create Date: 2026-10-14 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d3f1a85c42'
down_revision: Union[str, Sequence[str], None] = 'a1c4e9d27b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('skill', 'description')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('skill', sa.Column('description', sa.String(length=500), nullable=True))
