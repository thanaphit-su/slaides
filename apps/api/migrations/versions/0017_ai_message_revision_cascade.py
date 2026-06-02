"""Make widget_ai_message.revision_id cascade on revision delete.

`widget_ai_message.revision_id` → `widget_revision.id` was created NO ACTION
(migration 0015). Deleting a widget cascades to `widget_revision`, but Postgres
runs that cascade before the `widget` → thread → message cascade clears the
messages, so the NO ACTION check on `widget_ai_message_revision_id_fkey` trips
with a ForeignKeyViolationError. Revisions are only ever deleted alongside their
owning widget (no independent revision-prune path exists), so cascading the
message delete here is safe and removes the need for callers to hand-order the
thread delete before the widget delete.

SQLite enforces FKs softly in the test suite and rebuilding the table to alter a
constraint is disruptive, so this is a Postgres-only constraint swap.

Revision ID: 0017_ai_message_revision_cascade
Revises: 0016_session_events
Create Date: 2026-06-02

"""
from __future__ import annotations

from alembic import op


revision = "0017_ai_message_revision_cascade"
down_revision = "0016_session_events"
branch_labels = None
depends_on = None

_CONSTRAINT = "widget_ai_message_revision_id_fkey"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint(_CONSTRAINT, "widget_ai_message", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "widget_ai_message",
        "widget_revision",
        ["revision_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint(_CONSTRAINT, "widget_ai_message", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "widget_ai_message",
        "widget_revision",
        ["revision_id"],
        ["id"],
    )
