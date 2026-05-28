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
    
    Uses SQL UNION ALL with LIMIT/OFFSET to push pagination into the database.
    
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
    
    # Get total count first
    count_result = await session.execute(
        select(
            func.count().label("total")
        ).select_from(
            sa.union_all(
                select(SessionEvent.session_id),
                select(InteractionLog.session_id),
                select(Question.session_id),
                select(SessionSlide.session_id),
            ).subquery()
        ).where(
            sa.column("session_id") == session_id
        )
    )
    total = count_result.scalar() or 0
    
    # Build UNION ALL query with proper ordering
    # Each subquery returns: occurred_at, event_type, payload, source
    se_subq = select(
        SessionEvent.occurred_at,
        SessionEvent.event_type,
        SessionEvent.payload,
        sa.literal("session_event").label("source"),
        sa.literal(None).label("participant_ref"),
        sa.literal(None).label("slide_id"),
        sa.literal(None).label("session_slide_id"),
        sa.literal(None).label("widget_id"),
        sa.literal(None).label("question_id"),
        sa.literal(None).label("text"),
        sa.literal(None).label("anon"),
        sa.literal(None).label("kind"),
        sa.literal(None).label("spec"),
        sa.literal(None).label("parent_slide_id"),
    ).where(SessionEvent.session_id == session_id)
    
    il_subq = select(
        InteractionLog.occurred_at,
        (sa.literal("interaction.") + InteractionLog.kind).label("event_type"),
        InteractionLog.payload,
        sa.literal("interaction_log").label("source"),
        InteractionLog.participant_ref,
        InteractionLog.slide_id,
        InteractionLog.session_slide_id,
        InteractionLog.widget_id,
        sa.literal(None).label("question_id"),
        sa.literal(None).label("text"),
        sa.literal(None).label("anon"),
        sa.literal(None).label("kind"),
        sa.literal(None).label("spec"),
        sa.literal(None).label("parent_slide_id"),
    ).where(InteractionLog.session_id == session_id)
    
    q_subq = select(
        Question.raised_at.label("occurred_at"),
        sa.literal("question.raised").label("event_type"),
        sa.cast(
            sa.func.json_object(
                'question_id', sa.cast(Question.id, sa.String),
                'text', Question.text,
                'participant_ref', Question.participant_ref,
                'anon', Question.anon,
                'slide_id', sa.cast(Question.slide_id, sa.String)
            ), sa.JSON
        ).label("payload"),
        sa.literal("question").label("source"),
        Question.participant_ref,
        sa.literal(None).label("slide_id"),
        sa.literal(None).label("session_slide_id"),
        sa.literal(None).label("widget_id"),
        Question.id.label("question_id"),
        Question.text,
        Question.anon,
        sa.literal(None).label("kind"),
        sa.literal(None).label("spec"),
        sa.literal(None).label("parent_slide_id"),
    ).where(Question.session_id == session_id)
    
    ss_open_subq = select(
        SessionSlide.opened_at.label("occurred_at"),
        sa.literal("interaction.opened").label("event_type"),
        sa.cast(
            sa.func.json_object(
                'session_slide_id', sa.cast(SessionSlide.id, sa.String),
                'kind', SessionSlide.kind,
                'spec', SessionSlide.spec,
                'parent_slide_id', sa.cast(SessionSlide.parent_slide_id, sa.String)
            ), sa.JSON
        ).label("payload"),
        sa.literal("session_slide").label("source"),
        sa.literal(None).label("participant_ref"),
        sa.literal(None).label("slide_id"),
        sa.literal(None).label("session_slide_id"),
        sa.literal(None).label("widget_id"),
        sa.literal(None).label("question_id"),
        sa.literal(None).label("text"),
        sa.literal(None).label("anon"),
        SessionSlide.kind,
        SessionSlide.spec,
        SessionSlide.parent_slide_id,
    ).where(SessionSlide.session_id == session_id)
    
    # Union all subqueries
    union_query = sa.union_all(se_subq, il_subq, q_subq, ss_open_subq)
    
    # Order and paginate
    ordered = union_query.order_by(sa.column("occurred_at"))
    paginated_query = ordered.limit(limit).offset(offset)
    
    rows = await session.execute(paginated_query)
    
    events = []
    for r in rows:
        event = {
            "occurred_at": r.occurred_at.isoformat(),
            "event_type": r.event_type,
            "payload": r.payload if r.payload else {},
            "source": r.source,
        }
        # Add participant_ref to payload if present
        if r.participant_ref:
            event["payload"]["participant_ref"] = r.participant_ref
        
        # Decrypt llm.interpret selection/prompt fields
        if r.event_type == "llm.interpret" and r.source == "session_event":
            payload = event["payload"]
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
        
        events.append(event)
    
    return events, total


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
