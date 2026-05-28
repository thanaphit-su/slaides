from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    role: str
    approval_status: str


class AuthResponse(BaseModel):
    access: str
    refresh: str
    user: UserOut


class GuestJoinRequest(BaseModel):
    code: str
    email: EmailStr
    display_name: str | None = None
    anonymous: bool = False


class GuestJoinResponse(BaseModel):
    session_id: uuid.UUID
    participant_id: uuid.UUID
    participant_ref: str
    token: str
    display_name: str | None
    anon: bool
