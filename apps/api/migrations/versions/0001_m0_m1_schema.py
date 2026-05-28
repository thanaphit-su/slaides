"""m0+m1 schema: workspace, app_user, deck, section, slide

Revision ID: 0001_m0_m1
Revises:
Create Date: 2026-05-19

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_m0_m1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = sa.dialects.postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)

    op.create_table(
        "workspace",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("llm_base_url", sa.String(500), nullable=False, server_default="https://api.openai.com/v1"),
        sa.Column("llm_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("llm_model", sa.String(200), nullable=True, server_default="gpt-4.1-mini"),
        sa.Column("llm_caps", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "app_user",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="instructor"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "deck",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default="Untitled"),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("cover", sa.String(120), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "section",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("deck_id", uuid_type, sa.ForeignKey("deck.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_section_deck_position", "section", ["deck_id", "position"])

    op.create_table(
        "slide",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("deck_id", uuid_type, sa.ForeignKey("deck.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", uuid_type, sa.ForeignKey("section.id"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kicker", sa.String(300), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_slide_deck_position", "slide", ["deck_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_slide_deck_position", table_name="slide")
    op.drop_table("slide")
    op.drop_index("ix_section_deck_position", table_name="section")
    op.drop_table("section")
    op.drop_table("deck")
    op.drop_table("app_user")
    op.drop_table("workspace")
