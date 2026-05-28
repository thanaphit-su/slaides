"""Widgets v2 Step 4 — placement_state table for Loud widgets.

Each Loud-widget placement during a session gets one row keyed by
`(session_id, placement_id)`. `state` is the audience-visible projection
(produced by one of the five aggregators); `state_version` increments on
every aggregation pass so out-of-order broadcasts can't roll back.

Rows are frozen forever after `closed_at` (or the session ends) — they're
how the transcript view reconstructs interactions after the fact.

Revision ID: 0012_placement_state
Revises: 0011_widget_deck_local
Create Date: 2026-05-24

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_placement_state"
down_revision = "0011_widget_deck_local"
branch_labels = None
depends_on = None


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = _uuid_type(dialect)

    op.create_table(
        "placement_state",
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("placement_id", sa.String(length=80), nullable=False),
        sa.Column("widget_id", uuid_type, nullable=True),
        sa.Column("aggregator", sa.String(length=40), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("contribution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("session_id", "placement_id", name="pk_placement_state"),
    )
    op.create_index(
        "ix_placement_state_session", "placement_state", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_placement_state_session", table_name="placement_state")
    op.drop_table("placement_state")
