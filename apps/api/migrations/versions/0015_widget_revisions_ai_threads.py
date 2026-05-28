"""Add widget revisions and AI thread history.

Revision ID: 0015_widget_revisions_ai_threads
Revises: 0014_tutorial_v2_reseed
Create Date: 2026-05-26
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0015_widget_revisions_ai_threads"
down_revision = "0014_tutorial_v2_reseed"
branch_labels = None
depends_on = None


def _uuid() -> str:
    return str(uuid.uuid4())


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def _json(value) -> str:
    if value is None:
        return json.dumps({})
    if isinstance(value, str):
        return value
    return json.dumps(value)


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = _uuid_type(bind.dialect.name)

    op.create_table(
        "widget_revision",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "widget_id",
            uuid_type,
            sa.ForeignKey("widget.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False, server_default=""),
        sa.Column("js", sa.Text(), nullable=True),
        sa.Column("css", sa.Text(), nullable=True),
        sa.Column("props_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("example_props", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "behavior",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{\"kind\": \"quiet\"}'"),
        ),
        sa.Column("ai_spec", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_reason", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("widget_id", "version_number", name="uq_widget_revision_version"),
    )
    op.create_index("ix_widget_revision_widget", "widget_revision", ["widget_id", "version_number"])

    with op.batch_alter_table("widget") as batch:
        batch.add_column(sa.Column("current_revision_id", uuid_type, nullable=True))
    with op.batch_alter_table("slide_widget") as batch:
        batch.add_column(sa.Column("revision_id", uuid_type, nullable=True))

    rows = bind.execute(
        sa.text("SELECT id, html, js, css, props_schema, behavior FROM widget")
    ).mappings().all()
    for row in rows:
        revision_id = _uuid()
        bind.execute(
            sa.text(
                """
                INSERT INTO widget_revision
                  (id, widget_id, version_number, html, js, css, props_schema, example_props,
                   behavior, ai_spec, created_reason)
                VALUES
                  (:id, :widget_id, 1, :html, :js, :css, :props_schema, :example_props,
                   :behavior, :ai_spec, :created_reason)
                """
            ),
            {
                "id": revision_id,
                "widget_id": str(row["id"]),
                "html": row["html"] or "",
                "js": row["js"],
                "css": row["css"],
                "props_schema": _json(row["props_schema"]),
                "example_props": json.dumps({}),
                "behavior": _json(row["behavior"] or {"kind": "quiet"}),
                "ai_spec": json.dumps({}),
                "created_reason": "migration_backfill",
            },
        )
        bind.execute(
            sa.text("UPDATE widget SET current_revision_id = :revision_id WHERE id = :widget_id"),
            {"revision_id": revision_id, "widget_id": str(row["id"])},
        )
        bind.execute(
            sa.text("UPDATE slide_widget SET revision_id = :revision_id WHERE widget_id = :widget_id"),
            {"revision_id": revision_id, "widget_id": str(row["id"])},
        )

    # Enforce the current-revision pointer in Postgres. SQLite is used only for
    # tests/dev here; adding this FK through batch mode rebuilds the legacy
    # `widget` table and can fail on older server-default syntax from previous
    # migrations. Runtime ownership checks still validate revision/widget pairs.
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_widget_current_revision",
            "widget",
            "widget_revision",
            ["current_revision_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_slide_widget_revision",
            "slide_widget",
            "widget_revision",
            ["revision_id"],
            ["id"],
        )

    op.create_table(
        "widget_ai_thread",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "widget_id",
            uuid_type,
            sa.ForeignKey("widget.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("compact_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "widget_ai_message",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "thread_id",
            uuid_type,
            sa.ForeignKey("widget_ai_thread.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("revision_id", uuid_type, sa.ForeignKey("widget_revision.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_widget_ai_message_thread_created",
        "widget_ai_message",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_widget_ai_message_thread_created", table_name="widget_ai_message")
    op.drop_table("widget_ai_message")
    op.drop_table("widget_ai_thread")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_slide_widget_revision", "slide_widget", type_="foreignkey")
        op.drop_constraint("fk_widget_current_revision", "widget", type_="foreignkey")
    with op.batch_alter_table("slide_widget") as batch:
        batch.drop_column("revision_id")
    with op.batch_alter_table("widget") as batch:
        batch.drop_column("current_revision_id")
    op.drop_index("ix_widget_revision_widget", table_name="widget_revision")
    op.drop_table("widget_revision")
