"""Widgets v2 Step 2 — deck-local widget ownership.

Replaces `widget.workspace_id` with `widget.deck_id` and adds two new columns:

  - `derived_from_id`: soft (no-FK) pointer back to the widget a copy was
    cloned from. Informational only — never enforces cascade.
  - `behavior`: JSON declaring whether the widget is Quiet or Loud. Defaults
    to `{"kind": "quiet"}` since no existing widget implements the Loud
    protocol yet.

Data migration (snapshot copy, the user-approved Migration A):

  1. For each widget, find the distinct decks that reference it via
     `slide_widget -> slide -> deck`.
  2. If exactly one deck references it: set `widget.deck_id` to that deck.
  3. If multiple decks reference it: keep the original on the first deck and
     clone it into each additional deck with `derived_from_id` set; repoint
     `slide_widget.widget_id` in those extra decks to the clones.
  4. If no deck references it (an unused workspace-library widget):
     materialise a per-workspace auto-deck named "Library" and park the
     widget there.

After data migration the `deck_id` column is set to NOT NULL and
`workspace_id` is dropped.

Revision ID: 0011_widget_deck_local
Revises: 0010_split_workspace_llm_caps
Create Date: 2026-05-24

"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_widget_deck_local"
down_revision = "0010_split_workspace_llm_caps"
branch_labels = None
depends_on = None


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def _new_id() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    uuid_type = _uuid_type(dialect)

    # Step 1 — add the three new columns. `deck_id` is nullable for now so we
    # can data-migrate; tightened to NOT NULL at the bottom.
    with op.batch_alter_table("widget") as batch:
        batch.add_column(sa.Column("deck_id", uuid_type, nullable=True))
        batch.add_column(sa.Column("derived_from_id", uuid_type, nullable=True))
        batch.add_column(
            sa.Column(
                "behavior",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{\"kind\": \"quiet\"}'"),
            )
        )

    # Step 2 — data-migrate.
    widgets = list(
        bind.execute(sa.text("SELECT id, workspace_id FROM widget")).mappings()
    )
    library_deck_by_workspace: dict[str, str] = {}

    def _str_id(v) -> str:
        return str(v)

    for w in widgets:
        widget_id = _str_id(w["id"])
        workspace_id = _str_id(w["workspace_id"])

        deck_rows = list(
            bind.execute(
                sa.text(
                    "SELECT DISTINCT s.deck_id AS deck_id "
                    "FROM slide_widget sw "
                    "JOIN slide s ON s.id = sw.slide_id "
                    "WHERE sw.widget_id = :wid"
                ),
                {"wid": widget_id},
            ).mappings()
        )
        deck_ids = [_str_id(row["deck_id"]) for row in deck_rows]

        if not deck_ids:
            # Unreferenced widget → land in this workspace's Library deck.
            lib_id = library_deck_by_workspace.get(workspace_id)
            if lib_id is None:
                owner_row = bind.execute(
                    sa.text(
                        "SELECT id FROM app_user "
                        "WHERE workspace_id = :wid AND approval_status = 'approved' "
                        "ORDER BY created_at ASC LIMIT 1"
                    ),
                    {"wid": workspace_id},
                ).first()
                if owner_row is None:
                    owner_row = bind.execute(
                        sa.text(
                            "SELECT id FROM app_user WHERE workspace_id = :wid "
                            "ORDER BY created_at ASC LIMIT 1"
                        ),
                        {"wid": workspace_id},
                    ).first()
                if owner_row is None:
                    # Truly orphaned widget — workspace has no instructor.
                    # Skip data-migration; the NOT NULL tightening below will
                    # raise so the operator notices.
                    continue
                owner_id = _str_id(owner_row[0])
                lib_id = _new_id()
                bind.execute(
                    sa.text(
                        "INSERT INTO deck (id, workspace_id, owner_id, title, subtitle, cover, manifest, created_at, updated_at) "
                        "VALUES (:id, :wid, :owner, :title, NULL, NULL, :manifest, "
                        "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": lib_id,
                        "wid": workspace_id,
                        "owner": owner_id,
                        "title": "Library",
                        "manifest": json.dumps({"auto_library": True}),
                    },
                )
                library_deck_by_workspace[workspace_id] = lib_id
            bind.execute(
                sa.text("UPDATE widget SET deck_id = :did WHERE id = :wid"),
                {"did": lib_id, "wid": widget_id},
            )
        elif len(deck_ids) == 1:
            bind.execute(
                sa.text("UPDATE widget SET deck_id = :did WHERE id = :wid"),
                {"did": deck_ids[0], "wid": widget_id},
            )
        else:
            primary = deck_ids[0]
            bind.execute(
                sa.text("UPDATE widget SET deck_id = :did WHERE id = :wid"),
                {"did": primary, "wid": widget_id},
            )
            for extra_deck in deck_ids[1:]:
                clone_id = _new_id()
                bind.execute(
                    sa.text(
                        "INSERT INTO widget "
                        "(id, workspace_id, deck_id, derived_from_id, name, kind, description, "
                        "  html, js, css, props_schema, tags, version, behavior, created_at, updated_at) "
                        "SELECT :new_id, workspace_id, :did, :src, name, kind, description, "
                        "  html, js, css, props_schema, tags, version, behavior, "
                        "  CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                        "FROM widget WHERE id = :src"
                    ),
                    {"new_id": clone_id, "did": extra_deck, "src": widget_id},
                )
                bind.execute(
                    sa.text(
                        "UPDATE slide_widget SET widget_id = :new_id "
                        "WHERE widget_id = :src AND slide_id IN ("
                        "  SELECT id FROM slide WHERE deck_id = :did"
                        ")"
                    ),
                    {"new_id": clone_id, "src": widget_id, "did": extra_deck},
                )

    # Step 3 — tighten constraint; drop workspace_id.
    with op.batch_alter_table("widget") as batch:
        batch.alter_column("deck_id", nullable=False)
        # Postgres named the original FK after the column.
        if dialect == "postgresql":
            batch.drop_constraint("widget_workspace_id_fkey", type_="foreignkey")
        batch.create_foreign_key(
            "widget_deck_id_fkey",
            "deck",
            ["deck_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_column("workspace_id")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    uuid_type = _uuid_type(dialect)

    # Re-add workspace_id, populate from deck.workspace_id.
    with op.batch_alter_table("widget") as batch:
        batch.add_column(sa.Column("workspace_id", uuid_type, nullable=True))

    bind.execute(
        sa.text(
            "UPDATE widget SET workspace_id = ("
            "  SELECT workspace_id FROM deck WHERE deck.id = widget.deck_id"
            ")"
        )
    )

    with op.batch_alter_table("widget") as batch:
        batch.alter_column("workspace_id", nullable=False)
        batch.create_foreign_key(
            "widget_workspace_id_fkey",
            "workspace",
            ["workspace_id"],
            ["id"],
        )
        if dialect == "postgresql":
            batch.drop_constraint("widget_deck_id_fkey", type_="foreignkey")
        batch.drop_column("deck_id")
        batch.drop_column("derived_from_id")
        batch.drop_column("behavior")
