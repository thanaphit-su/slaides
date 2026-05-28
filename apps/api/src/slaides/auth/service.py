from __future__ import annotations

import time
import uuid

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppUser, Workspace
from ..settings import get_settings

GUEST_AUDIENCE = "slaides-guest"


def issue_guest(participant_id: uuid.UUID, session_id: uuid.UUID, ref: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(participant_id),
        "kind": "guest",
        "aud": GUEST_AUDIENCE,
        "sid": str(session_id),
        "ref": ref,
        "iat": now,
        "exp": now + settings.jwt_refresh_ttl,
    }
    return jwt.encode(payload, settings.guest_jwt_secret, algorithm="HS256")


def decode_guest(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.guest_jwt_secret,
        algorithms=["HS256"],
        audience=GUEST_AUDIENCE,
    )


async def get_or_create_pending_workspace(session: AsyncSession) -> Workspace:
    row = (
        await session.execute(select(Workspace).where(Workspace.name == "Pending Instructors"))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = Workspace(name="Pending Instructors")
    session.add(row)
    await session.flush()
    return row


async def sync_supabase_user(
    session: AsyncSession,
    *,
    supabase_user_id: uuid.UUID,
    email: str,
    display_name: str | None,
    default_status: str,
) -> AppUser:
    email = email.lower().strip()
    user = (
        await session.execute(select(AppUser).where(AppUser.supabase_user_id == supabase_user_id))
    ).scalar_one_or_none()
    if user is None:
        user = (
            await session.execute(select(AppUser).where(AppUser.email == email))
        ).scalar_one_or_none()
    if user is None:
        pending_ws = await get_or_create_pending_workspace(session)
        user = AppUser(
            workspace_id=pending_ws.id,
            supabase_user_id=supabase_user_id,
            email=email,
            display_name=display_name,
            role="instructor",
            approval_status=default_status,
        )
        session.add(user)
    else:
        if user.supabase_user_id is not None and user.supabase_user_id != supabase_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="user email is already linked to another Supabase account",
            )
        user.supabase_user_id = supabase_user_id
        if display_name and not user.display_name:
            user.display_name = display_name
    await session.flush()
    return user
