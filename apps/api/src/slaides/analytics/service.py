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


# Named constant for pre-migration warning
# This is the migration deployment date - sessions before this won't have slide tracking
SLIDE_TRACKING_ENABLED_AT = datetime(2026, 5, 28, tzinfo=timezone.utc)


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
    Merge events from multiple sources into chronological transcript using SQL UNION ALL.
    
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
    
    # Get total count via UNION ALL subquery - cast all IDs to string for type compatibility
    count_query = sa.union_all(
        select(sa.cast(SessionEvent.id, sa.String)),
        select(sa.cast(InteractionLog.id, sa.String)),
        select(sa.cast(Question.id, sa.String)),
        select(sa.cast(SessionSlide.id, sa.String)),
    ).alias("all_ids")
    
    total = (await session.execute(
        select(func.count()).select_from(count_query)
    )).scalar() or 0
    
    # Build UNION ALL with explicit type casts for PostgreSQL compatibility
    # All columns must match types across union branches
    se_subq = select(
        SessionEvent.occurred_at,
        SessionEvent.event_type,
        sa.cast(SessionEvent.payload, sa.JSON).label("payload"),
        sa.literal("session_event").label("source"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("participant_ref"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("slide_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("session_slide_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("widget_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_text"),
        sa.cast(sa.literal(None, sa.Boolean), sa.Boolean).label("anon"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("kind"),
        sa.cast(sa.literal(None, sa.JSON), sa.JSON).label("spec"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("parent_slide_id"),
    ).where(SessionEvent.session_id == session_id)
    
    il_subq = select(
        InteractionLog.occurred_at,
        sa.cast(sa.literal("interaction.", sa.String) + InteractionLog.kind, sa.String).label("event_type"),
        sa.cast(InteractionLog.payload, sa.JSON).label("payload"),
        sa.literal("interaction_log").label("source"),
        InteractionLog.participant_ref,
        sa.cast(InteractionLog.slide_id, sa.String).label("slide_id"),
        sa.cast(InteractionLog.session_slide_id, sa.String).label("session_slide_id"),
        sa.cast(InteractionLog.widget_id, sa.String).label("widget_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_text"),
        sa.cast(sa.literal(None, sa.Boolean), sa.Boolean).label("anon"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("kind"),
        sa.cast(sa.literal(None, sa.JSON), sa.JSON).label("spec"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("parent_slide_id"),
    ).where(InteractionLog.session_id == session_id)
    
    # Build JSON payload - use jsonb_build_object for PostgreSQL (variadic key-value)
    # For SQLite, json_object with same syntax works
    q_payload = sa.cast(
        sa.func.jsonb_build_object(
            'question_id', sa.cast(Question.id, sa.String),
            'text', Question.text,
            'participant_ref', Question.participant_ref,
            'anon', Question.anon,
            'slide_id', sa.cast(Question.slide_id, sa.String)
        ), sa.JSON
    )
    
    # For question rows, we'll build payload in Python (database-agnostic)
    q_subq = select(
        Question.raised_at.label("occurred_at"),
        sa.literal("question.raised").label("event_type"),
        sa.cast(sa.literal(None, sa.JSON), sa.JSON).label("payload"),  # Will be built in Python
        sa.literal("question").label("source"),
        Question.participant_ref,
        sa.cast(Question.slide_id, sa.String).label("slide_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("session_slide_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("widget_id"),
        sa.cast(Question.id, sa.String).label("question_id"),
        Question.text.label("question_text"),
        Question.anon,
        sa.cast(sa.literal(None, sa.String), sa.String).label("kind"),
        sa.cast(sa.literal(None, sa.JSON), sa.JSON).label("spec"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("parent_slide_id"),
    ).where(Question.session_id == session_id)
    
    # For session_slide rows, we'll build payload in Python (database-agnostic)
    ss_subq = select(
        SessionSlide.opened_at.label("occurred_at"),
        sa.literal("interaction.opened").label("event_type"),
        sa.cast(sa.literal(None, sa.JSON), sa.JSON).label("payload"),  # Built in Python
        sa.literal("session_slide").label("source"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("participant_ref"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("slide_id"),
        sa.cast(SessionSlide.id, sa.String).label("session_slide_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("widget_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_id"),
        sa.cast(sa.literal(None, sa.String), sa.String).label("question_text"),
        sa.cast(sa.literal(None, sa.Boolean), sa.Boolean).label("anon"),
        SessionSlide.kind,
        SessionSlide.spec,
        sa.cast(SessionSlide.parent_slide_id, sa.String).label("parent_slide_id"),
    ).where(SessionSlide.session_id == session_id)
    
    # Union all and paginate in SQL
    union_query = sa.union_all(se_subq, il_subq, q_subq, ss_subq)
    ordered = union_query.order_by(sa.column("occurred_at"))
    paginated_query = ordered.limit(limit).offset(offset)
    
    rows = await session.execute(paginated_query)
    
    events = []
    for r in rows:
        # Build payload based on source
        if r.source == "session_event":
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
        elif r.source == "interaction_log":
            payload = dict(r.payload) if r.payload else {}
            if r.participant_ref:
                payload["participant_ref"] = r.participant_ref
        elif r.source == "question":
            payload = {
                "question_id": r.question_id,
                "text": r.question_text,
                "participant_ref": r.participant_ref,
                "anon": bool(r.anon) if r.anon is not None else False,
                "slide_id": r.slide_id,
            }
        elif r.source == "session_slide":
            payload = {
                "session_slide_id": r.session_slide_id,
                "kind": r.kind,
                "spec": r.spec,
                "parent_slide_id": r.parent_slide_id,
            }
        else:
            payload = {}
        
        events.append({
            "occurred_at": r.occurred_at.isoformat(),
            "event_type": r.event_type,
            "payload": payload,
            "source": r.source,
        })
    
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
