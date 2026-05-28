"""m3 hotfix: drop FK on session.current_slide_id (can hold either slide.id or session_slide.id)

Revision ID: 0004_session_fixes
Revises: 0003_sessions
Create Date: 2026-05-19

"""
from __future__ import annotations

from alembic import op

revision = "0004_session_fixes"
down_revision = "0003_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # Drop the FK named by Postgres' default convention.
        op.execute("ALTER TABLE session DROP CONSTRAINT IF EXISTS session_current_slide_id_fkey")
    # SQLite test suite uses metadata.create_all from the model definitions, which
    # no longer declare a FK here — no migration needed.


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE session ADD CONSTRAINT session_current_slide_id_fkey "
            "FOREIGN KEY (current_slide_id) REFERENCES slide(id)"
        )
