"""Add session_event table for chronological event logging.

Revision ID: 0016_session_events
Revises: 0015_widget_revisions_ai_threads
Create Date: 2026-05-28

"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0016_session_events"
down_revision = "0015_widget_revisions_ai_threads"
branch_labels = None
depends_on = None


def _uuid() -> str:
    return str(uuid.uuid4())


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = _uuid_type(bind.dialect.name)

    # Session event table for slide advances + LLM interpret metadata
    op.create_table(
        "session_event",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_event_session", "session_event", ["session_id", "occurred_at"])
    op.create_index("ix_session_event_type", "session_event", ["session_id", "event_type"])

    # Workspace boolean for LLM prompt logging (privacy-sensitive, explicit column)
    op.add_column(
        "workspace",
        sa.Column(
            "log_llm_prompts_for_transcript",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0") if bind.dialect.name == "sqlite" else sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace", "log_llm_prompts_for_transcript")
    op.drop_index("ix_session_event_type")
    op.drop_index("ix_session_event_session")
    op.drop_table("session_event")
