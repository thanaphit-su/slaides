"""m2 schema: widget + slide_widget

Revision ID: 0002_widgets
Revises: 0001_m0_m1
Create Date: 2026-05-19

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_widgets"
down_revision = "0001_m0_m1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    uuid_type = sa.dialects.postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)

    op.create_table(
        "widget",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("description", sa.String(600), nullable=True),
        sa.Column("html", sa.Text(), nullable=False, server_default=""),
        sa.Column("js", sa.Text(), nullable=True),
        sa.Column("css", sa.Text(), nullable=True),
        sa.Column("props_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("version", sa.String(40), nullable=False, server_default="v0.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_widget_workspace", "widget", ["workspace_id"])

    op.create_table(
        "slide_widget",
        sa.Column("slide_id", uuid_type, sa.ForeignKey("slide.id", ondelete="CASCADE"), nullable=False),
        sa.Column("placement_id", sa.String(80), nullable=False),
        sa.Column("widget_id", uuid_type, sa.ForeignKey("widget.id"), nullable=False),
        sa.Column("props", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("slide_id", "placement_id"),
    )


def downgrade() -> None:
    op.drop_table("slide_widget")
    op.drop_index("ix_widget_workspace", table_name="widget")
    op.drop_table("widget")
