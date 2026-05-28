"""m4 llm accounting

Revision ID: 0005_llm_calls
Revises: 0004_session_fixes
Create Date: 2026-05-19

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_llm_calls"
down_revision = "0004_session_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = sa.dialects.postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)
    id_type = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    op.create_table(
        "llm_call",
        sa.Column("id", id_type, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("user_id", uuid_type, sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id"), nullable=True),
        sa.Column("purpose", sa.String(60), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_call_workspace", "llm_call", ["workspace_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_workspace", table_name="llm_call")
    op.drop_table("llm_call")
