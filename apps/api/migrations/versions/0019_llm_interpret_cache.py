"""Add per-session AI interpretation cache.

Revision ID: 0019_llm_interpret_cache
Revises: 0018_interpret_quick_options
Create Date: 2026-06-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0019_llm_interpret_cache"
down_revision = "0018_interpret_quick_options"
branch_labels = None
depends_on = None


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = _uuid_type(bind.dialect.name)
    id_type = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    false_default = sa.text("0") if bind.dialect.name == "sqlite" else sa.text("false")

    with op.batch_alter_table("llm_call") as batch:
        batch.add_column(sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=false_default))

    op.create_table(
        "llm_interpret_cache",
        sa.Column("id", id_type, primary_key=True, autoincrement=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("slide_id", uuid_type, nullable=True),
        sa.Column("selection_hash", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("model_parameters_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "session_id",
            "slide_id",
            "selection_hash",
            "prompt_hash",
            "model",
            "model_parameters_hash",
            name="uq_llm_interpret_cache_key",
        ),
    )
    op.create_index("ix_llm_interpret_cache_session", "llm_interpret_cache", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_interpret_cache_session", table_name="llm_interpret_cache")
    op.drop_table("llm_interpret_cache")
    with op.batch_alter_table("llm_call") as batch:
        batch.drop_column("cache_hit")
