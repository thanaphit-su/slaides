"""split workspace.llm_caps into llm_models + llm_capability_models

The single `llm_caps` JSON column was carrying three different things at
once: capability booleans (`inline_write`, `interpret`, `widget_generate`),
the per-workspace model library (`_models`), and the capability→model id
map (`_capability_models`).

This migration moves `_models` and `_capability_models` into their own JSON
columns and drops `llm_caps`. Capability booleans are no longer stored —
they're derived from the capability-model map at API response time
(a capability whose value is `None` is disabled).

Revision ID: 0010_split_workspace_llm_caps
Revises: 0009_drop_app_user_password_hash
Create Date: 2026-05-23

"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0010_split_workspace_llm_caps"
down_revision = "0009_drop_app_user_password_hash"
branch_labels = None
depends_on = None

CAPABILITIES = ("inline_write", "interpret", "widget_generate")


def upgrade() -> None:
    with op.batch_alter_table("workspace") as batch:
        batch.add_column(
            sa.Column("llm_models", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.add_column(
            sa.Column(
                "llm_capability_models",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )

    # Data-migrate existing rows: pull `_models` / `_capability_models` out of
    # `llm_caps` into the new columns. We use raw SQL keyed by id to avoid
    # depending on the ORM model (which is one step ahead by this point).
    conn = op.get_bind()
    rows = list(conn.execute(sa.text("SELECT id, llm_caps FROM workspace")))
    for row in rows:
        raw = row.llm_caps
        if isinstance(raw, str):
            try:
                caps = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                caps = {}
        elif isinstance(raw, dict):
            caps = raw
        else:
            caps = {}
        models = caps.get("_models") if isinstance(caps.get("_models"), list) else []
        assignments_raw = caps.get("_capability_models")
        assignments = assignments_raw if isinstance(assignments_raw, dict) else {}
        # Preserve disabled capability state — if the row had `inline_write: False`
        # in caps, mirror it into the new map as None.
        for cap in CAPABILITIES:
            if caps.get(cap) is False:
                assignments[cap] = None
        conn.execute(
            sa.text(
                "UPDATE workspace SET llm_models = :models, llm_capability_models = :caps "
                "WHERE id = :id"
            ),
            {
                "id": row.id,
                "models": json.dumps(models),
                "caps": json.dumps(assignments),
            },
        )

    with op.batch_alter_table("workspace") as batch:
        batch.drop_column("llm_caps")


def downgrade() -> None:
    with op.batch_alter_table("workspace") as batch:
        batch.add_column(
            sa.Column("llm_caps", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )

    # Fold the split columns back into llm_caps, including derived booleans.
    conn = op.get_bind()
    rows = list(
        conn.execute(
            sa.text("SELECT id, llm_models, llm_capability_models FROM workspace")
        )
    )
    for row in rows:
        models = _maybe_json(row.llm_models, default=[])
        assignments = _maybe_json(row.llm_capability_models, default={})
        caps: dict = {}
        for cap in CAPABILITIES:
            caps[cap] = assignments.get(cap) is not None
        caps["_models"] = models
        caps["_capability_models"] = assignments
        conn.execute(
            sa.text("UPDATE workspace SET llm_caps = :caps WHERE id = :id"),
            {"id": row.id, "caps": json.dumps(caps)},
        )

    with op.batch_alter_table("workspace") as batch:
        batch.drop_column("llm_models")
        batch.drop_column("llm_capability_models")


def _maybe_json(value, *, default):
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except json.JSONDecodeError:
            return default
    if value is None:
        return default
    return value
