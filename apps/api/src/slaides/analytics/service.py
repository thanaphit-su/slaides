"""Transcript service layer - merged event stream and summaries."""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    SessionEvent, InteractionLog, Question, Participant,
    SessionSlide, Session
)
from .crypto import decrypt_for_transcript
from .crypto import decrypt_for_transcript


# Named constant for pre-migration warning
# Derived from first session_event row in the database
SLIDE_TRACKING_ENABLED_AT: datetime | None = None


async def get_slide_tracking_enabled_at(session: AsyncSession) -> datetime | None:
    """Get the earliest session_event timestamp, or None if no events exist."""
    global SLIDE_TRACKING_ENABLED_AT
    if SLIDE_TRACKING_ENABLED_AT is not None:
        return SLIDE_TRACKING_ENABLED_AT
    
    result = await session.execute(
        select(func.min(SessionEvent.occurred_at))
    )
    earliest = result.scalar()
    if earliest:
        SLIDE_TRACKING_ENABLED_AT = earliest.replace(tzinfo=timezone.utc)
    return SLIDE_TRACKING_ENABLED_AT


async def get_session_events(
    session: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 500,
    offset: int = 0,
    max_limit: int = 1000,
) -> tuple[list[dict], int]:
    """Return chronological session_event stream with pagination and total count."""
    limit = min(limit, max_limit)
    
    # Count total
    count_result = await session.execute(
        select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == session_id)
    )
    total = count_result.scalar() or 0
    
    # Fetch paginated
    rows = await session.execute(
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .order_by(SessionEvent.occurred_at, SessionEvent.id)
        .limit(limit)
        .offset(offset)
    )
    events = [
        {
            "id": r.id,
            "event_type": r.event_type,
            "payload": r.payload,
            "occurred_at": r.occurred_at.isoformat(),
            "source": "session_event",
        }
        for r in rows.scalars()
    ]
    return events, total


async def get_merged_transcript(
    session: AsyncSession,
    session_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 500,
    offset: int = 0,
    max_limit: int = 1000,
) -> tuple[list[dict], int]:
    """
    Merge events from multiple sources into chronological transcript.
    
    Fetches from each source with LIMIT/OFFSET applied per-source, then merges and sorts in Python.
    
    Sources:
    - session_event: slide.advance, llm.interpret
    - interaction_log: poll votes, open answers, widget contributions
    - question: raised questions
    - session_slide: interaction opened/closed
    
    Degrades gracefully for pre-migration sessions (no session_event rows).
    Decrypts llm.interpret selection/prompt fields before returning.
    Returns (events, total_count).
    """
    limit = min(limit, max_limit)
    
    # Get total count
    se_count = (await session.execute(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == session_id))).scalar() or 0
    il_count = (await session.execute(select(func.count()).select_from(InteractionLog).where(InteractionLog.session_id == session_id))).scalar() or 0
    q_count = (await session.execute(select(func.count()).select_from(Question).where(Question.session_id == session_id))).scalar() or 0
    ss_count = (await session.execute(select(func.count()).select_from(SessionSlide).where(SessionSlide.session_id == session_id))).scalar() or 0
    total = se_count + il_count + q_count + ss_count
    
    events = []
    
    # Fetch session events
    se_rows = await session.execute(
        select(SessionEvent).where(SessionEvent.session_id == session_id).order_by(SessionEvent.occurred_at).limit(limit).offset(offset)
    )
    for r in se_rows.scalars():
        payload = dict(r.payload) if r.payload else {}
        # Decrypt llm.interpret
        if r.event_type == "llm.interpret":
            if "selection_enc" in payload:
                try:
                    payload["selection"] = decrypt_for_transcript(workspace_id, payload["selection_enc"])
                    del payload["selection_enc"]
                except Exception:
                    payload["selection"] = "[unable to decrypt]"
                    del payload["selection_enc"]
            if "prompt_enc" in payload:
                try:
                    payload["prompt"] = decrypt_for_transcript(workspace_id, payload["prompt_enc"])
                    del payload["prompt_enc"]
                except Exception:
                    payload["prompt"] = "[unable to decrypt]"
                    del payload["prompt_enc"]
        events.append({
            "occurred_at": r.occurred_at.isoformat(),
            "event_type": r.event_type,
            "payload": payload,
            "source": "session_event",
        })
    
    # Fetch interaction log
    il_rows = await session.execute(
        select(InteractionLog).where(InteractionLog.session_id == session_id).order_by(InteractionLog.occurred_at).limit(limit).offset(offset)
    )
    for r in il_rows.scalars():
        payload = dict(r.payload) if r.payload else {}
        if r.participant_ref:
            payload["participant_ref"] = r.participant_ref
        if r.slide_id:
            payload["slide_id"] = str(r.slide_id)
        if r.session_slide_id:
            payload["session_slide_id"] = str(r.session_slide_id)
        if r.widget_id:
            payload["widget_id"] = str(r.widget_id)
        events.append({
            "occurred_at": r.occurred_at.isoformat(),
            "event_type": f"interaction.{r.kind}",
            "payload": payload,
            "source": "interaction_log",
        })
    
    # Fetch questions
    q_rows = await session.execute(
        select(Question).where(Question.session_id == session_id).order_by(Question.raised_at).limit(limit).offset(offset)
    )
    for r in q_rows.scalars():
        events.append({
            "occurred_at": r.raised_at.isoformat(),
            "event_type": "question.raised",
            "payload": {
                "question_id": str(r.id),
                "text": r.text,
                "participant_ref": r.participant_ref,
                "anon": str(r.anon),
                "slide_id": str(r.slide_id) if r.slide_id else None,
            },
            "source": "question",
        })
    
    # Fetch session slides (opened events)
    ss_rows = await session.execute(
        select(SessionSlide).where(SessionSlide.session_id == session_id).order_by(SessionSlide.opened_at).limit(limit).offset(offset)
    )
    for r in ss_rows.scalars():
        events.append({
            "occurred_at": r.opened_at.isoformat(),
            "event_type": "interaction.opened",
            "payload": {
                "session_slide_id": str(r.id),
                "kind": r.kind,
                "spec": r.spec,
                "parent_slide_id": str(r.parent_slide_id) if r.parent_slide_id else None,
            },
            "source": "session_slide",
        })
        if r.closed_at:
            events.append({
                "occurred_at": r.closed_at.isoformat(),
                "event_type": "interaction.closed",
                "payload": {
                    "session_slide_id": str(r.id),
                    "kind": r.kind,
                },
                "source": "session_slide",
            })
    
    # Sort by occurred_at and apply pagination
    events.sort(key=lambda e: e["occurred_at"])
    paginated = events[offset:offset + limit]
    
    return paginated, total


async def get_per_slide_summary(
    session: AsyncSession,
    session_id: uuid.UUID,
) -> list[dict]:
    """Count interactions per slide (deck + session slides) with by_kind breakdown."""
    # Deck slides (exclude rows that also have session_slide_id)
    deck_slide_counts = await session.execute(
        select(
            InteractionLog.slide_id,
            InteractionLog.kind,
            func.count(InteractionLog.id).label("count"),
        )
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.slide_id.isnot(None),
            InteractionLog.session_slide_id.is_(None),
        )
        .group_by(InteractionLog.slide_id, InteractionLog.kind)
    )
    
    # Session slides
    session_slide_counts = await session.execute(
        select(
            InteractionLog.session_slide_id,
            InteractionLog.kind,
            func.count(InteractionLog.id).label("count"),
        )
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.session_slide_id.isnot(None),
        )
        .group_by(InteractionLog.session_slide_id, InteractionLog.kind)
    )
    
    # Merge into per-slide summary
    summary = {}
    for row in deck_slide_counts:
        key = str(row.slide_id)
        if key not in summary:
            summary[key] = {"slide_id": key, "kind": "deck", "interaction_count": 0, "by_kind": {}}
        summary[key]["interaction_count"] += row.count
        summary[key]["by_kind"][row.kind] = row.count
    
    for row in session_slide_counts:
        key = str(row.session_slide_id)
        if key not in summary:
            summary[key] = {"slide_id": key, "kind": "session", "interaction_count": 0, "by_kind": {}}
        summary[key]["interaction_count"] += row.count
        summary[key]["by_kind"][row.kind] = row.count
    
    return list(summary.values())


async def get_per_participant_summary(
    session: AsyncSession,
    session_id: uuid.UUID,
    participant_ref: str,
) -> dict:
    """Count interactions by type for one participant."""
    counts = await session.execute(
        select(
            InteractionLog.kind,
            func.count(InteractionLog.id).label("count"),
        )
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.participant_ref == participant_ref,
        )
        .group_by(InteractionLog.kind)
    )
    
    by_kind = {row.kind: row.count for row in counts}
    total = sum(by_kind.values())
    
    # Get participant metadata
    participant = (await session.execute(
        select(Participant)
        .where(
            Participant.session_id == session_id,
            Participant.ref == participant_ref,
        )
    )).scalar_one_or_none()
    
    return {
        "participant_ref": participant_ref,
        "display_name": participant.display_name if participant and not participant.anon else "Anonymous",
        "anon": participant.anon if participant else True,
        "joined_at": participant.joined_at.isoformat() if participant else None,
        "total_interactions": total,
        "by_kind": by_kind,
    }


async def get_all_participant_summaries(
    session: AsyncSession,
    session_id: uuid.UUID,
) -> list[dict]:
    """Return summary for all participants in a session (single grouped query)."""
    # Get all participants
    participants = (await session.execute(
        select(Participant).where(Participant.session_id == session_id)
    )).scalars().all()
    
    if not participants:
        return []
    
    # Get all interaction counts grouped by participant_ref and kind
    interaction_counts = await session.execute(
        select(
            InteractionLog.participant_ref,
            InteractionLog.kind,
            func.count(InteractionLog.id).label("count"),
        )
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.participant_ref.in_([p.ref for p in participants]),
        )
        .group_by(InteractionLog.participant_ref, InteractionLog.kind)
    )
    
    # Build a dict: participant_ref -> {kind: count}
    counts_by_participant: dict[str, dict[str, int]] = {}
    for row in interaction_counts:
        if row.participant_ref not in counts_by_participant:
            counts_by_participant[row.participant_ref] = {}
        counts_by_participant[row.participant_ref][row.kind] = row.count
    
    # Build summaries
    summaries = []
    for p in participants:
        by_kind = counts_by_participant.get(p.ref, {})
        total = sum(by_kind.values())
        
        summaries.append({
            "participant_ref": p.ref,
            "display_name": p.display_name if not p.anon else "Anonymous",
            "anon": p.anon,
            "joined_at": p.joined_at.isoformat(),
            "total_interactions": total,
            "by_kind": by_kind,
        })
    
    return summaries
