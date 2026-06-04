from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.deps import db_session
from ..db.models import AppUser, Participant
from ..db.models import Session as SessionRow
from ..settings import get_settings
from . import service
from .deps import current_user_profile
from .schemas import (
    AuthResponse,
    GuestJoinRequest,
    GuestJoinResponse,
    RefreshRequest,
    SignInRequest,
    SignUpRequest,
    UserOut,
)
from .supabase import get_supabase_auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: AppUser) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        approval_status=user.approval_status,
    )


@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignUpRequest, session: AsyncSession = Depends(db_session)) -> AuthResponse:
    sb = await get_supabase_auth().sign_up(body.email.lower(), body.password, body.display_name)
    user = await service.sync_supabase_user(
        session,
        supabase_user_id=uuid.UUID(sb.user_id),
        email=sb.email or body.email,
        display_name=body.display_name,
        default_status="pending",
    )
    user.approval_status = "pending"
    await session.flush()
    await session.commit()
    return AuthResponse(access=sb.access_token, refresh=sb.refresh_token, user=_user_out(user))


@router.post("/signin", response_model=AuthResponse)
async def signin(body: SignInRequest, session: AsyncSession = Depends(db_session)) -> AuthResponse:
    sb = await get_supabase_auth().sign_in(body.email.lower(), body.password)
    user = await service.sync_supabase_user(
        session,
        supabase_user_id=uuid.UUID(sb.user_id),
        email=sb.email or body.email,
        display_name=None,
        default_status="pending",
    )
    await session.commit()
    return AuthResponse(access=sb.access_token, refresh=sb.refresh_token, user=_user_out(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(db_session)) -> AuthResponse:
    sb = await get_supabase_auth().refresh(body.refresh_token)
    user = await service.sync_supabase_user(
        session,
        supabase_user_id=uuid.UUID(sb.user_id),
        email=sb.email,
        display_name=None,
        default_status="pending",
    )
    await session.commit()
    return AuthResponse(access=sb.access_token, refresh=sb.refresh_token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: AppUser = Depends(current_user_profile)) -> UserOut:
    return _user_out(user)


def _participant_ref(email: str, salt: str) -> str:
    return hashlib.sha256((email.strip().lower() + salt).encode("utf-8")).hexdigest()


def is_participant_unique_conflict(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return (
        "participant" in message
        and ("session_id" in message or "uq_participant_session_ref" in message)
        and "ref" in message
    )


def _apply_guest_profile(participant: Participant, body: GuestJoinRequest) -> None:
    if body.display_name and not participant.display_name:
        participant.display_name = body.display_name
    participant.anon = body.anonymous
    if body.anonymous:
        participant.email = None
    elif body.email and not participant.email:
        participant.email = body.email


@router.post("/guest", response_model=GuestJoinResponse)
async def guest(body: GuestJoinRequest, session: AsyncSession = Depends(db_session)) -> GuestJoinResponse:
    code = body.code.strip().upper()
    row = (
        await session.execute(
            select(SessionRow)
            .where(SessionRow.code == code)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    if row.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="session ended")
    ref = _participant_ref(body.email, row.salt)
    session_id = row.id
    participant = (
        await session.execute(
            select(Participant).where(Participant.session_id == session_id, Participant.ref == ref)
        )
    ).scalar_one_or_none()
    if participant is None:
        cap = get_settings().session_audience_cap
        existing = (
            await session.execute(
                select(func.count(Participant.id)).where(Participant.session_id == session_id)
            )
        ).scalar_one()
        if existing >= cap:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="session is at audience capacity",
            )
        participant = Participant(
            session_id=session_id,
            email=None if body.anonymous else body.email,
            display_name=body.display_name,
            anon=body.anonymous,
            ref=ref,
        )
        try:
            async with session.begin_nested():
                session.add(participant)
                await session.flush()
        except IntegrityError as exc:
            if not is_participant_unique_conflict(exc):
                raise
            participant = (
                await session.execute(
                    select(Participant).where(
                        Participant.session_id == session_id,
                        Participant.ref == ref,
                    )
                )
            ).scalar_one_or_none()
            if participant is None:
                raise
            _apply_guest_profile(participant, body)
            await session.flush()
    else:
        _apply_guest_profile(participant, body)
        await session.flush()
    token = service.issue_guest(participant.id, session_id, ref)
    return GuestJoinResponse(
        session_id=session_id,
        participant_id=participant.id,
        participant_ref=ref,
        token=token,
        display_name=participant.display_name,
        anon=participant.anon,
    )
