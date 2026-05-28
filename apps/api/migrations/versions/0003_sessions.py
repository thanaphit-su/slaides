"""m3 schema: session + participant + question + interaction_log + session_slide

Revision ID: 0003_sessions
Revises: 0002_widgets
Create Date: 2026-05-19

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_sessions"
down_revision = "0002_widgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = sa.dialects.postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)

    op.create_table(
        "session",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("deck_id", uuid_type, sa.ForeignKey("deck.id"), nullable=False),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("salt", sa.String(64), nullable=False),
        sa.Column("current_slide_id", uuid_type, sa.ForeignKey("slide.id"), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_code", "session", ["code"], unique=True)
    op.create_index("ix_session_workspace", "session", ["workspace_id"])

    op.create_table(
        "participant",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid_type, sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("anon", sa.Boolean(), nullable=False, server_default=sa.text("0") if dialect == "sqlite" else sa.text("false")),
        sa.Column("ref", sa.String(64), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "ref", name="uq_participant_session_ref"),
    )
    op.create_index("ix_participant_session", "participant", ["session_id"])

    op.create_table(
        "question",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slide_id", uuid_type, sa.ForeignKey("slide.id"), nullable=True),
        sa.Column("participant_ref", sa.String(64), nullable=False),
        sa.Column("anon", sa.Boolean(), nullable=False, server_default=sa.text("0") if dialect == "sqlite" else sa.text("false")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_question_session", "question", ["session_id", "raised_at"])

    op.create_table(
        "interaction_log",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slide_id", uuid_type, sa.ForeignKey("slide.id"), nullable=True),
        sa.Column("widget_id", uuid_type, sa.ForeignKey("widget.id"), nullable=True),
        sa.Column("participant_ref", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_log_session", "interaction_log", ["session_id", "occurred_at"])
    op.create_index("ix_log_widget", "interaction_log", ["widget_id"])

    op.create_table(
        "session_slide",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("session_id", uuid_type, sa.ForeignKey("session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_slide_id", uuid_type, sa.ForeignKey("slide.id"), nullable=True),
        sa.Column("widget_id", uuid_type, sa.ForeignKey("widget.id"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("results", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("inverted_theme", sa.Boolean(), nullable=False, server_default=sa.text("1") if dialect == "sqlite" else sa.text("true")),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_slide_session", "session_slide", ["session_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_session_slide_session", table_name="session_slide")
    op.drop_table("session_slide")
    op.drop_index("ix_log_widget", table_name="interaction_log")
    op.drop_index("ix_log_session", table_name="interaction_log")
    op.drop_table("interaction_log")
    op.drop_index("ix_question_session", table_name="question")
    op.drop_table("question")
    op.drop_index("ix_participant_session", table_name="participant")
    op.drop_table("participant")
    op.drop_index("ix_session_workspace", table_name="session")
    op.drop_index("ix_session_code", table_name="session")
    op.drop_table("session")
