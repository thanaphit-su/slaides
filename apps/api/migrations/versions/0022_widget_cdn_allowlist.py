"""widget cdn allowlist

Revision ID: 0022_widget_cdn_allowlist
Revises: 0021_mirror_screen_access
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_widget_cdn_allowlist"
down_revision = "0021_mirror_screen_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace",
        sa.Column("widget_cdn_allowlist", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("workspace", "widget_cdn_allowlist")
