"""make skill names unique case-insensitively

Revision ID: d4f6a8c2e1b7
Revises: b3c8d7aa7e2a
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4f6a8c2e1b7'
down_revision: Union[str, Sequence[str], None] = 'b3c8d7aa7e2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Merge existing case-variants ("Python"/"python") into the lowest-id skill.
    op.execute("""
        CREATE TEMP TABLE skill_merge ON COMMIT DROP AS
        SELECT id AS old_id, MIN(id) OVER (PARTITION BY lower(name)) AS keep_id
        FROM skill
    """)
    # An employee holding both variants keeps the lowest-id link's row; drop the other.
    op.execute("""
        DELETE FROM employeeskill es
        USING skill_merge m
        WHERE es.skill_id = m.old_id AND m.old_id <> m.keep_id
          AND EXISTS (
            SELECT 1 FROM employeeskill k
            WHERE k.employee_id = es.employee_id AND k.skill_id = m.keep_id
          )
    """)
    op.execute("""
        DELETE FROM employeeskill es
        USING skill_merge m
        WHERE es.skill_id = m.old_id AND m.old_id <> m.keep_id
          AND EXISTS (
            SELECT 1 FROM employeeskill o JOIN skill_merge mo ON mo.old_id = o.skill_id
            WHERE o.employee_id = es.employee_id AND mo.keep_id = m.keep_id
              AND o.skill_id < es.skill_id
          )
    """)
    op.execute("""
        UPDATE employeeskill es SET skill_id = m.keep_id
        FROM skill_merge m
        WHERE es.skill_id = m.old_id AND m.old_id <> m.keep_id
    """)
    op.execute("DELETE FROM skill s USING skill_merge m WHERE s.id = m.old_id AND m.old_id <> m.keep_id")

    op.drop_index('ix_skill_name', table_name='skill')
    op.execute("CREATE UNIQUE INDEX ix_skill_name_lower ON skill (lower(name))")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_skill_name_lower', table_name='skill')
    op.create_index('ix_skill_name', 'skill', ['name'], unique=True)
