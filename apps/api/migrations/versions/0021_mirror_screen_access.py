"""mirror screen access

Revision ID: 0021_mirror_screen_access
Revises: 0020_slide_presenter_notes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_mirror_screen_access"
down_revision = "0020_slide_presenter_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deck",
        sa.Column("mirror_access_mode", sa.String(length=24), nullable=False, server_default="owner"),
    )
    op.add_column(
        "deck",
        sa.Column("mirror_allowed_emails", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("session", sa.Column("mirror_token", sa.String(length=64), nullable=True))
    op.create_index("ix_session_mirror_token", "session", ["mirror_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_session_mirror_token", table_name="session")
    op.drop_column("session", "mirror_token")
    op.drop_column("deck", "mirror_allowed_emails")
    op.drop_column("deck", "mirror_access_mode")
