"""Analytics router for session transcript and replay."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import sqlalchemy as sa
from sqlalchemy import select, func

from ..db.models import Session, SessionEvent
from ..auth.deps import current_user
from ..db.deps import db_session
from . import service, export
from .service import SLIDE_TRACKING_ENABLED_AT

router = APIRouter(prefix="/sessions/{session_id}", tags=["analytics"])


async def _load_owned_session(
    session,
    user,
    session_id: uuid.UUID,
) -> Session:
    """Verify session ownership."""
    row = (
        await session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.owner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return row


@router.get("/replay")
async def get_session_replay(
    session_id: uuid.UUID,
    user = Depends(current_user),
    session = Depends(db_session),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return chronological event stream for session replay (FR-074)."""
    row = await _load_owned_session(session, user, session_id)
    
    events, total = await service.get_merged_transcript(session, session_id, row.workspace_id, limit=limit, offset=offset)
    return {
        "session_id": str(session_id),
        "events": events,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(events) < total,
    }


@router.get("/transcript")
async def get_session_transcript(
    session_id: uuid.UUID,
    user = Depends(current_user),
    session = Depends(db_session),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return structured transcript with per-slide + per-participant summaries."""
    row = await _load_owned_session(session, user, session_id)
    
    events, total = await service.get_merged_transcript(session, session_id, row.workspace_id, limit=limit, offset=offset)
    per_slide = await service.get_per_slide_summary(session, session_id)
    per_participant = await service.get_all_participant_summaries(session, session_id)
    
    # Check if pre-migration session: zero slide.advance events AND started before tracking date
    has_slide_advances = await session.execute(
        select(func.count()).select_from(SessionEvent).where(
            SessionEvent.session_id == session_id,
            SessionEvent.event_type == "slide.advance",
        )
    )
    slide_advance_count = has_slide_advances.scalar() or 0
    
    pre_migration_warning = None
    started_at = row.started_at
    # Normalize timezone for SQLite (returns naive datetimes)
    if started_at and started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if slide_advance_count == 0 and started_at and started_at < SLIDE_TRACKING_ENABLED_AT:
        pre_migration_warning = "This session ended before slide pacing tracking was enabled. Slide transitions are not available."
    
    return {
        "session_id": str(session_id),
        "deck_id": str(row.deck_id),
        "workspace_id": str(row.workspace_id),
        "started_at": row.started_at.isoformat(),
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(events) < total,
        "per_slide": per_slide,
        "per_participant": per_participant,
        "pre_migration_warning": pre_migration_warning,
    }


@router.get("/transcript.csv")
async def get_session_transcript_csv(
    session_id: uuid.UUID,
    user = Depends(current_user),
    session = Depends(db_session),
):
    """Export transcript as CSV (FR-076). Limit 10,000 events with metadata."""
    row = await _load_owned_session(session, user, session_id)
    
    events, total = await service.get_merged_transcript(session, session_id, row.workspace_id, limit=10000, max_limit=10000)
    truncated = total > len(events)
    csv_content = export.transcript_to_csv(events, total, len(events), truncated)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=session-{session_id}.csv"},
    )


@router.get("/transcript.json")
async def get_session_transcript_json(
    session_id: uuid.UUID,
    user = Depends(current_user),
    session = Depends(db_session),
):
    """Export transcript as .slaides-session JSON (FR-076). Limit 10,000 events with metadata."""
    row = await _load_owned_session(session, user, session_id)
    
    events, total = await service.get_merged_transcript(session, session_id, row.workspace_id, limit=10000, max_limit=10000)
    truncated = total > len(events)
    session_meta = {
        "id": str(session_id),
        "deck_id": str(row.deck_id),
        "started_at": row.started_at.isoformat(),
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
    }
    json_content = export.transcript_to_json(events, session_meta, total, truncated)
    
    return Response(
        content=json.dumps(json_content, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=session-{session_id}.slaides.json"},
    )


@router.delete("/transcript")
async def delete_session_transcript(
    session_id: uuid.UUID,
    user = Depends(current_user),
    session = Depends(db_session),
) -> dict:
    """Delete all transcript events for a session (session itself is preserved)."""
    row = await _load_owned_session(session, user, session_id)
    
    # Delete session_event rows
    deleted = await session.execute(
        sa.delete(SessionEvent).where(SessionEvent.session_id == session_id)
    )
    deleted_count = deleted.rowcount
    
    # Also clear interaction_log rows that have slide_id/session_slide_id for this session
    # (but keep the interaction_log entries themselves - they're part of the core session data)
    # Actually, for full history clear, we should delete interaction_log entries too
    # But that's more invasive. For now, just clear session_event (slide advances + LLM calls)
    
    await session.commit()
    
    return {
        "session_id": str(session_id),
        "deleted_events": deleted_count,
        "message": f"Deleted {deleted_count} transcript events. Session preserved.",
    }
