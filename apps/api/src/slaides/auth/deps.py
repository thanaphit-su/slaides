from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.deps import db_session
from ..db.models import AppUser, Participant
from ..db.models import Session as SessionRow
from . import service
from .supabase import get_supabase_auth


@dataclass
class GuestPrincipal:
    participant: Participant
    session_id: uuid.UUID
    ref: str

_bearer = HTTPBearer(auto_error=False)


def _require_approved_user(user: AppUser) -> AppUser:
    if user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account pending approval")
    if user.approval_status == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account rejected")
    return user


async def current_user_profile(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> AppUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = creds.credentials
    supabase_user_id, email = await get_supabase_auth().get_user(token)
    try:
        user_uuid = uuid.UUID(supabase_user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject") from exc
    return await service.sync_supabase_user(
        session,
        supabase_user_id=user_uuid,
        email=email,
        display_name=None,
        default_status="pending",
    )


async def current_user(user: AppUser = Depends(current_user_profile)) -> AppUser:
    return _require_approved_user(user)


def _decode_guest_token(token: str) -> dict:
    try:
        return service.decode_guest(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


async def _guest_from_payload(payload: dict, session: AsyncSession) -> GuestPrincipal:
    if payload.get("kind") != "guest":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="wrong token kind")
    try:
        participant_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject") from exc
    participant = (
        await session.execute(select(Participant).where(Participant.id == participant_id))
    ).scalar_one_or_none()
    if participant is None or participant.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="participant not found")
    session_row = (
        await session.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session not found")
    if session_row.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="session ended")
    return GuestPrincipal(participant=participant, session_id=session_id, ref=payload.get("ref", ""))


async def current_guest(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> GuestPrincipal:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = _decode_guest_token(creds.credentials)
    return await _guest_from_payload(payload, session)


async def current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> AppUser | GuestPrincipal:
    """Accept either an instructor access token or a guest token."""
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = creds.credentials
    try:
        guest_payload = service.decode_guest(token)
    except Exception:
        guest_payload = None
    if guest_payload is not None and guest_payload.get("kind") == "guest":
        return await _guest_from_payload(guest_payload, session)

    return _require_approved_user(await current_user_profile(creds, session))
