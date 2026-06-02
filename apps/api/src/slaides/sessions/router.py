from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import GuestPrincipal, current_guest, current_user
from ..auth.service import issue_guest
from ..db.deps import db_session
from ..db.models import AppUser, Deck, InteractionLog, LlmCall, Participant, Slide
from ..db.models import Session as SessionRow
from ..decks import service as deck_service
from ..decks.schemas import SectionOut, SlideOut, SlideWidgetEmbed
from . import service
from . import placement_state_service
from .schemas import (
    InteractionPatch,
    OpenAnswerOut,
    OpenInteractionRequest,
    ParticipantOut,
    PlacementStateOut,
    PollSpec,
    PreviewFakeGuest,
    PreviewSessionRequest,
    PreviewSessionResponse,
    QuestionOut,
    QuestionSpec,
    RandomAudienceSpec,
    SessionAdvance,
    SessionCreate,
    SessionListItem,
    SessionPublic,
    SessionSlideOut,
    SessionSnapshot,
)

# Display names the preview harness hands out to fake guests. Five covers the
# audience_count cap; the extra names are harmless if the cap changes later.
_PREVIEW_DISPLAY_NAMES = (
    "Alice", "Bob", "Carol", "Dave", "Erin", "Frank",
    "Grace", "Heidi", "Ivan", "Judy", "Mallory", "Niaj",
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _load_owned(session: AsyncSession, user: AppUser, session_id: uuid.UUID) -> SessionRow:
    row = (
        await session.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one_or_none()
    if row is None or row.workspace_id != user.workspace_id or row.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return row


async def _active_session_for_owner(
    session: AsyncSession,
    user: AppUser,
    *,
    is_preview: bool,
) -> SessionRow | None:
    return (
        await session.execute(
            select(SessionRow)
            .where(
                SessionRow.workspace_id == user.workspace_id,
                SessionRow.owner_id == user.id,
                SessionRow.ended_at.is_(None),
                SessionRow.is_preview.is_(is_preview),
            )
            .order_by(SessionRow.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _snapshot(
    session: AsyncSession, row: SessionRow, *, viewer: str = "host"
) -> SessionSnapshot:
    deck = (await session.execute(select(Deck).where(Deck.id == row.deck_id))).scalar_one()
    slides = await deck_service.list_slides(session, deck.id)
    sections = await deck_service.list_sections(session, deck.id)
    placements = await deck_service.load_widget_placements(session, [s.id for s in slides])
    slide_outs: list[SlideOut] = []
    for s in slides:
        out = SlideOut.model_validate(s)
        out.widgets = [SlideWidgetEmbed(**p) for p in placements.get(s.id, [])]
        slide_outs.append(out)
    session_slides = await service.list_session_slides(session, row.id)
    questions = await service.list_questions(session, row.id)
    participants = await service.list_participants(session, row.id)
    placement_states = await placement_state_service.list_session_placement_states(session, row.id)
    if viewer == "audience":
        # `collect` widgets are presenter-only: their entries hold every
        # audience member's answer, so they must never appear in the audience
        # snapshot. Each audience member renders only its own answer locally.
        placement_states = [p for p in placement_states if p.aggregator != "collect"]
    return SessionSnapshot(
        id=row.id,
        code=row.code,
        deck_id=deck.id,
        deck_title=deck.title,
        owner_id=row.owner_id,
        started_at=row.started_at,
        ended_at=row.ended_at,
        current_slide_id=row.current_slide_id,
        sections=[SectionOut.model_validate(s) for s in sections],
        slides=slide_outs,
        session_slides=[SessionSlideOut.model_validate(s) for s in session_slides],
        questions=[QuestionOut.model_validate(q) for q in questions],
        audience_count=len(participants),
        placement_states=[
            PlacementStateOut(**placement_state_service.project_for_snapshot(p))
            for p in placement_states
        ],
    )


def _participant_count_subq():
    return (
        select(func.count(Participant.id))
        .where(Participant.session_id == SessionRow.id)
        .correlate(SessionRow)
        .scalar_subquery()
    )


def _interaction_count_subq():
    return (
        select(func.count(InteractionLog.id))
        .where(InteractionLog.session_id == SessionRow.id)
        .correlate(SessionRow)
        .scalar_subquery()
    )


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SessionListItem]:
    rows = await session.execute(
        select(
            SessionRow,
            Deck.title.label("deck_title"),
            _participant_count_subq().label("participant_count"),
            _interaction_count_subq().label("interaction_count"),
        )
        .join(Deck, Deck.id == SessionRow.deck_id)
        .where(
            SessionRow.workspace_id == user.workspace_id,
            SessionRow.owner_id == user.id,
            # Preview-tab sessions are ephemeral; they shouldn't show in the
            # instructor's session history.
            SessionRow.is_preview.is_(False),
        )
        .order_by(SessionRow.started_at.desc())
    )
    return [
        SessionListItem(
            id=row.Session.id,
            deck_id=row.Session.deck_id,
            code=row.Session.code,
            started_at=row.Session.started_at,
            ended_at=row.Session.ended_at,
            deck_title=row.deck_title or "",
            participant_count=row.participant_count or 0,
            interaction_count=row.interaction_count or 0,
        )
        for row in rows.all()
    ]


@router.get("/active", response_model=SessionListItem | None)
async def get_active_session_for_deck(
    deck_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionListItem | None:
    row = (
        await session.execute(
            select(SessionRow)
            .where(
                SessionRow.workspace_id == user.workspace_id,
                SessionRow.owner_id == user.id,
                SessionRow.deck_id == deck_id,
                SessionRow.ended_at.is_(None),
                # Preview-tab sessions are ephemeral and live behind their own
                # endpoint; the editor's Start/Resume button must never offer
                # to resume into one (it would put the instructor's live
                # audience into a deck-test sandbox).
                SessionRow.is_preview.is_(False),
            )
            .order_by(SessionRow.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return SessionListItem.model_validate(row)


@router.post("", response_model=SessionSnapshot, status_code=status.HTTP_201_CREATED)
async def create_session_endpoint(
    body: SessionCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSnapshot:
    deck = (await session.execute(select(Deck).where(Deck.id == body.deck_id))).scalar_one_or_none()
    if deck is None or deck.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deck not found")
    if await _active_session_for_owner(session, user, is_preview=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="end active live session before starting a new one",
        )
    row = await service.create_session(session, deck, user.id)
    return await _snapshot(session, row)


@router.get("/by-code/{code}", response_model=SessionPublic)
async def get_by_code(
    code: str,
    session: AsyncSession = Depends(db_session),
) -> SessionPublic:
    row = (
        await session.execute(select(SessionRow).where(SessionRow.code == code.upper()))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    deck = (await session.execute(select(Deck).where(Deck.id == row.deck_id))).scalar_one()
    return SessionPublic(
        id=row.id,
        code=row.code,
        deck_title=deck.title,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


@router.get("/{session_id}/audience", response_model=SessionSnapshot)
async def get_audience_snapshot(
    session_id: uuid.UUID,
    principal: GuestPrincipal = Depends(current_guest),
    session: AsyncSession = Depends(db_session),
) -> SessionSnapshot:
    if principal.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    row = (
        await session.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return await _snapshot(session, row, viewer="audience")


@router.get("/{session_id}", response_model=SessionSnapshot)
async def get_session(
    session_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSnapshot:
    row = await _load_owned(session, user, session_id)
    return await _snapshot(session, row)


@router.post("/{session_id}/end", response_model=SessionSnapshot)
async def end_session_endpoint(
    session_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSnapshot:
    row = await _load_owned(session, user, session_id)
    await service.end_session(session, row)
    snapshot = await _snapshot(session, row)
    from .ws import broadcast_session_ended

    await broadcast_session_ended(row.id)
    return snapshot


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_session_endpoint(
    session_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Permanently delete a session and all its data.

    Cascades remove participants, interactions, questions, session_event,
    session_slide and placement_state. LlmCall.session_id is NULL-ed out
    so billing/audit records survive without dangling FKs.
    """
    row = await _load_owned(session, user, session_id)
    if row.ended_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="end the session before deleting it",
        )
    await session.execute(
        update(LlmCall).where(LlmCall.session_id == session_id).values(session_id=None)
    )
    await session.execute(delete(SessionRow).where(SessionRow.id == session_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/advance", response_model=SessionSnapshot)
async def advance_endpoint(
    session_id: uuid.UUID,
    body: SessionAdvance,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSnapshot:
    row = await _load_owned(session, user, session_id)
    if row.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="session ended")
    if not body.is_session_slide:
        slide = (
            await session.execute(select(Slide).where(Slide.id == body.slide_id, Slide.deck_id == row.deck_id))
        ).scalar_one_or_none()
        if slide is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slide not found")
    await service.advance_slide(session, row, body.slide_id)
    snapshot = await _snapshot(session, row)
    # Best-effort fanout via WS hub; failure shouldn't break the REST response.
    from .ws import broadcast_slide_changed

    await broadcast_slide_changed(row.id, body.slide_id, body.is_session_slide)
    return snapshot


@router.post(
    "/preview",
    response_model=PreviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_preview_session_endpoint(
    body: PreviewSessionRequest,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> PreviewSessionResponse:
    """Spin up a preview session + N pre-authenticated fake guests.

    Preview sessions are real server resources. Keep one active preview per
    instructor so a stuck tab cannot multiply participants and websockets
    across repeated preview starts.
    """

    deck = (
        await session.execute(select(Deck).where(Deck.id == body.deck_id))
    ).scalar_one_or_none()
    if deck is None or deck.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deck not found")
    if await _active_session_for_owner(session, user, is_preview=True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="end active preview session before starting a new one",
        )

    row = await service.create_session(session, deck, user.id)
    row.is_preview = True
    await session.flush()
    await session.refresh(row)

    # Mint N fake guests. Each gets a stable display name from the rotating
    # list and a participant_ref derived from the session salt — identical to
    # the real /auth/guest path, so the WS handler treats them as ordinary
    # guests with no special casing.
    fake_guests: list[PreviewFakeGuest] = []
    for i in range(body.audience_count):
        display_name = _PREVIEW_DISPLAY_NAMES[i % len(_PREVIEW_DISPLAY_NAMES)]
        # Salt the ref with a per-guest nonce so two preview runs don't
        # collide on the unique (session_id, ref) constraint even if we
        # ever leave a prior preview row around.
        nonce = secrets.token_hex(4)
        ref = hashlib.sha256(f"preview-{i}-{nonce}-{row.salt}".encode("utf-8")).hexdigest()
        participant = Participant(
            session_id=row.id,
            email=None,
            display_name=display_name,
            anon=False,
            ref=ref,
        )
        session.add(participant)
        await session.flush()
        token = issue_guest(participant.id, row.id, ref)
        fake_guests.append(
            PreviewFakeGuest(
                participant_id=participant.id,
                participant_ref=ref,
                display_name=display_name,
                token=token,
            )
        )

    return PreviewSessionResponse(
        session_id=row.id,
        code=row.code,
        fake_guests=fake_guests,
    )


def _validate_interaction_spec(kind: str, spec: dict) -> dict:
    """Validate spec by kind and return the normalized dict for storage.

    For the dedicated live types ('poll', 'question') we enforce shape with
    Pydantic. The legacy 'widget' kind is left freeform.
    """
    if kind == "poll":
        return PollSpec(**{**spec, "type": "poll"}).model_dump()
    if kind == "question":
        return QuestionSpec(**{**spec, "type": "question"}).model_dump()
    if kind == "random":
        return RandomAudienceSpec(**{**spec, "type": "random"}).model_dump()
    return spec


@router.post(
    "/{session_id}/interactions",
    response_model=SessionSlideOut,
    status_code=status.HTTP_201_CREATED,
)
async def open_interaction(
    session_id: uuid.UUID,
    body: OpenInteractionRequest,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    row = await _load_owned(session, user, session_id)
    if row.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="session ended")
    try:
        normalized_spec = _validate_interaction_spec(body.kind, body.spec or {})
    except Exception as exc:  # pydantic ValidationError or ValueError
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    inserted = await service.insert_session_slide_after_current(
        session,
        row=row,
        kind=body.kind,
        parent_slide_id=body.parent_slide_id,
        widget_id=body.widget_id,
        spec=normalized_spec,
        inverted_theme=body.inverted_theme,
    )
    if body.kind == "random":
        inserted = await service.pick_random_audience(
            session,
            inserted,
            count=int(normalized_spec.get("count") or 1),
        )
    # Auto-advance to the new interaction slide.
    await service.advance_slide(session, row, inserted.id)
    from .ws import broadcast_session_slide_inserted, broadcast_slide_changed

    await broadcast_session_slide_inserted(row.id, inserted)
    await broadcast_slide_changed(row.id, inserted.id, True)
    return SessionSlideOut.model_validate(inserted)


async def _load_owned_session_slide(
    session: AsyncSession, user: AppUser, session_id: uuid.UUID, session_slide_id: uuid.UUID
):
    row = await _load_owned(session, user, session_id)
    slide = await service.load_session_slide(session, session_slide_id)
    if slide is None or slide.session_id != row.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction not found")
    return row, slide


@router.patch(
    "/{session_id}/interactions/{session_slide_id}", response_model=SessionSlideOut
)
async def patch_interaction(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    body: InteractionPatch,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    if slide.kind == "poll" and body.choices is not None:
        # Reject choice edits once any vote has landed.
        state = (slide.spec or {}).get("state") or {}
        voters = int((slide.results or {}).get("voters") or 0)
        if state.get("choices_locked") or voters > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "choices_locked", "voters": voters},
            )
    if slide.kind == "question" and body.choices is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="choices not allowed on a question")

    await service.update_interaction_spec(
        session,
        slide,
        question=body.question,
        prompt=body.prompt,
        choices=[c.model_dump() for c in body.choices] if body.choices is not None else None,
        config=body.config,
    )
    from .ws import broadcast_interaction_spec_updated

    await broadcast_interaction_spec_updated(slide.session_id, slide.id, slide.spec)
    return SessionSlideOut.model_validate(slide)


@router.get(
    "/{session_id}/interactions/{session_slide_id}/answers",
    response_model=list[OpenAnswerOut],
)
async def list_interaction_answers(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[OpenAnswerOut]:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    if slide.kind != "question":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="answers list is only available for question interactions",
        )
    answers = await service.list_open_answers(session, slide)
    return [OpenAnswerOut(**a) for a in answers]


@router.post(
    "/{session_id}/interactions/{session_slide_id}/promote/{log_id}",
    response_model=SessionSlideOut,
)
async def promote_answer(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    log_id: int,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    try:
        await service.promote_answer(session, slide, log_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    from .ws import broadcast_interaction_results_updated

    await broadcast_interaction_results_updated(slide.session_id, slide.id, slide.results)
    return SessionSlideOut.model_validate(slide)


@router.post(
    "/{session_id}/interactions/{session_slide_id}/unpromote/{log_id}",
    response_model=SessionSlideOut,
)
async def unpromote_answer(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    log_id: int,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    await service.unpromote_answer(session, slide, log_id)
    from .ws import broadcast_interaction_results_updated

    await broadcast_interaction_results_updated(slide.session_id, slide.id, slide.results)
    return SessionSlideOut.model_validate(slide)


@router.post(
    "/{session_id}/interactions/{session_slide_id}/hide/{log_id}",
    response_model=SessionSlideOut,
)
async def hide_answer(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    log_id: int,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    await service.hide_answer(session, slide, log_id)
    from .ws import broadcast_interaction_results_updated

    await broadcast_interaction_results_updated(slide.session_id, slide.id, slide.results)
    return SessionSlideOut.model_validate(slide)


@router.post(
    "/{session_id}/interactions/{session_slide_id}/reset", response_model=SessionSlideOut
)
async def reset_interaction(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    if slide.kind != "poll":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reset is only available for polls",
        )
    await service.reset_poll(session, slide)
    from .ws import (
        broadcast_interaction_results_updated,
        broadcast_interaction_spec_updated,
    )

    await broadcast_interaction_results_updated(slide.session_id, slide.id, slide.results)
    await broadcast_interaction_spec_updated(slide.session_id, slide.id, slide.spec)
    return SessionSlideOut.model_validate(slide)


@router.post(
    "/{session_id}/interactions/{session_slide_id}/close", response_model=SessionSlideOut
)
async def close_voting(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    await service.set_voting_closed(session, slide, True)
    from .ws import broadcast_interaction_spec_updated

    await broadcast_interaction_spec_updated(slide.session_id, slide.id, slide.spec)
    return SessionSlideOut.model_validate(slide)


@router.post(
    "/{session_id}/interactions/{session_slide_id}/reopen", response_model=SessionSlideOut
)
async def reopen_voting(
    session_id: uuid.UUID,
    session_slide_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> SessionSlideOut:
    _, slide = await _load_owned_session_slide(session, user, session_id, session_slide_id)
    await service.set_voting_closed(session, slide, False)
    from .ws import broadcast_interaction_spec_updated

    await broadcast_interaction_spec_updated(slide.session_id, slide.id, slide.spec)
    return SessionSlideOut.model_validate(slide)
