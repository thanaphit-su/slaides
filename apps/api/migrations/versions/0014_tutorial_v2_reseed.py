"""Re-seed onboarding tutorial decks to v2.

Two bugs in v1:
1. §06 ("Quiet vs Loud") shipped two `{{widget:...}}` placeholders on a
   single slide, violating the system-wide "one widget per slide" rule.
2. Placement_ids were bare widget slugs (`live-poll`) instead of the
   `{slug}-{8hex}` shape the editor everywhere else generates.

v2 splits §06 into §06a (Quiet) + §06b (Loud) and rewrites the seed-time
markdown so every placeholder carries a random per-deck suffix.

This migration deletes every deck whose manifest has `is_tutorial: True`
(FK CASCADE drops slide / slide_widget / widget rows for that deck) and
re-seeds for each affected owner using the current `content` module.

Users who had already deleted their tutorial are not re-seeded — their
manifest row is gone, so the select doesn't find them.

Revision ID: 0014_tutorial_v2_reseed
Revises: 0013_session_is_preview
Create Date: 2026-05-26
"""
from __future__ import annotations

import json
import re
import secrets
import uuid as _uuid

import sqlalchemy as sa
from alembic import op


revision = "0014_tutorial_v2_reseed"
down_revision = "0013_session_is_preview"
branch_labels = None
depends_on = None


_WIDGET_PLACEHOLDER = re.compile(r"\{\{widget:([a-zA-Z0-9_-]+)\}\}")


def _new_id() -> str:
    return str(_uuid.uuid4())


def _suffix_placeholders(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Mirror of `onboarding.service._suffix_placeholders`, duplicated here
    so the migration stays stable if the service-layer helper is later
    refactored."""
    pairs: list[tuple[str, str]] = []
    by_slug: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        slug = match.group(1)
        placement_id = by_slug.get(slug)
        if placement_id is None:
            placement_id = f"{slug}-{secrets.token_hex(4)}"
            by_slug[slug] = placement_id
            pairs.append((slug, placement_id))
        return f"{{{{widget:{placement_id}}}}}"

    return _WIDGET_PLACEHOLDER.sub(replace, markdown), pairs


def upgrade() -> None:
    # Pulled in lazily — migrations otherwise avoid app imports, but the
    # tutorial markdown and widget bodies are the single source of truth
    # we'd duplicate by copying them here. content.py is pure data with
    # no app-runtime dependencies (no DB, no FastAPI), so the import is
    # safe and stable.
    from slaides.onboarding import content as tutorial

    bind = op.get_bind()

    # 1) Find every tutorial deck. Filter manifest in Python because JSON
    #    access syntax differs across SQLite + Postgres (matches
    #    `_find_existing_tutorial`'s reasoning in onboarding/service.py).
    deck_rows = bind.execute(
        sa.text("SELECT id, workspace_id, owner_id, manifest FROM deck")
    ).mappings().all()
    targets: list[tuple[str, str]] = []  # (workspace_id, owner_id)
    deck_ids_to_drop: list[str] = []
    for row in deck_rows:
        manifest = row["manifest"]
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except json.JSONDecodeError:
                continue
        if isinstance(manifest, dict) and manifest.get("is_tutorial") is True:
            deck_ids_to_drop.append(str(row["id"]))
            targets.append((str(row["workspace_id"]), str(row["owner_id"])))

    # 2) Delete each tutorial deck. Session.deck_id is intentionally not
    #    ON DELETE CASCADE, so runtime session rows must be removed first.
    #    LlmCall.session_id also has no cascade, so null it before deleting
    #    sessions; participant/question/interaction/session_slide/
    #    placement_state rows cascade from session.
    for deck_id in deck_ids_to_drop:
        session_ids = [
            str(row["id"])
            for row in bind.execute(
                sa.text("SELECT id FROM session WHERE deck_id = :id"),
                {"id": deck_id},
            ).mappings().all()
        ]
        if session_ids:
            bind.execute(
                sa.text("UPDATE llm_call SET session_id = NULL WHERE session_id IN :ids")
                .bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": session_ids},
            )
            bind.execute(
                sa.text("DELETE FROM session WHERE id IN :ids")
                .bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": session_ids},
            )
        bind.execute(sa.text("DELETE FROM deck WHERE id = :id"), {"id": deck_id})

    # 3) Re-seed v2 for every (workspace, owner) pair. Replicates
    #    `create_tutorial_for`'s ORM logic via raw SQL.
    for workspace_id, owner_id in targets:
        _seed_tutorial(bind, workspace_id, owner_id, tutorial)


def _seed_tutorial(bind, workspace_id: str, owner_id: str, tutorial) -> None:
    new_deck_id = _new_id()
    manifest = json.dumps(
        {"is_tutorial": True, "version": tutorial.TUTORIAL_VERSION}
    )

    bind.execute(
        sa.text(
            "INSERT INTO deck (id, workspace_id, owner_id, title, subtitle, manifest) "
            "VALUES (:id, :wid, :owner, :title, :subtitle, :manifest)"
        ),
        {
            "id": new_deck_id,
            "wid": workspace_id,
            "owner": owner_id,
            "title": tutorial.TUTORIAL_DECK_TITLE,
            "subtitle": tutorial.TUTORIAL_DECK_SUBTITLE,
            "manifest": manifest,
        },
    )

    widget_ids: dict[str, str] = {}
    for spec in tutorial.STARTER_WIDGETS:
        wid = _new_id()
        bind.execute(
            sa.text(
                "INSERT INTO widget "
                "(id, deck_id, name, kind, description, html, js, css, "
                " props_schema, tags, behavior, version) "
                "VALUES (:id, :deck, :name, :kind, :description, :html, :js, "
                "        :css, :props_schema, :tags, :behavior, :version)"
            ),
            {
                "id": wid,
                "deck": new_deck_id,
                "name": spec.name,
                "kind": spec.kind,
                "description": spec.description,
                "html": spec.html,
                "js": spec.js,
                "css": spec.css,
                "props_schema": json.dumps(spec.props_schema),
                "tags": json.dumps(list(spec.tags)),
                "behavior": json.dumps(spec.behavior),
                "version": "v0.1",
            },
        )
        widget_ids[spec.kind] = wid

    for position, slide_def in enumerate(tutorial.TUTORIAL_SLIDES):
        rewritten_md, placements = _suffix_placeholders(slide_def["markdown"])
        slide_id = _new_id()
        bind.execute(
            sa.text(
                "INSERT INTO slide "
                "(id, deck_id, section_id, position, kicker, markdown) "
                "VALUES (:id, :deck, NULL, :pos, :kicker, :md)"
            ),
            {
                "id": slide_id,
                "deck": new_deck_id,
                "pos": position,
                "kicker": slide_def["kicker"],
                "md": rewritten_md,
            },
        )
        for placement_position, (slug, placement_id) in enumerate(placements):
            wid = widget_ids.get(slug)
            if wid is None:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO slide_widget "
                    "(slide_id, placement_id, widget_id, props, position) "
                    "VALUES (:slide, :pid, :wid, :props, :pos)"
                ),
                {
                    "slide": slide_id,
                    "pid": placement_id,
                    "wid": wid,
                    "props": json.dumps({}),
                    "pos": placement_position,
                },
            )


def downgrade() -> None:
    # Lossy: existing v2 tutorials would need to be rolled back to v1, but
    # the v1 markdown is no longer in tree. Accept a one-way migration.
    pass
