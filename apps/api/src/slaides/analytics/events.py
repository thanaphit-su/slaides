"""Event logging helpers for session transcript."""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import SessionEvent, Slide, SessionSlide
from .crypto import encrypt_for_transcript, hash_for_transcript


async def _get_slide_kind(session: AsyncSession, slide_id: uuid.UUID | None) -> str | None:
    """Query both deck.slide and session_slide tables to determine kind."""
    if slide_id is None:
        return None
    
    # Try deck slide first
    deck_slide = (await session.execute(
        sa.select(Slide).where(Slide.id == slide_id)
    )).scalar_one_or_none()
    if deck_slide:
        return "deck"
    
    # Try session slide
    session_slide = (await session.execute(
        sa.select(SessionSlide).where(SessionSlide.id == slide_id)
    )).scalar_one_or_none()
    if session_slide:
        return "session"
    
    return None


async def log_slide_advance(
    session: AsyncSession,
    session_id: uuid.UUID,
    from_id: uuid.UUID | None,
    to_id: uuid.UUID,
    from_kind: str | None = None,
    to_kind: str | None = None,
) -> None:
    """Log a slide transition event."""
    if from_kind is None:
        from_kind = await _get_slide_kind(session, from_id)
    if to_kind is None:
        to_kind = await _get_slide_kind(session, to_id)
    
    session.add(
        SessionEvent(
            session_id=session_id,
            event_type="slide.advance",
            payload={
                "from_id": str(from_id) if from_id else None,
                "from_kind": from_kind,
                "to_id": str(to_id),
                "to_kind": to_kind,
            },
        )
    )


async def log_llm_interpret(
    session: AsyncSession,
    session_id: uuid.UUID,
    workspace_id: uuid.UUID,
    selection: str,
    prompt: str,
    slide_id: uuid.UUID | None,
    log_prompts: bool,
    cache_hit: bool = False,
) -> None:
    """Log LLM interpret call metadata for transcript."""
    selection_hash = hash_for_transcript(selection)
    prompt_hash = hash_for_transcript(prompt)
    
    payload = {
        "selection_hash": selection_hash,
        "prompt_hash": prompt_hash,
        "slide_id": str(slide_id) if slide_id else None,
        "cache_hit": cache_hit,
    }
    
    if log_prompts:
        payload["selection_enc"] = encrypt_for_transcript(workspace_id, selection)
        payload["prompt_enc"] = encrypt_for_transcript(workspace_id, prompt)
    
    session.add(
        SessionEvent(
            session_id=session_id,
            event_type="llm.interpret",
            payload=payload,
        )
    )
