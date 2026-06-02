"""Add workspace interpret quick options.

Revision ID: 0018_interpret_quick_options
Revises: 0017_ai_message_revision_cascade
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0018_interpret_quick_options"
down_revision = "0017_ai_message_revision_cascade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workspace") as batch:
        batch.add_column(
            sa.Column(
                "interpret_quick_options",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("workspace") as batch:
        batch.drop_column("interpret_quick_options")
