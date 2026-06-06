from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..db.models import (
    Deck,
    InteractionLog,
    Participant,
    Question,
    Session as SessionRow,
    SessionSlide,
    Slide,
)
from .aggregators import (
    AggregatorError,
    append_contribute,
    tally_contribute,
    tally_public,
)

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_AMBIGUOUS = set("O0I1")


def _random_code_segment(n: int) -> str:
    pool = "".join(c for c in CODE_ALPHABET if c not in CODE_AMBIGUOUS)
    return "".join(secrets.choice(pool) for _ in range(n))


def generate_code() -> str:
    return f"SLD-{_random_code_segment(4)}-{_random_code_segment(2)}"


def generate_salt() -> str:
    return secrets.token_hex(16)


def generate_mirror_token() -> str:
    return secrets.token_urlsafe(32)


async def _code_taken(session: AsyncSession, code: str) -> bool:
    row = (await session.execute(select(SessionRow.id).where(SessionRow.code == code))).first()
    return row is not None


async def create_session(
    session: AsyncSession,
    deck: Deck,
    owner_id: uuid.UUID,
) -> SessionRow:
    code = generate_code()
    for _ in range(8):
        if not await _code_taken(session, code):
            break
        code = generate_code()
    first_slide = (
        await session.execute(
            select(Slide).where(Slide.deck_id == deck.id).order_by(Slide.position).limit(1)
        )
    ).scalar_one_or_none()
    row = SessionRow(
        deck_id=deck.id,
        owner_id=owner_id,
        workspace_id=deck.workspace_id,
        code=code,
        salt=generate_salt(),
        mirror_token=generate_mirror_token(),
        current_slide_id=first_slide.id if first_slide else None,
        config={},
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    
    # Log initial slide display
    if first_slide:
        from ..analytics.events import log_slide_advance
        await log_slide_advance(session, row.id, None, first_slide.id)
    
    return row


async def end_session(session: AsyncSession, row: SessionRow) -> SessionRow:
    if row.ended_at is None:
        row.ended_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(row)
    return row


async def advance_slide(
    session: AsyncSession,
    row: SessionRow,
    slide_id: uuid.UUID,
) -> SessionRow:
    from_id = row.current_slide_id
    
    # No-op if already on this slide
    if from_id == slide_id:
        return row
    
    row.current_slide_id = slide_id
    
    # Log the transition event - let _get_slide_kind determine the kind
    from ..analytics.events import log_slide_advance
    await log_slide_advance(session, row.id, from_id, slide_id)
    
    await session.flush()
    await session.refresh(row)
    return row


async def list_session_slides(
    session: AsyncSession, session_id: uuid.UUID
) -> list[SessionSlide]:
    result = await session.execute(
        select(SessionSlide)
        .where(SessionSlide.session_id == session_id)
        .order_by(SessionSlide.position)
    )
    return list(result.scalars())


async def list_questions(session: AsyncSession, session_id: uuid.UUID) -> list[Question]:
    result = await session.execute(
        select(Question).where(Question.session_id == session_id).order_by(Question.raised_at)
    )
    return list(result.scalars())


async def list_participants(session: AsyncSession, session_id: uuid.UUID) -> list[Participant]:
    result = await session.execute(
        select(Participant)
        .where(Participant.session_id == session_id, Participant.left_at.is_(None))
        .order_by(Participant.joined_at)
    )
    return list(result.scalars())


async def append_session_slide(
    session: AsyncSession,
    session_id: uuid.UUID,
    kind: str,
    parent_slide_id: uuid.UUID | None,
    widget_id: uuid.UUID | None,
    spec: dict,
    inverted_theme: bool,
) -> SessionSlide:
    next_pos = await session.execute(
        select(func.coalesce(func.max(SessionSlide.position), -1)).where(
            SessionSlide.session_id == session_id
        )
    )
    pos = int(next_pos.scalar() or -1) + 1
    row = SessionSlide(
        session_id=session_id,
        parent_slide_id=parent_slide_id,
        widget_id=widget_id,
        position=pos,
        kind=kind,
        spec=spec or {},
        results={},
        inverted_theme=inverted_theme,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def insert_session_slide_after_current(
    session: AsyncSession,
    row: SessionRow,
    kind: str,
    parent_slide_id: uuid.UUID | None,
    widget_id: uuid.UUID | None,
    spec: dict,
    inverted_theme: bool,
) -> SessionSlide:
    """Insert a live interaction into the current presentation point.

    Session slides are anchored to a deck slide via parent_slide_id and ordered
    within that anchor by position. Launching from a deck slide inserts as the
    first interaction after it; launching from an existing interaction inserts
    immediately after that interaction.
    """
    current_session_slide = None
    if row.current_slide_id is not None:
        current_session_slide = (
            await session.execute(
                select(SessionSlide).where(
                    SessionSlide.id == row.current_slide_id,
                    SessionSlide.session_id == row.id,
                )
            )
        ).scalar_one_or_none()

    if current_session_slide is not None:
        anchor_parent_id = current_session_slide.parent_slide_id or parent_slide_id
        insert_pos = current_session_slide.position + 1
    elif row.current_slide_id is not None:
        anchor_parent_id = row.current_slide_id
        insert_pos = 0
    else:
        anchor_parent_id = parent_slide_id
        next_pos = await session.execute(
            select(func.coalesce(func.max(SessionSlide.position), -1)).where(
                SessionSlide.session_id == row.id,
                _session_slide_parent_filter(anchor_parent_id),
            )
        )
        insert_pos = int(next_pos.scalar() or -1) + 1

    siblings = (
        await session.execute(
            select(SessionSlide).where(
                SessionSlide.session_id == row.id,
                _session_slide_parent_filter(anchor_parent_id),
                SessionSlide.position >= insert_pos,
            )
        )
    ).scalars()
    for sibling in siblings:
        sibling.position += 1

    inserted = SessionSlide(
        session_id=row.id,
        parent_slide_id=anchor_parent_id,
        widget_id=widget_id,
        position=insert_pos,
        kind=kind,
        spec=spec or {},
        results={},
        inverted_theme=inverted_theme,
    )
    session.add(inserted)
    await session.flush()
    await session.refresh(inserted)
    return inserted


def _session_slide_parent_filter(parent_slide_id: uuid.UUID | None):
    if parent_slide_id is None:
        return SessionSlide.parent_slide_id.is_(None)
    return SessionSlide.parent_slide_id == parent_slide_id


async def pick_random_audience(
    session: AsyncSession,
    slide: SessionSlide,
    count: int,
) -> SessionSlide:
    participants = await list_participants(session, slide.session_id)
    sampled = secrets.SystemRandom().sample(participants, k=min(count, len(participants)))
    slide.results = {
        "requested_count": count,
        "eligible_count": len(participants),
        "picked": [
            {
                "participant_ref": p.ref,
                "display_name": p.display_name,
                "anon": p.anon,
            }
            for p in sampled
        ],
    }
    flag_modified(slide, "results")
    await session.flush()
    await session.refresh(slide)
    return slide


async def log_interaction(
    session: AsyncSession,
    session_id: uuid.UUID,
    slide_id: uuid.UUID | None,
    widget_id: uuid.UUID | None,
    participant_ref: str,
    kind: str,
    payload: dict,
) -> InteractionLog:
    row = InteractionLog(
        session_id=session_id,
        slide_id=slide_id,
        widget_id=widget_id,
        participant_ref=participant_ref,
        kind=kind,
        payload=payload or {},
    )
    session.add(row)
    await session.flush()
    return row


async def add_question(
    session: AsyncSession,
    session_id: uuid.UUID,
    slide_id: uuid.UUID | None,
    participant_ref: str,
    text: str,
    anon: bool,
) -> Question:
    row = Question(
        session_id=session_id,
        slide_id=slide_id,
        participant_ref=participant_ref,
        anon=anon,
        text=text,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


# ---- Live-interaction helpers (poll / open question) ----
#
# Poll votes and open-question answers are both written to interaction_log, but
# scoped to session_slide.id so each interaction has its own clean event stream.
# Aggregates are recomputed from the log after each write and stored on
# session_slide.results so audience snapshots include the live tally / promoted
# answers without an extra query.


async def load_session_slide(
    session: AsyncSession, session_slide_id: uuid.UUID
) -> SessionSlide | None:
    return (
        await session.execute(select(SessionSlide).where(SessionSlide.id == session_slide_id))
    ).scalar_one_or_none()


def _bump_spec(slide: SessionSlide, mutator) -> None:
    """Apply a mutation to slide.spec and tell SQLAlchemy the JSON column changed."""
    spec = dict(slide.spec or {})
    mutator(spec)
    slide.spec = spec
    flag_modified(slide, "spec")


def _bump_results(slide: SessionSlide, mutator) -> None:
    results = dict(slide.results or {})
    mutator(results)
    slide.results = results
    flag_modified(slide, "results")


async def _recompute_poll_tally(
    session: AsyncSession, slide: SessionSlide
) -> dict:
    """Aggregate poll_vote rows for the slide and store the tally on results.

    Folds the raw log rows through the `tally` aggregator (the same pure
    function the Widgets v2 unified protocol uses), then projects to the
    audience-visible state. This keeps the legacy `interaction_log` storage
    *and* exercises the aggregator code on every native poll vote, so any
    regression in the aggregator surfaces on real production traffic before
    Step 4 generalises it to LLM-generated widgets.
    """
    rows = (
        await session.execute(
            select(InteractionLog.payload, InteractionLog.participant_ref)
            .where(
                InteractionLog.session_slide_id == slide.id,
                InteractionLog.kind == "poll_vote",
            )
            .order_by(InteractionLog.occurred_at)
        )
    ).all()
    agg_state: dict = {}
    for payload, ref in rows:
        choice = str((payload or {}).get("choice") or "")
        if not choice:
            continue
        agg_state = tally_contribute(agg_state, choice, ref)
    public = tally_public(agg_state)

    # Capture "other" responses inline so the presenter view can see them
    # without an extra fetch. We only include them when allow_other is on.
    other_rows = (
        await session.execute(
            select(
                InteractionLog.id, InteractionLog.payload, InteractionLog.participant_ref
            ).where(
                InteractionLog.session_slide_id == slide.id,
                InteractionLog.kind == "poll_other",
            ).order_by(InteractionLog.occurred_at)
        )
    ).all()
    other_responses = [
        {"id": str(rid), "text": str((p or {}).get("text") or ""), "ref": ref}
        for rid, p, ref in other_rows
    ]

    def apply(r: dict) -> None:
        r["tally"] = public.get("tally", {})
        r["voters"] = public.get("voters", 0)
        r["other_responses"] = other_responses

    _bump_results(slide, apply)
    return slide.results


async def record_poll_vote(
    session: AsyncSession,
    slide: SessionSlide,
    participant_ref: str,
    choice_id: str,
) -> dict:
    """Upsert a single-choice vote. Re-voting overwrites the previous vote.

    Returns the new results dict.
    """
    # UPSERT in application code (SQLite test DB can't do a partial unique idx).
    await session.execute(
        delete(InteractionLog).where(
            InteractionLog.session_slide_id == slide.id,
            InteractionLog.participant_ref == participant_ref,
            InteractionLog.kind == "poll_vote",
        )
    )
    session.add(
        InteractionLog(
            session_id=slide.session_id,
            session_slide_id=slide.id,
            participant_ref=participant_ref,
            kind="poll_vote",
            payload={"choice": choice_id},
        )
    )
    await session.flush()
    await _recompute_poll_tally(session, slide)
    # Once a vote has landed, the presenter can no longer edit the choice list.
    _bump_spec(slide, lambda s: s.setdefault("state", {}).update({"choices_locked": True}))
    await session.flush()
    return slide.results


async def record_poll_other(
    session: AsyncSession,
    slide: SessionSlide,
    participant_ref: str,
    text: str,
) -> dict:
    text = (text or "").strip()
    if not text:
        return slide.results
    # Replace any existing "other" from this participant.
    await session.execute(
        delete(InteractionLog).where(
            InteractionLog.session_slide_id == slide.id,
            InteractionLog.participant_ref == participant_ref,
            InteractionLog.kind == "poll_other",
        )
    )
    session.add(
        InteractionLog(
            session_id=slide.session_id,
            session_slide_id=slide.id,
            participant_ref=participant_ref,
            kind="poll_other",
            payload={"text": text[:200]},
        )
    )
    await session.flush()
    await _recompute_poll_tally(session, slide)
    await session.flush()
    return slide.results


async def record_open_answer(
    session: AsyncSession,
    slide: SessionSlide,
    participant_ref: str,
    text: str,
) -> InteractionLog:
    """Append an open answer. Runs through the `append` aggregator so the
    `total_answers` counter shares the same source of truth the Loud-widget
    protocol will use; the raw text still persists to `interaction_log` for
    transcript replay.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("answer text required")
    truncated = text[:2000]
    row = InteractionLog(
        session_id=slide.session_id,
        session_slide_id=slide.id,
        participant_ref=participant_ref,
        kind="open_answer",
        payload={"text": truncated},
    )
    session.add(row)
    await session.flush()

    # Run the append aggregator over the current `total_answers` so we share
    # the math with the Loud-widget protocol. We deliberately don't store
    # `entries` here — open answers stream host-only via `question_answer.new`
    # until the moderator promotes them — but the running counter must match
    # exactly what the aggregator computes.
    try:
        next_state = append_contribute(
            {"total": int((slide.results or {}).get("total_answers") or 0)},
            truncated,
            participant_ref,
        )
    except AggregatorError:
        # Defensive — the existing path would silently accept any string; the
        # 2 KB cap is well below the 2000-char truncation above.
        next_state = {"total": int((slide.results or {}).get("total_answers") or 0) + 1}

    def apply(r: dict) -> None:
        r["total_answers"] = int(next_state.get("total", 0))
        r.setdefault("promoted", r.get("promoted") or [])

    _bump_results(slide, apply)
    await session.flush()
    return row


async def list_open_answers(
    session: AsyncSession,
    slide: SessionSlide,
) -> list[dict]:
    """Return all open-question answers for the presenter's moderation rail."""
    rows = (
        await session.execute(
            select(InteractionLog).where(
                InteractionLog.session_slide_id == slide.id,
                InteractionLog.kind == "open_answer",
            ).order_by(InteractionLog.occurred_at.desc())
        )
    ).scalars().all()
    promoted_ids = {p.get("id") for p in (slide.results or {}).get("promoted", [])}
    refs = {r.participant_ref for r in rows}
    name_by_ref: dict[str, tuple[str | None, bool]] = {}
    if refs:
        prows = (
            await session.execute(
                select(Participant).where(
                    Participant.session_id == slide.session_id,
                    Participant.ref.in_(refs),
                )
            )
        ).scalars().all()
        for p in prows:
            name_by_ref[p.ref] = (p.display_name, bool(p.anon))
    out: list[dict] = []
    for row in rows:
        display_name, anon = name_by_ref.get(row.participant_ref, (None, True))
        out.append(
            {
                "id": int(row.id),
                "text": str((row.payload or {}).get("text") or ""),
                "participant_ref": row.participant_ref,
                "display_name": None if anon else display_name,
                "anon": anon,
                "occurred_at": row.occurred_at,
                "promoted": str(row.id) in promoted_ids,
            }
        )
    return out


async def promote_answer(
    session: AsyncSession,
    slide: SessionSlide,
    log_id: int,
) -> dict:
    log = (
        await session.execute(
            select(InteractionLog).where(
                InteractionLog.id == log_id,
                InteractionLog.session_slide_id == slide.id,
                InteractionLog.kind == "open_answer",
            )
        )
    ).scalar_one_or_none()
    if log is None:
        raise ValueError("answer not found")
    participant = (
        await session.execute(
            select(Participant).where(
                Participant.session_id == slide.session_id,
                Participant.ref == log.participant_ref,
            )
        )
    ).scalar_one_or_none()
    display_name = participant.display_name if participant else None
    anon = bool(participant.anon) if participant else True

    entry = {
        "id": str(log.id),
        "text": str((log.payload or {}).get("text") or ""),
        "display_name": None if anon else display_name,
        "anon": anon,
    }

    def apply(r: dict) -> None:
        promoted = list(r.get("promoted") or [])
        # Replace if already promoted (updates name/anon if changed).
        promoted = [p for p in promoted if p.get("id") != entry["id"]]
        promoted.append(entry)
        r["promoted"] = promoted

    _bump_results(slide, apply)
    await session.flush()
    return slide.results


async def unpromote_answer(
    session: AsyncSession, slide: SessionSlide, log_id: int
) -> dict:
    target = str(log_id)

    def apply(r: dict) -> None:
        r["promoted"] = [p for p in (r.get("promoted") or []) if p.get("id") != target]

    _bump_results(slide, apply)
    await session.flush()
    return slide.results


async def hide_answer(
    session: AsyncSession, slide: SessionSlide, log_id: int
) -> dict:
    """Delete an open answer from interaction_log AND from the promoted list."""
    await session.execute(
        delete(InteractionLog).where(
            InteractionLog.id == log_id,
            InteractionLog.session_slide_id == slide.id,
            InteractionLog.kind == "open_answer",
        )
    )
    target = str(log_id)

    def apply(r: dict) -> None:
        r["promoted"] = [p for p in (r.get("promoted") or []) if p.get("id") != target]
        r["total_answers"] = max(0, int(r.get("total_answers") or 1) - 1)

    _bump_results(slide, apply)
    await session.flush()
    return slide.results


async def reset_poll(session: AsyncSession, slide: SessionSlide) -> dict:
    await session.execute(
        delete(InteractionLog).where(
            InteractionLog.session_slide_id == slide.id,
            InteractionLog.kind.in_(("poll_vote", "poll_other")),
        )
    )
    def apply(r: dict) -> None:
        r["tally"] = {}
        r["voters"] = 0
        r["other_responses"] = []

    _bump_results(slide, apply)
    # Unlock choices so the presenter can edit again after a reset.
    _bump_spec(slide, lambda s: s.setdefault("state", {}).update({"choices_locked": False}))
    await session.flush()
    return slide.results


async def set_voting_closed(
    session: AsyncSession, slide: SessionSlide, closed: bool
) -> dict:
    _bump_spec(slide, lambda s: s.setdefault("state", {}).update({"voting_closed": bool(closed)}))
    await session.flush()
    return slide.spec


async def update_interaction_spec(
    session: AsyncSession,
    slide: SessionSlide,
    *,
    question: str | None = None,
    prompt: str | None = None,
    choices: list[dict] | None = None,
    config: dict | None = None,
) -> dict:
    spec = dict(slide.spec or {})
    if question is not None and spec.get("type") == "poll":
        spec["question"] = question
    if prompt is not None and spec.get("type") == "question":
        spec["prompt"] = prompt
    if config is not None:
        merged = dict(spec.get("config") or {})
        merged.update(config)
        spec["config"] = merged
    if choices is not None:
        # Caller enforces choices_locked / voters > 0; this just persists.
        spec["choices"] = choices
    slide.spec = spec
    flag_modified(slide, "spec")
    await session.flush()
    return slide.spec
