from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import GuestPrincipal, current_principal, current_user
from ..db.deps import db_session
from ..db.models import (
    AppUser,
    Deck,
    InteractionLog,
    PlacementState,
    Slide,
    SlideWidget,
    Widget,
    WidgetAiMessage,
    WidgetAiThread,
    WidgetRevision,
)
from ..db.models import Session as SessionRow
from ..db.models import SessionSlide
from . import package
from .props_validator import PropsValidationError, validate_props
from .schemas import (
    SlideWidgetCreate,
    SlideWidgetOut,
    SlideWidgetPatch,
    SlideWidgetRevisionOut,
    WidgetAiMessageCreate,
    WidgetAiMessageOut,
    WidgetAiThreadCreate,
    WidgetAiThreadOut,
    WidgetCopyRequest,
    WidgetCreate,
    WidgetOut,
    WidgetPatch,
    WidgetRevisionOut,
    WidgetSummary,
)

router = APIRouter(prefix="/widgets", tags=["widgets"])


def _summary(w: Widget) -> WidgetSummary:
    return WidgetSummary(
        id=w.id,
        deck_id=w.deck_id,
        derived_from_id=w.derived_from_id,
        name=w.name,
        kind=w.kind,
        description=w.description,
        tags=w.tags or [],
        version=w.version,
        behavior=w.behavior or {"kind": "quiet"},
    )


def _revision_out(revision: WidgetRevision | None) -> SlideWidgetRevisionOut | None:
    if revision is None:
        return None
    return SlideWidgetRevisionOut(
        id=revision.id,
        widget_id=revision.widget_id,
        version_number=revision.version_number,
        html=revision.html or "",
        js=revision.js,
        css=revision.css,
        props_schema=revision.props_schema or {},
        example_props=revision.example_props or {},
        behavior=revision.behavior or {"kind": "quiet"},
        ai_spec=revision.ai_spec or {},
        created_reason=revision.created_reason,
    )


def _full(w: Widget) -> WidgetOut:
    return WidgetOut(
        id=w.id,
        deck_id=w.deck_id,
        derived_from_id=w.derived_from_id,
        name=w.name,
        kind=w.kind,
        description=w.description,
        html=w.html or "",
        js=w.js,
        css=w.css,
        props_schema=w.props_schema or {},
        tags=w.tags or [],
        version=w.version,
        behavior=w.behavior or {"kind": "quiet"},
        current_revision_id=w.current_revision_id,
        example_props={},
        ai_spec={},
    )


async def _current_revision(session: AsyncSession, widget: Widget) -> WidgetRevision | None:
    if widget.current_revision_id is None:
        return None
    return (
        await session.execute(
            select(WidgetRevision).where(WidgetRevision.id == widget.current_revision_id)
        )
    ).scalar_one_or_none()


async def _next_revision_number(session: AsyncSession, widget_id: uuid.UUID) -> int:
    value = (
        await session.execute(
            select(func.max(WidgetRevision.version_number)).where(WidgetRevision.widget_id == widget_id)
        )
    ).scalar_one_or_none()
    return int(value or 0) + 1


async def _create_revision(
    session: AsyncSession,
    widget: Widget,
    *,
    html: str,
    js: str | None,
    css: str | None,
    props_schema: dict,
    example_props: dict,
    behavior: dict | None,
    ai_spec: dict,
    created_reason: str,
) -> WidgetRevision:
    rev = WidgetRevision(
        widget_id=widget.id,
        version_number=await _next_revision_number(session, widget.id),
        html=html or "",
        js=js,
        css=css,
        props_schema=props_schema or {},
        example_props=example_props or {},
        behavior=_normalise_behavior(behavior),
        ai_spec=ai_spec or {},
        created_reason=created_reason,
    )
    session.add(rev)
    await session.flush()
    widget.current_revision_id = rev.id
    # Dual-write during rollout so existing render/export paths keep reading
    # the flattened widget source until they are moved to explicit revisions.
    widget.html = rev.html
    widget.js = rev.js
    widget.css = rev.css
    widget.props_schema = rev.props_schema
    widget.behavior = rev.behavior
    await session.flush()
    return rev


async def _full_with_revision(session: AsyncSession, w: Widget) -> WidgetOut:
    rev = await _current_revision(session, w)
    if rev is None:
        return _full(w)
    return WidgetOut(
        id=w.id,
        deck_id=w.deck_id,
        derived_from_id=w.derived_from_id,
        name=w.name,
        kind=w.kind,
        description=w.description,
        html=rev.html or "",
        js=rev.js,
        css=rev.css,
        props_schema=rev.props_schema or {},
        tags=w.tags or [],
        version=w.version,
        behavior=rev.behavior or {"kind": "quiet"},
        current_revision_id=rev.id,
        example_props=rev.example_props or {},
        ai_spec=rev.ai_spec or {},
    )


async def _load_owned_deck(
    session: AsyncSession, user: AppUser, deck_id: uuid.UUID
) -> Deck:
    deck = (await session.execute(select(Deck).where(Deck.id == deck_id))).scalar_one_or_none()
    if deck is None or deck.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deck not found")
    return deck


async def _load_widget(session: AsyncSession, user: AppUser, widget_id: uuid.UUID) -> Widget:
    """Load a widget the caller's workspace owns, by joining through deck."""
    row = (
        await session.execute(
            select(Widget, Deck.workspace_id)
            .join(Deck, Deck.id == Widget.deck_id)
            .where(Widget.id == widget_id)
        )
    ).first()
    if row is None or row[1] != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    return row[0]


async def _open_placement_states_for_widget(
    session: AsyncSession, widget_id: uuid.UUID
) -> list[PlacementState]:
    rows = (
        await session.execute(
            select(PlacementState).where(
                PlacementState.widget_id == widget_id,
                PlacementState.closed_at.is_(None),
            )
        )
    ).scalars().all()
    return list(rows)


async def _open_placement_state_for_placement(
    session: AsyncSession, placement_id: str
) -> PlacementState | None:
    return (
        await session.execute(
            select(PlacementState).where(
                PlacementState.placement_id == placement_id,
                PlacementState.closed_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _reset_placement_states(
    session: AsyncSession, rows: list[PlacementState]
) -> None:
    """Delete the open placement_state rows and broadcast `widget.reset` to
    every affected session channel so audience iframes drop their cached
    projection. Raw `interaction_log` contributions are NOT touched — they
    remain in audit history."""
    # Import here to avoid a session ↔ widgets import cycle.
    from ..sessions.ws import broadcast_widget_reset

    notifications = [(row.session_id, row.placement_id) for row in rows]
    for row in rows:
        await session.delete(row)
    await session.flush()
    for session_id, placement_id in notifications:
        await broadcast_widget_reset(session_id, placement_id)


def _placement_in_use_conflict(rows: list[PlacementState]) -> HTTPException:
    sessions = sorted({str(r.session_id) for r in rows})
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "edit_requires_reset",
            "open_session_count": len(sessions),
            "open_placement_count": len(rows),
            "message": (
                f"This widget is aggregating contributions in "
                f"{len(sessions)} live session(s). Re-submit with "
                f"?reset_state=true to clear the audience tally and apply "
                f"the edit, or end the session first."
            ),
        },
    )


_LOUD_AGGREGATORS = {
    "tally",
    "latest_per_participant",
    "append",
    "set_union",
    "keyed_tally",
}


def _normalise_behavior(raw: dict | None) -> dict:
    if raw is None:
        return {"kind": "quiet"}
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="behavior must be an object",
        )
    kind = raw.get("kind")
    if kind == "quiet":
        return {"kind": "quiet"}
    if kind != "loud":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="behavior.kind must be quiet or loud",
        )
    aggregator = raw.get("aggregator")
    if aggregator not in _LOUD_AGGREGATORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="behavior.aggregator is required for loud widgets",
        )
    contribution_schema = raw.get("contribution_schema")
    if not isinstance(contribution_schema, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="behavior.contribution_schema is required for loud widgets",
        )
    return {
        "kind": "loud",
        "aggregator": aggregator,
        "contribution_schema": contribution_schema,
    }


@router.get("", response_model=list[WidgetSummary])
async def list_widgets(
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WidgetSummary]:
    """List every widget across the caller's workspace.

    Used by the cross-deck copy picker. The editor's right-sidebar library
    uses `GET /decks/{deck_id}/widgets` instead — that scope is narrower.
    """
    rows = await session.execute(
        select(Widget)
        .join(Deck, Deck.id == Widget.deck_id)
        .where(Deck.workspace_id == user.workspace_id)
        .order_by(Widget.name)
    )
    return [_summary(w) for w in rows.scalars()]


@router.post(
    "/from-interaction", response_model=WidgetOut, status_code=status.HTTP_201_CREATED
)
async def widget_from_interaction(
    body: dict,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    """Materialise a live poll / open-question into a reusable deck widget.

    Body: `{ session_slide_id: UUID }`. The widget lands in the session's deck
    (the same deck that hosted the live interaction). Only the session's owner
    can save it.
    """
    raw_id = body.get("session_slide_id")
    if not raw_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_slide_id required")
    try:
        session_slide_id = uuid.UUID(str(raw_id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid session_slide_id") from exc

    slide = (
        await session.execute(select(SessionSlide).where(SessionSlide.id == session_slide_id))
    ).scalar_one_or_none()
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction not found")
    sess_row = (
        await session.execute(select(SessionRow).where(SessionRow.id == slide.session_id))
    ).scalar_one_or_none()
    if (
        sess_row is None
        or sess_row.owner_id != user.id
        or sess_row.workspace_id != user.workspace_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction not found")

    from ..sessions.templates import build_widget_from_interaction

    try:
        widget_payload = build_widget_from_interaction(slide.kind, slide.spec or {})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    w = Widget(deck_id=sess_row.deck_id, behavior={"kind": "quiet"}, **widget_payload)
    session.add(w)
    await session.flush()
    await _create_revision(
        session,
        w,
        html=w.html or "",
        js=w.js,
        css=w.css,
        props_schema=w.props_schema or {},
        example_props={},
        behavior=w.behavior,
        ai_spec={},
        created_reason="migration_backfill",
    )
    await session.refresh(w)
    return await _full_with_revision(session, w)


async def _guest_can_read_widget(
    session: AsyncSession, principal: GuestPrincipal, widget: Widget
) -> bool:
    """A guest can fetch widget bodies for widgets actually used in their
    session — either as a deck-slide placement on the session's deck, or as a
    session_slide widget. Widgets v2 also requires `widget.deck_id` to match
    the session's deck (a widget from another deck shouldn't be visible even
    if a stray placement existed)."""
    row = (
        await session.execute(select(SessionRow).where(SessionRow.id == principal.session_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    # 1) Widget is in this session's deck and placed on a slide of it.
    if widget.deck_id == row.deck_id:
        placement = (
            await session.execute(
                select(SlideWidget.widget_id)
                .join(Slide, Slide.id == SlideWidget.slide_id)
                .where(SlideWidget.widget_id == widget.id, Slide.deck_id == row.deck_id)
                .limit(1)
            )
        ).first()
        if placement is not None:
            return True
    # 2) Widget is referenced by a session_slide in this session (e.g. saved
    #    interaction widget materialised mid-session).
    in_session = (
        await session.execute(
            select(SessionSlide.id)
            .where(SessionSlide.session_id == row.id, SessionSlide.widget_id == widget.id)
            .limit(1)
        )
    ).first()
    return in_session is not None


@router.get("/{widget_id}", response_model=WidgetOut)
async def get_widget(
    widget_id: uuid.UUID,
    principal: AppUser | GuestPrincipal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    widget = (
        await session.execute(select(Widget).where(Widget.id == widget_id))
    ).scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    if isinstance(principal, AppUser):
        deck = (await session.execute(select(Deck).where(Deck.id == widget.deck_id))).scalar_one_or_none()
        if deck is None or deck.workspace_id != principal.workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    else:  # GuestPrincipal
        if not await _guest_can_read_widget(session, principal, widget):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget not found")
    return await _full_with_revision(session, widget)


@router.patch("/{widget_id}", response_model=WidgetOut)
async def patch_widget(
    widget_id: uuid.UUID,
    body: WidgetPatch,
    reset_state: bool = False,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    w = await _load_widget(session, user, widget_id)

    # Per WIDGETS_V2.md decision log, editing a widget mid-session resets
    # the audience-visible projection. Refuse with 409 until the caller
    # confirms by re-submitting with ?reset_state=true, then drop the
    # affected placement_state rows and broadcast widget.reset.
    open_rows = await _open_placement_states_for_widget(session, w.id)
    if open_rows:
        if not reset_state:
            raise _placement_in_use_conflict(open_rows)
        await _reset_placement_states(session, open_rows)

    for field in ("name", "kind", "description", "tags"):
        v = getattr(body, field)
        if v is not None:
            setattr(w, field, v)
    revision_fields = {"html", "js", "css", "props_schema", "example_props", "behavior", "ai_spec"}
    if revision_fields.intersection(body.model_fields_set):
        current = await _current_revision(session, w)
        base = {
            "html": current.html if current else (w.html or ""),
            "js": current.js if current else w.js,
            "css": current.css if current else w.css,
            "props_schema": current.props_schema if current else (w.props_schema or {}),
            "example_props": current.example_props if current else {},
            "behavior": current.behavior if current else (w.behavior or {"kind": "quiet"}),
            "ai_spec": current.ai_spec if current else {},
        }
        for key in revision_fields:
            if key in body.model_fields_set:
                value = getattr(body, key)
                if value is not None:
                    base[key] = value
        await _create_revision(session, w, created_reason="patch", **base)
    await session.flush()
    await session.refresh(w)
    return await _full_with_revision(session, w)


@router.get("/{widget_id}/revisions", response_model=list[WidgetRevisionOut])
async def list_widget_revisions(
    widget_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WidgetRevisionOut]:
    widget = await _load_widget(session, user, widget_id)
    rows = (
        await session.execute(
            select(WidgetRevision)
            .where(WidgetRevision.widget_id == widget.id)
            .order_by(WidgetRevision.version_number)
        )
    ).scalars().all()
    return [WidgetRevisionOut.model_validate(row) for row in rows]


@router.post("/{widget_id}/revisions/{revision_id}/rollback", response_model=WidgetOut)
async def rollback_widget_revision(
    widget_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    widget = await _load_widget(session, user, widget_id)
    source = (
        await session.execute(
            select(WidgetRevision).where(
                WidgetRevision.id == revision_id,
                WidgetRevision.widget_id == widget.id,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")
    await _create_revision(
        session,
        widget,
        html=source.html,
        js=source.js,
        css=source.css,
        props_schema=source.props_schema or {},
        example_props=source.example_props or {},
        behavior=source.behavior or {"kind": "quiet"},
        ai_spec=source.ai_spec or {},
        created_reason="rollback",
    )
    await session.flush()
    await session.refresh(widget)
    return await _full_with_revision(session, widget)


@router.post(
    "/{widget_id}/ai-thread",
    response_model=WidgetAiThreadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_thread(
    widget_id: uuid.UUID,
    body: WidgetAiThreadCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiThreadOut:
    widget = await _load_widget(session, user, widget_id)
    thread = WidgetAiThread(
        widget_id=widget.id,
        title=body.title,
        compact_summary=body.compact_summary or {},
    )
    session.add(thread)
    await session.flush()
    await session.refresh(thread)
    return WidgetAiThreadOut(
        id=thread.id,
        widget_id=thread.widget_id,
        title=thread.title,
        compact_summary=thread.compact_summary or {},
        messages=[],
    )


@router.get("/{widget_id}/ai-thread", response_model=WidgetAiThreadOut | None)
async def get_ai_thread(
    widget_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiThreadOut | None:
    widget = await _load_widget(session, user, widget_id)
    thread = (
        await session.execute(
            select(WidgetAiThread)
            .where(WidgetAiThread.widget_id == widget.id)
            .order_by(WidgetAiThread.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if thread is None:
        return None
    rows = (
        await session.execute(
            select(WidgetAiMessage)
            .where(WidgetAiMessage.thread_id == thread.id)
            .order_by(WidgetAiMessage.created_at)
        )
    ).scalars().all()
    return WidgetAiThreadOut(
        id=thread.id,
        widget_id=thread.widget_id,
        title=thread.title,
        compact_summary=thread.compact_summary or {},
        messages=[WidgetAiMessageOut.model_validate(row) for row in rows],
    )


@router.post(
    "/{widget_id}/ai-thread/{thread_id}/messages",
    response_model=WidgetAiMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def append_ai_message(
    widget_id: uuid.UUID,
    thread_id: uuid.UUID,
    body: WidgetAiMessageCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiMessageOut:
    widget = await _load_widget(session, user, widget_id)
    thread = (
        await session.execute(
            select(WidgetAiThread).where(
                WidgetAiThread.id == thread_id,
                WidgetAiThread.widget_id == widget.id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI thread not found")
    if body.revision_id is not None:
        revision = (
            await session.execute(
                select(WidgetRevision).where(
                    WidgetRevision.id == body.revision_id,
                    WidgetRevision.widget_id == widget.id,
                )
            )
        ).scalar_one_or_none()
        if revision is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")
    msg = WidgetAiMessage(
        thread_id=thread.id,
        role=body.role,
        message_type=body.message_type,
        content=body.content or {},
        revision_id=body.revision_id,
    )
    session.add(msg)
    thread.updated_at = func.now()
    await session.flush()
    await session.refresh(msg)
    return WidgetAiMessageOut.model_validate(msg)


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(
    widget_id: uuid.UUID,
    force: bool = False,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Permanently delete a widget from the deck library.

    Without `?force=true`, returns 409 if the widget is currently attached to
    any slide so the caller can show a confirmation prompt. With `force=true`,
    detaches the widget from every slide (stripping the `{{widget:id}}` line
    from each slide's markdown), nulls out historical session_slide /
    interaction_log references, and deletes the widget row.
    """
    w = await _load_widget(session, user, widget_id)

    placements_rows = (
        await session.execute(select(SlideWidget).where(SlideWidget.widget_id == w.id))
    ).scalars().all()

    if placements_rows and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "widget_in_use",
                "usage_count": len(placements_rows),
                "message": (
                    f"Widget is still placed on {len(placements_rows)} slide(s). "
                    "Pass ?force=true to detach and delete."
                ),
            },
        )

    # Detach: strip placeholder from every affected slide's markdown.
    if placements_rows:
        affected_slide_ids = {row.slide_id for row in placements_rows}
        placeholders_by_slide: dict[uuid.UUID, set[str]] = {}
        for row in placements_rows:
            placeholders_by_slide.setdefault(row.slide_id, set()).add(
                f"{{{{widget:{row.placement_id}}}}}"
            )
        slides = (
            await session.execute(select(Slide).where(Slide.id.in_(affected_slide_ids)))
        ).scalars().all()
        for slide in slides:
            placeholders = placeholders_by_slide.get(slide.id, set())
            if slide.markdown and placeholders:
                slide.markdown = "\n".join(
                    ln for ln in slide.markdown.split("\n") if ln.strip() not in placeholders
                )
        # Remove placements.
        for row in placements_rows:
            await session.delete(row)

    # Null out historical session_slide and interaction_log references so the
    # widget row can be deleted without violating FK constraints. We keep the
    # log rows themselves — they're audit data scoped to a (now-ended) session.
    await session.execute(
        update(SessionSlide).where(SessionSlide.widget_id == w.id).values(widget_id=None)
    )
    await session.execute(
        update(InteractionLog).where(InteractionLog.widget_id == w.id).values(widget_id=None)
    )

    # Drop AI threads + their messages up front. `widget_ai_thread.widget_id`
    # already cascades on widget delete, but Postgres runs the
    # `widget_revision`-side cascade first, and `widget_ai_message.revision_id`
    # → `widget_revision.id` (NO ACTION) trips before the thread cascade can
    # clear the messages. Wiping the threads here cascades to messages and
    # leaves no revision_id references behind. (SQLite tests miss this because
    # the FK is soft there — see migration 0015's note on the constraint.)
    await session.execute(
        delete(WidgetAiThread).where(WidgetAiThread.widget_id == w.id)
    )

    await session.delete(w)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{widget_id}/export")
async def export_widget(
    widget_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    w = await _load_widget(session, user, widget_id)
    revision = await _current_revision(session, w)
    body = package.pack(
        package.WidgetFile(
            name=w.name,
            kind=w.kind,
            description=w.description,
            html=(revision.html if revision else w.html) or "",
            js=revision.js if revision else w.js,
            css=revision.css if revision else w.css,
            props_schema=(revision.props_schema if revision else w.props_schema) or {},
            example_props=(revision.example_props if revision else {}) or {},
            behavior=(revision.behavior if revision else w.behavior) or {"kind": "quiet"},
            ai_spec=(revision.ai_spec if revision else {}) or {},
            tags=list(w.tags or []),
            version=w.version,
        )
    )
    safe_name = (w.name or "widget").replace("/", "-")
    return Response(
        content=body,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.swidget"'},
    )


# ---------- deck-scoped widget endpoints ----------

deck_widget_router = APIRouter(tags=["widgets"])


@deck_widget_router.get(
    "/decks/{deck_id}/widgets", response_model=list[WidgetSummary]
)
async def list_deck_widgets(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WidgetSummary]:
    """Widgets v2 — list the widgets owned by this deck. Used by the editor's
    right-sidebar library."""
    await _load_owned_deck(session, user, deck_id)
    rows = await session.execute(
        select(Widget).where(Widget.deck_id == deck_id).order_by(Widget.name)
    )
    return [_summary(w) for w in rows.scalars()]


@deck_widget_router.post(
    "/decks/{deck_id}/widgets",
    response_model=WidgetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_deck_widget(
    deck_id: uuid.UUID,
    body: WidgetCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    """Widgets v2 — create a widget owned by this deck."""
    deck = await _load_owned_deck(session, user, deck_id)
    w = Widget(
        deck_id=deck.id,
        name=body.name,
        kind=body.kind,
        description=body.description,
        html="",
        js=None,
        css=None,
        props_schema={},
        tags=body.tags or [],
        behavior={"kind": "quiet"},
    )
    session.add(w)
    await session.flush()
    await _create_revision(
        session,
        w,
        html=body.html or "",
        js=body.js,
        css=body.css,
        props_schema=body.props_schema or {},
        example_props=body.example_props or {},
        behavior=body.behavior,
        ai_spec=body.ai_spec or {},
        created_reason="create",
    )
    await session.refresh(w)
    return await _full_with_revision(session, w)


@deck_widget_router.post(
    "/decks/{deck_id}/widgets/copy",
    response_model=WidgetOut,
    status_code=status.HTTP_201_CREATED,
)
async def copy_widget_from_deck(
    deck_id: uuid.UUID,
    body: WidgetCopyRequest,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    """Widgets v2 — clone a widget into this deck.

    The new widget is independent; `derived_from_id` carries an informational
    pointer at the source. Source edits never propagate. Same-deck copies are
    allowed so the user can create variants (e.g. duplicate a poll, then
    edit the clone into a multiple-choice quiz) — in that case the clone's
    name gets a `" (copy)"` suffix so the library doesn't surface two
    identically-titled cards.
    """
    target_deck = await _load_owned_deck(session, user, deck_id)
    source = await _load_widget(session, user, body.source_widget_id)
    clone_name = (
        await _unique_widget_name_in_deck(session, target_deck.id, source.name)
        if source.deck_id == target_deck.id
        else source.name
    )
    clone = Widget(
        deck_id=target_deck.id,
        derived_from_id=source.id,
        name=clone_name,
        kind=source.kind,
        description=source.description,
        html="",
        js=None,
        css=None,
        props_schema={},
        tags=list(source.tags or []),
        version=source.version,
        behavior={"kind": "quiet"},
    )
    session.add(clone)
    await session.flush()
    source_revision = await _current_revision(session, source)
    await _create_revision(
        session,
        clone,
        html=(source_revision.html if source_revision else source.html) or "",
        js=source_revision.js if source_revision else source.js,
        css=source_revision.css if source_revision else source.css,
        props_schema=(source_revision.props_schema if source_revision else source.props_schema) or {},
        example_props=(source_revision.example_props if source_revision else {}) or {},
        behavior=(source_revision.behavior if source_revision else source.behavior) or {"kind": "quiet"},
        ai_spec=(source_revision.ai_spec if source_revision else {}) or {},
        created_reason="copy",
    )
    await session.refresh(clone)
    return await _full_with_revision(session, clone)


async def _unique_widget_name_in_deck(
    session: AsyncSession, deck_id: uuid.UUID, base: str
) -> str:
    """If `base` collides with an existing widget name in the deck, return
    `<base> (copy)`, `<base> (copy 2)`, … until free. Probes against a
    single in-memory set so we don't issue N round-trips for a deck with
    several existing clones."""
    rows = await session.execute(
        select(Widget.name).where(Widget.deck_id == deck_id)
    )
    taken = {row for row in rows.scalars()}
    if base not in taken:
        return base
    candidate = f"{base} (copy)"
    if candidate not in taken:
        return candidate
    n = 2
    while True:
        candidate = f"{base} (copy {n})"
        if candidate not in taken:
            return candidate
        n += 1


@deck_widget_router.post(
    "/decks/{deck_id}/widgets/import",
    response_model=WidgetOut,
    status_code=status.HTTP_201_CREATED,
)
async def import_widget_into_deck(
    deck_id: uuid.UUID,
    file: UploadFile = File(...),
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    """Widgets v2 — import a `.swidget` package into this deck."""
    deck = await _load_owned_deck(session, user, deck_id)
    data = await file.read()
    try:
        wf = package.unpack(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid .swidget: {exc}") from exc
    w = Widget(
        deck_id=deck.id,
        name=wf.name,
        kind=wf.kind,
        description=wf.description,
        html="",
        js=None,
        css=None,
        props_schema={},
        tags=wf.tags,
        version=wf.version,
        behavior={"kind": "quiet"},
    )
    session.add(w)
    await session.flush()
    await _create_revision(
        session,
        w,
        html=wf.html,
        js=wf.js,
        css=wf.css,
        props_schema=wf.props_schema,
        example_props=wf.example_props,
        behavior=wf.behavior,
        ai_spec=wf.ai_spec,
        created_reason="import",
    )
    await session.refresh(w)
    return await _full_with_revision(session, w)


# Kept for symmetry with the old `/widgets/import` route; new clients use the
# deck-scoped variant above. We retain `import_router` so `main.py` doesn't need
# to change its `app.include_router` lines.
import_router = APIRouter(prefix="/widgets", tags=["widgets"])


# ---------- slide-attach endpoints (mounted under /decks/{deck_id}/slides/{slide_id}) ----------

slide_router = APIRouter(tags=["widgets"])


async def _load_slide(session: AsyncSession, user: AppUser, deck_id: uuid.UUID, slide_id: uuid.UUID) -> Slide:
    slide = (
        await session.execute(select(Slide).where(Slide.id == slide_id, Slide.deck_id == deck_id))
    ).scalar_one_or_none()
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    deck = (await session.execute(select(Deck).where(Deck.id == deck_id))).scalar_one()
    if deck.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    return slide


@slide_router.post(
    "/decks/{deck_id}/slides/{slide_id}/widgets",
    response_model=SlideWidgetOut,
    status_code=status.HTTP_201_CREATED,
)
async def attach_widget(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    body: SlideWidgetCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SlideWidgetOut:
    slide = await _load_slide(session, user, deck_id, slide_id)
    # Hard rule: one widget per slide. (SPEC §3.3.1, FR-031.)
    existing = (
        await session.execute(select(SlideWidget).where(SlideWidget.slide_id == slide.id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="slide already has a widget (1 max per slide)"
        )
    widget = await _load_widget(session, user, body.widget_id)
    # Widgets v2 — same-deck constraint: a widget can only be attached to a
    # slide in its own deck. Users who want to reuse a widget across decks
    # must copy it first via `POST /decks/{deck_id}/widgets/copy`.
    if widget.deck_id != deck_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "cross_deck_attach",
                "message": (
                    "widget belongs to a different deck — copy it into this "
                    "deck first via POST /decks/{deck_id}/widgets/copy"
                ),
            },
        )
    incoming_props = body.props or {}
    revision = await _current_revision(session, widget)
    if not incoming_props:
        incoming_props = dict((revision.example_props if revision else {}) or {})
    try:
        validated_props = validate_props(incoming_props, widget.props_schema or {})
    except PropsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    link = SlideWidget(
        slide_id=slide.id,
        placement_id=body.placement_id,
        widget_id=widget.id,
        revision_id=widget.current_revision_id,
        props=validated_props,
        position=0,
    )
    session.add(link)
    # Ensure the slide markdown contains the placeholder, append if absent.
    placeholder = f"{{{{widget:{body.placement_id}}}}}"
    if placeholder not in (slide.markdown or ""):
        sep = "\n\n" if slide.markdown and not slide.markdown.endswith("\n") else "\n"
        slide.markdown = (slide.markdown or "") + sep + placeholder + "\n"
    await session.flush()
    return SlideWidgetOut(
        placement_id=link.placement_id,
        widget_id=widget.id,
        revision_id=link.revision_id,
        revision=_revision_out(revision),
        kind=widget.kind,
        name=widget.name,
        props=link.props or {},
        position=link.position,
    )


@slide_router.patch(
    "/decks/{deck_id}/slides/{slide_id}/widgets/{placement_id}",
    response_model=SlideWidgetOut,
)
async def patch_placement_props(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    placement_id: str,
    body: SlideWidgetPatch,
    reset_state: bool = False,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SlideWidgetOut:
    """Update a widget placement's per-instance props.

    Validated against the linked widget's `props_schema` — type mismatches,
    out-of-enum values, length/range violations, etc. return 422.

    Mid-session prop edits reset the audience-visible tally: returns 409 with
    `error=edit_requires_reset` unless ?reset_state=true is set, in which case
    the open placement_state row for this placement is dropped and a
    `widget.reset` broadcast lands on the session channel.
    """
    slide = await _load_slide(session, user, deck_id, slide_id)
    link = (
        await session.execute(
            select(SlideWidget).where(
                SlideWidget.slide_id == slide.id,
                SlideWidget.placement_id == placement_id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget placement not found")
    widget = await _load_widget(session, user, link.widget_id)
    revision = await _current_revision(session, widget)
    if link.revision_id is not None:
        revision = (
            await session.execute(
                select(WidgetRevision).where(
                    WidgetRevision.id == link.revision_id,
                    WidgetRevision.widget_id == widget.id,
                )
            )
        ).scalar_one_or_none()

    open_row = await _open_placement_state_for_placement(session, placement_id)
    if open_row is not None:
        if not reset_state:
            raise _placement_in_use_conflict([open_row])
        await _reset_placement_states(session, [open_row])

    try:
        validated = validate_props(body.props, widget.props_schema or {})
    except PropsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    link.props = validated
    await session.flush()
    return SlideWidgetOut(
        placement_id=link.placement_id,
        widget_id=widget.id,
        revision_id=link.revision_id,
        revision=_revision_out(revision),
        kind=widget.kind,
        name=widget.name,
        props=link.props or {},
        position=link.position,
    )


@slide_router.delete(
    "/decks/{deck_id}/slides/{slide_id}/widgets/{placement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_widget(
    deck_id: uuid.UUID,
    slide_id: uuid.UUID,
    placement_id: str,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    slide = await _load_slide(session, user, deck_id, slide_id)
    link = (
        await session.execute(
            select(SlideWidget).where(
                SlideWidget.slide_id == slide.id, SlideWidget.placement_id == placement_id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="widget placement not found")
    widget_id = link.widget_id
    await session.delete(link)
    await session.flush()
    # Also strip the placeholder line from markdown.
    placeholder = f"{{{{widget:{placement_id}}}}}"
    if slide.markdown:
        new_md = "\n".join(
            ln for ln in slide.markdown.split("\n") if ln.strip() != placeholder
        )
        slide.markdown = new_md

    # GC drop-spawned copies. A widget created by the drag-drop / cross-deck
    # copy flow carries a `derived_from_id` pointer. If detaching this
    # placement leaves the widget unreferenced, drop the widget row too so
    # the deck library doesn't accumulate orphan copies. Hand-authored
    # widgets (no `derived_from_id`) are left alone — users own those
    # explicitly via the library.
    widget = (
        await session.execute(select(Widget).where(Widget.id == widget_id))
    ).scalar_one_or_none()
    if widget is not None and widget.derived_from_id is not None:
        remaining = (
            await session.execute(
                select(SlideWidget.placement_id).where(SlideWidget.widget_id == widget_id).limit(1)
            )
        ).scalar_one_or_none()
        if remaining is None:
            # Mirror delete_widget: null out historical session/interaction
            # references so the row can be removed without FK violation.
            await session.execute(
                update(SessionSlide).where(SessionSlide.widget_id == widget.id).values(widget_id=None)
            )
            await session.execute(
                update(InteractionLog).where(InteractionLog.widget_id == widget.id).values(widget_id=None)
            )
            await session.delete(widget)

    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
