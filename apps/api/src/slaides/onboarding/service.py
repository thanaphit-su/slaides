"""Provision the welcome tutorial deck + starter widget pack for an instructor.

`create_tutorial_for(session, user)` is idempotent — re-running against a user
who already has a tutorial deck (identified by `deck.manifest.is_tutorial`)
returns the existing deck without touching it. That way the approval script
can be re-run safely, and a user who *deletes* their tutorial gets to keep it
deleted (we only check; we don't recreate).
"""
from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppUser, Deck, Slide, SlideWidget, Widget, WidgetRevision
from . import content

_WIDGET_PLACEHOLDER = re.compile(r"\{\{widget:([a-zA-Z0-9_-]+)\}\}")


def _suffix_placeholders(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Rewrite every `{{widget:<slug>}}` token in `markdown` to
    `{{widget:<slug>-<8hex>}}`, matching the format the editor generates
    (`stores/editor.ts:156`). Returns the rewritten markdown and an ordered
    list of `(slug, placement_id)` pairs the caller persists as SlideWidget
    rows. Duplicate slugs on the same slide share the same placement_id —
    we still expect one widget per slide elsewhere, but the helper defends
    against author typos by deduping rather than minting two ids."""
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

    new_md = _WIDGET_PLACEHOLDER.sub(replace, markdown)
    return new_md, pairs


async def create_tutorial_for(session: AsyncSession, user: AppUser) -> Deck:
    """Idempotently create the welcome deck + starter widgets for `user`.

    Returns the deck (existing or newly created). Caller is responsible for
    committing the transaction.
    """
    existing = await _find_existing_tutorial(session, user)
    if existing is not None:
        return existing

    deck = Deck(
        workspace_id=user.workspace_id,
        owner_id=user.id,
        title=content.TUTORIAL_DECK_TITLE,
        subtitle=content.TUTORIAL_DECK_SUBTITLE,
        manifest={"is_tutorial": True, "version": content.TUTORIAL_VERSION},
    )
    session.add(deck)
    await session.flush()

    # Create one widget row per starter pack entry, owned by this deck.
    widget_ids: dict[str, uuid.UUID] = {}
    revision_ids: dict[str, uuid.UUID] = {}
    for spec in content.STARTER_WIDGETS:
        widget = Widget(
            deck_id=deck.id,
            name=spec.name,
            kind=spec.kind,
            description=spec.description,
            html="",
            js=None,
            css=None,
            props_schema={},
            tags=list(spec.tags),
            behavior={"kind": "quiet"},
        )
        session.add(widget)
        await session.flush()
        revision = WidgetRevision(
            widget_id=widget.id,
            version_number=1,
            html=spec.html,
            js=spec.js,
            css=spec.css,
            props_schema=spec.props_schema or {},
            example_props={},
            behavior=spec.behavior or {"kind": "quiet"},
            ai_spec={},
            created_reason="tutorial_seed",
        )
        session.add(revision)
        await session.flush()
        widget.current_revision_id = revision.id
        widget.html = revision.html
        widget.js = revision.js
        widget.css = revision.css
        widget.props_schema = revision.props_schema
        widget.behavior = revision.behavior
        widget_ids[spec.kind] = widget.id
        revision_ids[spec.kind] = revision.id

    # Create slides in order. Each slide's markdown may carry one or more
    # `{{widget:<slug>}}` placeholders. `_suffix_placeholders` rewrites them
    # to `{{widget:<slug>-<8hex>}}` (matching the editor's convention) and
    # returns the (slug, placement_id) pairs so we can mint a SlideWidget
    # row pointing at the just-created widget.
    for position, slide_def in enumerate(content.TUTORIAL_SLIDES):
        rewritten_md, placements = _suffix_placeholders(slide_def["markdown"])
        slide = Slide(
            deck_id=deck.id,
            section_id=None,
            position=position,
            kicker=slide_def["kicker"],
            markdown=rewritten_md,
        )
        session.add(slide)
        await session.flush()
        for placement_position, (slug, placement_id) in enumerate(placements):
            widget_id = widget_ids.get(slug)
            if widget_id is None:
                # Authoring mistake — placeholder references a widget the
                # starter pack doesn't ship. Skip silently so the rest of
                # the deck still provisions; test_onboarding has a check
                # that catches this in CI.
                continue
            placement = SlideWidget(
                slide_id=slide.id,
                placement_id=placement_id,
                widget_id=widget_id,
                revision_id=revision_ids.get(slug),
                props={},
                position=placement_position,
            )
            session.add(placement)

    await session.flush()
    return deck


async def _find_existing_tutorial(session: AsyncSession, user: AppUser) -> Deck | None:
    """Return an existing tutorial deck for `user`, or None.

    The check is `manifest.is_tutorial == True` evaluated in Python because
    JSONB containment syntax differs between Postgres and SQLite and the
    decks-per-user count is tiny (single-digit).
    """
    rows = (
        await session.execute(
            select(Deck).where(
                Deck.workspace_id == user.workspace_id,
                Deck.owner_id == user.id,
            )
        )
    ).scalars()
    for deck in rows:
        if isinstance(deck.manifest, dict) and deck.manifest.get("is_tutorial") is True:
            return deck
    return None
