"""Mark sessions created by the preview harness so we can clean them up.

Preview sessions are short-lived throwaway sessions spun up from the editor
when the instructor clicks "Preview" — they let the same widget run with
N fake audiences hitting the real aggregator path. Each new preview run
tears down the previous one for the same (deck, owner). The flag lets the
preview endpoint identify what to delete without confusing it with the
real sessions the instructor is still hosting.

Revision ID: 0013_session_is_preview
Revises: 0012_placement_state
Create Date: 2026-05-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_session_is_preview"
down_revision = "0012_placement_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session",
        sa.Column(
            "is_preview",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("session", "is_preview")
