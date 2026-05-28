"""m5 prep: link interaction_log to its owning session_slide

Revision ID: 0006_log_session_slide
Revises: 0005_llm_calls
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_log_session_slide"
down_revision = "0005_llm_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = sa.dialects.postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)

    op.add_column(
        "interaction_log",
        sa.Column("session_slide_id", uuid_type, sa.ForeignKey("session_slide.id"), nullable=True),
    )
    op.create_index("ix_log_session_slide", "interaction_log", ["session_slide_id"])


def downgrade() -> None:
    op.drop_index("ix_log_session_slide", table_name="interaction_log")
    op.drop_column("interaction_log", "session_slide_id")
