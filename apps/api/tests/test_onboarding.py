"""Tests for the tutorial-deck + starter-widget pack provisioning.

These cover:
- `create_tutorial_for` builds the right shape on first call.
- Idempotency on re-run for the same user.
- Each starter widget passes every contract scanner (theme/layout/behavior).
- Each widget's default props validate against its own props_schema.
- Slide markdown widget placeholders only reference widgets the pack ships.
"""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import select

from slaides.db.base import get_session_factory
from slaides.db.models import AppUser, Deck, Slide, SlideWidget, Widget, WidgetRevision, Workspace
from slaides.onboarding.content import STARTER_WIDGETS, TUTORIAL_SLIDES, TUTORIAL_VERSION
from slaides.onboarding.service import (
    _WIDGET_PLACEHOLDER,
    _suffix_placeholders,
    create_tutorial_for,
)


# Suffixed placement_id contract (matches editor.ts:156 `${kind}-${uuid8}`).
_PLACEMENT_ID_RE = re.compile(r"^[a-z0-9_-]+-[0-9a-f]{8}$")


async def _make_user(db, *, email: str = "fresh@example.com") -> AppUser:
    """Build a workspace + an approved user inside a passed AsyncSession."""
    ws = Workspace(name=f"Test Workspace for {email}")
    db.add(ws)
    await db.flush()
    user = AppUser(
        workspace_id=ws.id,
        email=email,
        display_name="Fresh User",
        role="instructor",
        approval_status="approved",
    )
    db.add(user)
    await db.flush()
    return user


async def test_create_tutorial_for_builds_expected_deck(app_with_db):
    factory = get_session_factory()
    async with factory() as db:
        user = await _make_user(db, email="alice-onboarding@example.com")
        deck = await create_tutorial_for(db, user)
        await db.commit()

        # The deck is flagged so the next provisioning pass can recognise it.
        assert deck.title  # truthy non-empty
        assert deck.manifest.get("is_tutorial") is True
        assert deck.workspace_id == user.workspace_id
        assert deck.owner_id == user.id

        # Slide count matches the curriculum.
        slides = (
            await db.execute(select(Slide).where(Slide.deck_id == deck.id).order_by(Slide.position))
        ).scalars().all()
        assert len(slides) == len(TUTORIAL_SLIDES)
        assert [s.kicker for s in slides] == [t["kicker"] for t in TUTORIAL_SLIDES]

        # One Widget row per starter pack entry, all deck-local.
        widgets = (
            await db.execute(select(Widget).where(Widget.deck_id == deck.id))
        ).scalars().all()
        assert len(widgets) == len(STARTER_WIDGETS)
        kinds = {w.kind for w in widgets}
        assert kinds == {spec.kind for spec in STARTER_WIDGETS}
        assert all(w.current_revision_id for w in widgets)

        # Every placeholder in the SOURCE tutorial markdown should appear in
        # the persisted slide's markdown as `{{widget:<slug>-<8hex>}}` — the
        # editor's convention. The resulting placement_id is the widget kind
        # plus a per-seed random suffix.
        widget_by_kind = {w.kind: w for w in widgets}
        source_by_position = list(TUTORIAL_SLIDES)
        for slide in slides:
            source_md = source_by_position[slide.position]["markdown"]
            source_slugs = [m.group(1) for m in _WIDGET_PLACEHOLDER.finditer(source_md)]
            persisted_ids = [m.group(1) for m in _WIDGET_PLACEHOLDER.finditer(slide.markdown)]
            assert len(persisted_ids) == len(source_slugs), (
                f"slide {slide.position}: placeholder count drift "
                f"(source={source_slugs}, persisted={persisted_ids})"
            )
            for source_slug, placement_id in zip(source_slugs, persisted_ids, strict=True):
                # New shape: persisted token must be `<source_slug>-<8hex>`.
                assert placement_id.startswith(source_slug + "-"), (
                    f"persisted token {placement_id!r} does not start with source slug {source_slug!r}"
                )
                assert _PLACEMENT_ID_RE.match(placement_id), (
                    f"persisted placement_id {placement_id!r} does not match {_PLACEMENT_ID_RE.pattern}"
                )
                row = (
                    await db.execute(
                        select(SlideWidget).where(
                            SlideWidget.slide_id == slide.id,
                            SlideWidget.placement_id == placement_id,
                        )
                    )
                ).scalar_one_or_none()
                assert row is not None, (
                    f"missing placement {placement_id!r} on slide {slide.position}"
                )
                assert row.widget_id == widget_by_kind[source_slug].id
                assert row.revision_id == widget_by_kind[source_slug].current_revision_id
                revision = (
                    await db.execute(
                        select(WidgetRevision).where(WidgetRevision.id == row.revision_id)
                    )
                ).scalar_one()
                assert revision.widget_id == row.widget_id

        # Bonus: §06 split landed — find §06a and §06b and confirm each has
        # exactly one widget placement.
        slides_by_kicker = {s.kicker: s for s in slides}
        for kicker in ("§ 06a — Quiet", "§ 06b — Loud"):
            assert kicker in slides_by_kicker, f"missing slide {kicker!r}"
            slide = slides_by_kicker[kicker]
            placements = (
                await db.execute(
                    select(SlideWidget).where(SlideWidget.slide_id == slide.id)
                )
            ).scalars().all()
            assert len(placements) == 1, (
                f"{kicker} should have exactly 1 widget, got {len(placements)}"
            )

        # Manifest carries the version so future migrations can target it.
        assert deck.manifest.get("version") == TUTORIAL_VERSION


async def test_create_tutorial_for_is_idempotent(app_with_db):
    factory = get_session_factory()
    async with factory() as db:
        user = await _make_user(db, email="bob-onboarding@example.com")
        first = await create_tutorial_for(db, user)
        await db.commit()

        # Re-run — must return the same deck and not duplicate any rows.
        second = await create_tutorial_for(db, user)
        await db.commit()
        assert second.id == first.id

        decks_for_user = (
            await db.execute(
                select(Deck).where(Deck.workspace_id == user.workspace_id, Deck.owner_id == user.id)
            )
        ).scalars().all()
        # Only the tutorial. No accidental duplicate from re-running.
        assert len(decks_for_user) == 1

        widgets = (
            await db.execute(select(Widget).where(Widget.deck_id == first.id))
        ).scalars().all()
        assert len(widgets) == len(STARTER_WIDGETS)


def test_starter_widgets_pass_theme_layout_behavior_scanners():
    """Same contract scanners we hold the LLM to. A starter widget that
    violates any of them would tell instructors "the AI is broken" because
    its own examples don't follow the rules."""
    from slaides.llm.service import (
        _scan_behavior_violations,
        _scan_layout_violations,
        _scan_theme_violations,
    )

    failures: list[str] = []
    for spec in STARTER_WIDGETS:
        body = "\n".join([spec.html or "", spec.css or "", spec.js or ""])
        for label, violations in (
            ("theme", _scan_theme_violations(body)),
            ("layout", _scan_layout_violations(body)),
        ):
            if violations:
                failures.append(f"{spec.kind}/{label}: {violations}")
        # Behavior scanner runs over the full JSON-encoded draft.
        draft = json.dumps(
            {
                "name": spec.name,
                "kind": spec.kind,
                "html": spec.html,
                "js": spec.js,
                "css": spec.css,
                "behavior": spec.behavior,
                "props_schema": spec.props_schema,
            }
        )
        beh = _scan_behavior_violations(draft)
        if beh:
            failures.append(f"{spec.kind}/behavior: {beh}")
    assert not failures, "\n".join(failures)


def test_starter_widget_default_props_validate_against_own_schema():
    """Each widget's default values (mined from its props_schema's `default`
    fields) must validate cleanly. Catches schema-typo regressions early."""
    from slaides.widgets.props_validator import PropsValidationError, validate_props

    for spec in STARTER_WIDGETS:
        defaults: dict = {}
        props = (spec.props_schema or {}).get("properties") or {}
        for key, sub in props.items():
            if isinstance(sub, dict) and "default" in sub:
                defaults[key] = sub["default"]
        try:
            validate_props(defaults, spec.props_schema)
        except PropsValidationError as exc:
            pytest.fail(f"{spec.kind}: default props fail own schema — {exc}")


def test_suffix_placeholders_generates_8hex_suffix_per_unique_slug():
    """`_suffix_placeholders` rewrites every `{{widget:<slug>}}` token to
    `{{widget:<slug>-<8hex>}}` and returns the (slug, placement_id) pairs
    in source order. Duplicate slugs on the same slide share one id."""
    md = (
        "# heading\n\n"
        "{{widget:live-poll}}\n\n"
        "some text\n\n"
        "{{widget:quick-quiz}}\n\n"
        "{{widget:live-poll}}\n"  # duplicate — should reuse the first id
    )
    rewritten, pairs = _suffix_placeholders(md)
    assert len(pairs) == 2  # dedupes the duplicate slug
    seen_slugs = [s for s, _ in pairs]
    assert seen_slugs == ["live-poll", "quick-quiz"]
    for slug, pid in pairs:
        assert pid.startswith(slug + "-")
        assert _PLACEMENT_ID_RE.match(pid)
    # Every persisted token in the rewritten markdown matches one of the ids.
    persisted = [m.group(1) for m in _WIDGET_PLACEHOLDER.finditer(rewritten)]
    assert persisted.count(pairs[0][1]) == 2  # the duplicate slug now resolves to one id, but appears twice
    assert persisted.count(pairs[1][1]) == 1


def test_suffix_placeholders_returns_different_ids_per_call():
    """Each call mints a fresh random suffix — proves the v2 migration
    re-seeding does not produce identical IDs across deck re-creations."""
    md = "{{widget:live-poll}}"
    _, a = _suffix_placeholders(md)
    _, b = _suffix_placeholders(md)
    assert a[0][1] != b[0][1], "two calls should produce different suffixes"


async def test_create_tutorial_for_re_seed_produces_fresh_placement_ids(app_with_db):
    """If we delete the tutorial and re-seed (the migration's path), the new
    placement_ids differ from the old ones. Confirms the suffix is genuinely
    per-seed, not derived from a stable hash."""
    factory = get_session_factory()
    async with factory() as db:
        user = await _make_user(db, email="reseed@example.com")
        deck_v1 = await create_tutorial_for(db, user)
        await db.commit()
        v1_ids = {
            row.placement_id
            for row in (
                await db.execute(
                    select(SlideWidget)
                    .join(Slide, Slide.id == SlideWidget.slide_id)
                    .where(Slide.deck_id == deck_v1.id)
                )
            ).scalars()
        }
        await db.delete(deck_v1)
        await db.commit()

        deck_v2 = await create_tutorial_for(db, user)
        await db.commit()
        v2_ids = {
            row.placement_id
            for row in (
                await db.execute(
                    select(SlideWidget)
                    .join(Slide, Slide.id == SlideWidget.slide_id)
                    .where(Slide.deck_id == deck_v2.id)
                )
            ).scalars()
        }
        # Different deck row, completely different random suffixes.
        assert deck_v2.id != deck_v1.id
        assert v1_ids.isdisjoint(v2_ids), (
            f"re-seed should mint fresh placement_ids; overlap={v1_ids & v2_ids}"
        )


async def test_tutorial_reseed_migration_helper_rebuilds_v2_deck(app_with_db):
    """Smoke test for the 0014_tutorial_v2_reseed migration's `_seed_tutorial`
    helper. Exercises the raw-SQL re-seed path the migration uses, so the
    seeding logic is covered without driving alembic from the test."""
    import importlib.util
    import pathlib

    # Load the migration module by path (not on sys.path normally).
    mig_path = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0014_tutorial_v2_reseed.py"
    spec = importlib.util.spec_from_file_location("mig_0014", mig_path)
    assert spec and spec.loader
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    factory = get_session_factory()
    async with factory() as db:
        user = await _make_user(db, email="mig-smoke@example.com")
        await db.commit()

        # Run the migration's seeder against a sync bind via run_sync.
        from slaides.onboarding import content as tutorial_content

        def _run(sync_conn):
            mig._seed_tutorial(sync_conn, str(user.workspace_id), str(user.id), tutorial_content)

        async with factory() as db2:
            conn = await db2.connection()
            await conn.run_sync(_run)
            await db2.commit()

    # Verify the seeded deck has the v2 shape end-to-end.
    async with factory() as db:
        decks = (
            await db.execute(
                select(Deck).where(
                    Deck.workspace_id == user.workspace_id,
                    Deck.owner_id == user.id,
                )
            )
        ).scalars().all()
        assert len(decks) == 1
        deck = decks[0]
        assert deck.manifest.get("is_tutorial") is True
        assert deck.manifest.get("version") == TUTORIAL_VERSION

        slides = (
            await db.execute(
                select(Slide).where(Slide.deck_id == deck.id).order_by(Slide.position)
            )
        ).scalars().all()
        assert len(slides) == len(TUTORIAL_SLIDES)
        for slide in slides:
            for match in _WIDGET_PLACEHOLDER.finditer(slide.markdown):
                assert _PLACEMENT_ID_RE.match(match.group(1)), (
                    f"migration produced non-conforming placement_id {match.group(1)!r}"
                )
        placements = (
            await db.execute(
                select(SlideWidget)
                .join(Slide, Slide.id == SlideWidget.slide_id)
                .where(Slide.deck_id == deck.id)
            )
        ).scalars().all()
        for row in placements:
            assert _PLACEMENT_ID_RE.match(row.placement_id), (
                f"migration produced non-conforming placement_id {row.placement_id!r}"
            )


def test_tutorial_slide_placeholders_only_reference_starter_widgets():
    """If a slide says `{{widget:foo}}` and the pack doesn't ship `foo`,
    the placeholder silently goes nowhere — the slide renders a literal
    `{{widget:foo}}` string. Fail loudly at import time instead."""
    starter_slugs = {spec.kind for spec in STARTER_WIDGETS}
    for slide in TUTORIAL_SLIDES:
        for match in _WIDGET_PLACEHOLDER.finditer(slide["markdown"]):
            slug = match.group(1)
            assert slug in starter_slugs, (
                f"slide '{slide['kicker']}' references {{{{widget:{slug}}}}} but the "
                f"starter pack ships only {sorted(starter_slugs)}"
            )
