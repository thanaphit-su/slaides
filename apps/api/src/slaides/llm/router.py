from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import GuestPrincipal, current_principal
from ..db.deps import db_session
from ..db.models import AppUser, Workspace
from ..db.models import Session as SessionRow
from .schemas import LlmCompleteRequest
from .service import stream_completion

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/complete")
async def complete(
    body: LlmCompleteRequest,
    principal: AppUser | GuestPrincipal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    user: AppUser | None = principal if isinstance(principal, AppUser) else None
    session_id = None

    if isinstance(principal, GuestPrincipal):
        if body.purpose != "interpret":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="guest tokens can only interpret selected slide text",
            )
        session_id = principal.session_id
        live_session = (
            await session.execute(select(SessionRow).where(SessionRow.id == principal.session_id))
        ).scalar_one_or_none()
        if live_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        workspace_id = live_session.workspace_id
    else:
        workspace_id = principal.workspace_id
        # For signed-in users, validate session_id from context (fail closed)
        if body.context.get("session_id"):
            try:
                candidate_session_id = uuid.UUID(body.context["session_id"])
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="invalid session_id format",
                )
            
            candidate_session = (
                await session.execute(
                    select(SessionRow).where(SessionRow.id == candidate_session_id)
                )
            ).scalar_one_or_none()
            
            if not candidate_session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="session not found",
                )
            
            if candidate_session.workspace_id != principal.workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="session does not belong to your workspace",
                )
            
            session_id = candidate_session_id

    workspace = (await session.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace missing")
    return StreamingResponse(
        stream_completion(session=session, user=user, workspace=workspace, body=body, session_id=session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
