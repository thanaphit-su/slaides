"""default live interaction slides to current theme

Revision ID: 0007_session_slide_theme_default
Revises: 0006_log_session_slide
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_session_slide_theme_default"
down_revision = "0006_log_session_slide"
branch_labels = None
depends_on = None


def _bool_default(value: bool) -> sa.TextClause:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        return sa.text("1" if value else "0")
    return sa.text("true" if value else "false")


def upgrade() -> None:
    with op.batch_alter_table("session_slide") as batch:
        batch.alter_column(
            "inverted_theme",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=_bool_default(False),
        )


def downgrade() -> None:
    with op.batch_alter_table("session_slide") as batch:
        batch.alter_column(
            "inverted_theme",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=_bool_default(True),
        )
