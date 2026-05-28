# Supabase Auth Sign-Up Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace instructor credential handling with Supabase Auth, add approval-gated instructor sign-up, and provide local Supabase Studio/Auth services without changing audience guest auth.

**Architecture:** Supabase Auth owns instructor passwords, access tokens, refresh tokens, and sign-up. SLAIDES keeps `app_user` as the authorization profile with workspace, role, and approval status; protected application routes require an approved local profile. Existing guest tokens remain custom SLAIDES JWTs and continue to flow through `current_guest`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, HTTPX, PyJWT for legacy guest JWTs, Vue 3, Pinia, Vite, Vitest, Supabase CLI local stack.

---

## File Structure

- Modify `apps/api/src/slaides/db/models.py`: add Supabase link and approval fields to `AppUser`.
- Create `apps/api/migrations/versions/0008_supabase_auth_approval.py`: add `supabase_user_id`, `approval_status`, `approved_at`.
- Modify `apps/api/src/slaides/settings.py`: add Supabase Auth URL/key/issuer settings.
- Modify `apps/api/src/slaides/auth/schemas.py`: add signup request and approval fields to auth responses.
- Create `apps/api/src/slaides/auth/supabase.py`: small HTTP client wrapper around Supabase Auth endpoints.
- Modify `apps/api/src/slaides/auth/service.py`: keep guest JWT helpers, add Supabase profile sync helpers, remove instructor password responsibility from router.
- Modify `apps/api/src/slaides/auth/deps.py`: accept Supabase instructor bearer tokens and legacy guest tokens; block pending/rejected users for application dependencies.
- Modify `apps/api/src/slaides/auth/router.py`: implement signup/signin/refresh via Supabase Auth; keep guest join unchanged.
- Modify `apps/api/scripts/seed.py`: ensure demo user exists in Supabase Auth when configured and local row is approved.
- Create `apps/api/scripts/approve_user.py`: approve a pending instructor by email for local operations.
- Modify `apps/api/tests/conftest.py`: install a fake Supabase Auth client in tests.
- Modify `apps/api/tests/test_auth.py`: cover signup pending, signin pending, approved access, refresh, and guest auth stability.
- Modify `apps/web/src/api/types.ts`: add `approval_status`.
- Modify `apps/web/src/api/auth.ts`: add `signUp`.
- Modify `apps/web/src/stores/auth.ts`: track pending approval and support sign-up.
- Modify `apps/web/src/router.ts`: block pending users from protected instructor routes.
- Modify `apps/web/src/pages/Signin.vue`: add instructor sign-in/sign-up segmented UI and pending approval state.
- Create `apps/web/tests/auth-store.test.ts`: cover sign-up pending state and pending route behavior at store level.
- Modify `.env.example`: document Supabase settings.
- Create `supabase/config.toml`: local Supabase CLI service config.
- Modify `Makefile`: add `supabase-up`, `supabase-down`, `supabase-status`, and make `up` start Supabase plus Redis.
- Modify `docs/HANDOFF.md`: update current auth state and local startup notes.

## Task 1: Database Model And Migration

**Files:**
- Modify: `apps/api/src/slaides/db/models.py`
- Create: `apps/api/migrations/versions/0008_supabase_auth_approval.py`
- Test: `apps/api/tests/test_auth.py`

- [ ] **Step 1: Write failing backend test for pending local user blocking workspace**

Add this test to `apps/api/tests/test_auth.py`:

```python
async def test_pending_signed_in_user_cannot_access_workspace(client, fake_supabase_auth):
    fake_supabase_auth.add_user(
        email="pending@example.com",
        password="secret123",
        user_id="11111111-1111-1111-1111-111111111111",
    )
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "pending@example.com", "password": "secret123", "display_name": "Pending User"},
    )
    assert signup.status_code == 200, signup.text
    body = signup.json()
    assert body["user"]["approval_status"] == "pending"

    workspace = await client.get(
        "/api/v1/workspace",
        headers={"Authorization": f"Bearer {body['access']}"},
    )
    assert workspace.status_code == 403
    assert workspace.json()["detail"] == "account pending approval"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py::test_pending_signed_in_user_cannot_access_workspace -v
```

Expected: FAIL because `/auth/signup` does not exist or `approval_status` is not present.

- [ ] **Step 3: Add model fields**

In `apps/api/src/slaides/db/models.py`, update imports:

```python
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
```

Then update `AppUser`:

```python
class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspace.id"), nullable=False)
    supabase_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(40), default="instructor")
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False, default="approved")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Add migration**

Create `apps/api/migrations/versions/0008_supabase_auth_approval.py`:

```python
"""add supabase auth link and approval state

Revision ID: 0008_supabase_auth_approval
Revises: 0007_session_slide_theme_default
Create Date: 2026-05-21

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_supabase_auth_approval"
down_revision = "0007_session_slide_theme_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.add_column(sa.Column("supabase_user_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "approval_status",
                sa.String(length=40),
                nullable=False,
                server_default="approved",
            )
        )
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_app_user_supabase_user_id", ["supabase_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.drop_constraint("uq_app_user_supabase_user_id", type_="unique")
        batch.drop_column("approved_at")
        batch.drop_column("approval_status")
        batch.drop_column("supabase_user_id")
```

- [ ] **Step 5: Run model/migration tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py::test_pending_signed_in_user_cannot_access_workspace -v
```

Expected: still FAIL because auth behavior is not implemented yet, but schema-related errors should be gone.

## Task 2: Supabase Auth Client And Test Fake

**Files:**
- Modify: `apps/api/src/slaides/settings.py`
- Create: `apps/api/src/slaides/auth/supabase.py`
- Modify: `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_auth.py`

- [ ] **Step 1: Write failing test for approved Supabase sign-in**

Add to `apps/api/tests/test_auth.py`:

```python
async def test_approved_supabase_user_can_sign_in_and_access_workspace(client, seeded_user, fake_supabase_auth):
    fake_supabase_auth.add_user(
        email=seeded_user["email"],
        password=seeded_user["password"],
        user_id=str(seeded_user["supabase_user_id"]),
    )

    signin = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )
    assert signin.status_code == 200, signin.text
    body = signin.json()
    assert body["user"]["approval_status"] == "approved"
    assert body["access"].startswith("sb-access:")
    assert body["refresh"].startswith("sb-refresh:")

    workspace = await client.get(
        "/api/v1/workspace",
        headers={"Authorization": f"Bearer {body['access']}"},
    )
    assert workspace.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py::test_approved_supabase_user_can_sign_in_and_access_workspace -v
```

Expected: FAIL because no `fake_supabase_auth` fixture or Supabase client exists.

- [ ] **Step 3: Add settings**

In `apps/api/src/slaides/settings.py`, add:

```python
    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_issuer: str = "http://localhost:54321/auth/v1"
    supabase_auth_verify_via_server: bool = True
```

- [ ] **Step 4: Create Supabase auth wrapper**

Create `apps/api/src/slaides/auth/supabase.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

from ..settings import get_settings


@dataclass
class SupabaseSession:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class SupabaseAuthClient:
    async def sign_up(self, email: str, password: str, display_name: str | None) -> SupabaseSession:
        payload: dict[str, Any] = {
            "email": email,
            "password": password,
            "data": {"display_name": display_name} if display_name else {},
        }
        return await self._request_session("POST", "/signup", payload)

    async def sign_in(self, email: str, password: str) -> SupabaseSession:
        return await self._request_session(
            "POST",
            "/token?grant_type=password",
            {"email": email, "password": password},
        )

    async def refresh(self, refresh_token: str) -> SupabaseSession:
        return await self._request_session(
            "POST",
            "/token?grant_type=refresh_token",
            {"refresh_token": refresh_token},
        )

    async def get_user(self, access_token: str) -> tuple[str, str]:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
        if res.status_code == 401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        if not res.is_success:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable")
        body = res.json()
        return str(body["id"]), str(body["email"]).lower()

    async def _request_session(self, method: str, path: str, payload: dict[str, Any]) -> SupabaseSession:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.request(
                method,
                f"{settings.supabase_url.rstrip('/')}/auth/v1{path}",
                headers={"apikey": settings.supabase_anon_key, "Content-Type": "application/json"},
                json=payload,
            )
        if res.status_code in {400, 401, 422}:
            detail = res.json().get("msg") if res.headers.get("content-type", "").startswith("application/json") else None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail or "bad credentials")
        if not res.is_success:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable")
        body = res.json()
        user = body.get("user") or {}
        return SupabaseSession(
            access_token=body.get("access_token") or "",
            refresh_token=body.get("refresh_token") or "",
            user_id=str(user.get("id") or ""),
            email=str(user.get("email") or "").lower(),
        )


_client: SupabaseAuthClient = SupabaseAuthClient()


def get_supabase_auth() -> SupabaseAuthClient:
    return _client


def set_supabase_auth_for_tests(client: SupabaseAuthClient) -> None:
    global _client
    _client = client
```

- [ ] **Step 5: Add test fake fixture**

In `apps/api/tests/conftest.py`, add after imports:

```python
from dataclasses import dataclass
from slaides.auth import supabase as supabase_auth  # noqa: E402


@dataclass
class FakeSupabaseUser:
    email: str
    password: str
    user_id: str


class FakeSupabaseAuth:
    def __init__(self) -> None:
        self.users: dict[str, FakeSupabaseUser] = {}
        self.tokens: dict[str, FakeSupabaseUser] = {}

    def add_user(self, email: str, password: str, user_id: str) -> None:
        self.users[email.lower()] = FakeSupabaseUser(email.lower(), password, user_id)

    async def sign_up(self, email: str, password: str, display_name: str | None):
        self.add_user(email, password, user_id=str(uuid.uuid4()))
        return self._session(self.users[email.lower()])

    async def sign_in(self, email: str, password: str):
        user = self.users.get(email.lower())
        if user is None or user.password != password:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="bad credentials")
        return self._session(user)

    async def refresh(self, refresh_token: str):
        user = self.tokens[refresh_token]
        return self._session(user)

    async def get_user(self, access_token: str):
        user = self.tokens[access_token]
        return user.user_id, user.email

    def _session(self, user: FakeSupabaseUser):
        access = f"sb-access:{user.user_id}:{uuid.uuid4()}"
        refresh = f"sb-refresh:{user.user_id}:{uuid.uuid4()}"
        self.tokens[access] = user
        self.tokens[refresh] = user
        return supabase_auth.SupabaseSession(access, refresh, user.user_id, user.email)
```

Add fixture:

```python
@pytest_asyncio.fixture
async def fake_supabase_auth():
    fake = FakeSupabaseAuth()
    supabase_auth.set_supabase_auth_for_tests(fake)  # type: ignore[arg-type]
    try:
        yield fake
    finally:
        supabase_auth.set_supabase_auth_for_tests(supabase_auth.SupabaseAuthClient())
```

- [ ] **Step 6: Update `seeded_user` fixture with Supabase id**

In `apps/api/tests/conftest.py`, set a stable UUID:

```python
supabase_user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
user = models.AppUser(
    workspace_id=ws.id,
    supabase_user_id=supabase_user_id,
    email="alice@example.com",
    display_name="Alice",
    password_hash=hash_password("hunter2"),
    role="owner",
    approval_status="approved",
)
```

Return it:

```python
"supabase_user_id": supabase_user_id,
```

- [ ] **Step 7: Run targeted test**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py::test_approved_supabase_user_can_sign_in_and_access_workspace -v
```

Expected: still FAIL until router/dependency integration is implemented.

## Task 3: Auth Router, Dependencies, And Service Sync

**Files:**
- Modify: `apps/api/src/slaides/auth/schemas.py`
- Modify: `apps/api/src/slaides/auth/service.py`
- Modify: `apps/api/src/slaides/auth/deps.py`
- Modify: `apps/api/src/slaides/auth/router.py`
- Test: `apps/api/tests/test_auth.py`

- [ ] **Step 1: Extend schemas**

In `apps/api/src/slaides/auth/schemas.py`, add:

```python
class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
```

Update `UserOut`:

```python
class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    role: str
    approval_status: str
```

- [ ] **Step 2: Add service helpers**

In `apps/api/src/slaides/auth/service.py`, keep `issue_guest` and `decode` unchanged for guest tokens. Add:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppUser, Workspace


async def get_or_create_pending_workspace(session: AsyncSession) -> Workspace:
    row = (await session.execute(select(Workspace).where(Workspace.name == "Pending Instructors"))).scalar_one_or_none()
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
        user = (await session.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
    if user is None:
        pending_ws = await get_or_create_pending_workspace(session)
        user = AppUser(
            workspace_id=pending_ws.id,
            supabase_user_id=supabase_user_id,
            email=email,
            display_name=display_name,
            password_hash="",
            role="instructor",
            approval_status=default_status,
        )
        session.add(user)
    else:
        user.supabase_user_id = supabase_user_id
        if display_name and not user.display_name:
            user.display_name = display_name
    await session.flush()
    return user
```

- [ ] **Step 3: Split auth dependencies**

In `apps/api/src/slaides/auth/deps.py`, add:

```python
from .supabase import get_supabase_auth
```

Replace instructor token handling with:

```python
async def current_user_profile(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> AppUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    user_id, email = await get_supabase_auth().get_user(creds.credentials)
    try:
        supabase_user_id = uuid.UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject") from exc
    user = (
        await session.execute(select(AppUser).where(AppUser.supabase_user_id == supabase_user_id))
    ).scalar_one_or_none()
    if user is None:
        user = (await session.execute(select(AppUser).where(AppUser.email == email.lower()))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    if user.supabase_user_id is None:
        user.supabase_user_id = supabase_user_id
        await session.flush()
    return user


async def current_user(user: AppUser = Depends(current_user_profile)) -> AppUser:
    if user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account pending approval")
    if user.approval_status == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account rejected")
    return user
```

Leave `current_guest` using `service.decode()` unchanged. Update `current_principal` so it first tries guest tokens when `service.decode()` returns `kind == "guest"`, otherwise falls back to Supabase `get_user()` and approved `AppUser`.

- [ ] **Step 4: Update router**

In `apps/api/src/slaides/auth/router.py`, import:

```python
from .supabase import get_supabase_auth
```

Update `_user_out`:

```python
def _user_out(user: AppUser) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        approval_status=user.approval_status,
    )
```

Add signup endpoint:

```python
@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignUpRequest, session: AsyncSession = Depends(db_session)) -> AuthResponse:
    email = body.email.lower().strip()
    sb = await get_supabase_auth().sign_up(email, body.password, body.display_name)
    user = await service.sync_supabase_user(
        session,
        supabase_user_id=uuid.UUID(sb.user_id),
        email=sb.email or email,
        display_name=body.display_name,
        default_status="pending",
    )
    user.approval_status = "pending"
    await session.commit()
    return AuthResponse(access=sb.access_token, refresh=sb.refresh_token, user=_user_out(user))
```

Replace signin:

```python
@router.post("/signin", response_model=AuthResponse)
async def signin(body: SignInRequest, session: AsyncSession = Depends(db_session)) -> AuthResponse:
    email = body.email.lower().strip()
    sb = await get_supabase_auth().sign_in(email, body.password)
    user = await service.sync_supabase_user(
        session,
        supabase_user_id=uuid.UUID(sb.user_id),
        email=sb.email or email,
        display_name=None,
        default_status="pending",
    )
    await session.commit()
    return AuthResponse(access=sb.access_token, refresh=sb.refresh_token, user=_user_out(user))
```

Replace refresh:

```python
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
```

Change `/me` to use `current_user_profile` so pending users can see their state:

```python
@router.get("/me", response_model=UserOut)
async def me(user: AppUser = Depends(current_user_profile)) -> UserOut:
    return _user_out(user)
```

- [ ] **Step 5: Update imports in router**

Ensure `SignUpRequest` and `current_user_profile` are imported:

```python
from .deps import current_user_profile
from .schemas import AuthResponse, GuestJoinRequest, GuestJoinResponse, RefreshRequest, SignInRequest, SignUpRequest, UserOut
```

- [ ] **Step 6: Run auth tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py -v
```

Expected: PASS for `test_pending_signed_in_user_cannot_access_workspace`, `test_approved_supabase_user_can_sign_in_and_access_workspace`, existing bad password, refresh, `/me`, and workspace tests.

## Task 4: Seed, Approval Script, And Local Supabase Services

**Files:**
- Modify: `apps/api/scripts/seed.py`
- Create: `apps/api/scripts/approve_user.py`
- Modify: `.env.example`
- Create: `supabase/config.toml`
- Modify: `Makefile`
- Test: manual commands plus backend tests

- [ ] **Step 1: Add Supabase env example**

Append to `.env.example`:

```bash
# Backend (apps/api)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres

# Supabase Auth / local Studio
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_ISSUER=http://localhost:54321/auth/v1
SUPABASE_AUTH_VERIFY_VIA_SERVER=true
```

This makes Supabase local Postgres the SLAIDES application database. After `make migrate`, Studio can inspect and edit `app_user.approval_status`.

- [ ] **Step 2: Add Supabase CLI config**

Create `supabase/config.toml`:

```toml
project_id = "slaides"

[api]
enabled = true
port = 54321
schemas = ["public", "graphql_public"]
extra_search_path = ["public", "extensions"]
max_rows = 1000

[db]
port = 54322
shadow_port = 54320
major_version = 16

[studio]
enabled = true
port = 54323
api_url = "http://127.0.0.1:54321"

[auth]
enabled = true
site_url = "http://localhost:5173"
additional_redirect_urls = ["http://localhost:5173"]
jwt_expiry = 3600
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10

[auth.email]
enable_signup = true
double_confirm_changes = true
enable_confirmations = false

[inbucket]
enabled = true
port = 54324
smtp_port = 54325
pop3_port = 54326
```

- [ ] **Step 3: Update Makefile**

Add targets:

```make
.PHONY: supabase-up supabase-down supabase-status redis-up legacy-postgres-up

supabase-up:
	supabase start

supabase-down:
	supabase stop

supabase-status:
	supabase status

redis-up:
	docker compose up -d redis

legacy-postgres-up:
	docker compose up -d postgres
```

Replace existing `up` / `down` targets with:

```make
up: supabase-up redis-up
	@echo "Supabase and Redis ready."

down:
	docker compose down
	supabase stop
```

Keep `legacy-postgres-up` only as an escape hatch for old local data. The normal `DATABASE_URL` now points at Supabase local Postgres on `54322`, so `make migrate` creates SLAIDES tables where Studio can inspect them.

- [ ] **Step 4: Update seed script for approved local row**

In `apps/api/scripts/seed.py`, stop requiring an Argon hash for local auth decisions but keep compatibility:

```python
from datetime import datetime, timezone
```

When creating the demo user, set:

```python
approval_status="approved",
approved_at=datetime.now(timezone.utc),
```

If user already exists, reconcile:

```python
user.approval_status = "approved"
if user.approved_at is None:
    user.approved_at = datetime.now(timezone.utc)
```

- [ ] **Step 5: Create approval script**

Create `apps/api/scripts/approve_user.py`:

```python
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from slaides.db.base import get_session_factory
from slaides.db.models import AppUser


async def approve(email: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(AppUser).where(AppUser.email == email.lower().strip()))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"user not found: {email}")
        user.approval_status = "approved"
        user.approved_at = datetime.now(timezone.utc)
        await session.commit()
        print(f"approved {user.email}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    args = parser.parse_args()
    asyncio.run(approve(args.email))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
cd apps/api && uv run pytest tests/test_auth.py -v
```

Expected: PASS.

- [ ] **Step 7: Check Supabase CLI availability**

Run:

```bash
supabase --version
```

Expected: prints a Supabase CLI version. If missing, install the CLI before running `make up`.

## Task 5: Frontend API And Auth Store

**Files:**
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/auth.ts`
- Modify: `apps/web/src/stores/auth.ts`
- Create: `apps/web/tests/auth-store.test.ts`

- [ ] **Step 1: Write failing store tests**

Create `apps/web/tests/auth-store.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "../src/stores/auth";
import { authApi } from "../src/api/auth";

vi.mock("../src/api/auth", () => ({
  authApi: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    me: vi.fn(),
  },
}));

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("stores pending approval state after signup", async () => {
    vi.mocked(authApi.signUp).mockResolvedValue({
      access: "access",
      refresh: "refresh",
      user: {
        id: "u1",
        email: "pending@example.com",
        display_name: "Pending",
        role: "instructor",
        approval_status: "pending",
      },
    });

    const auth = useAuthStore();
    await auth.signUp("pending@example.com", "secret123", "Pending");

    expect(auth.isSignedIn).toBe(true);
    expect(auth.isApproved).toBe(false);
    expect(auth.approvalStatus).toBe("pending");
  });

  it("marks approved users as approved after sign in", async () => {
    vi.mocked(authApi.signIn).mockResolvedValue({
      access: "access",
      refresh: "refresh",
      user: {
        id: "u1",
        email: "you@studio.press",
        display_name: "Field Notes",
        role: "owner",
        approval_status: "approved",
      },
    });

    const auth = useAuthStore();
    await auth.signIn("you@studio.press", "slaides");

    expect(auth.isSignedIn).toBe(true);
    expect(auth.isApproved).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/web && npm test -- auth-store.test.ts
```

Expected: FAIL because `signUp`, `approval_status`, and `isApproved` do not exist.

- [ ] **Step 3: Update types**

In `apps/web/src/api/types.ts`, update `User`:

```ts
export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  approval_status: ApprovalStatus;
}
```

- [ ] **Step 4: Add signup API**

In `apps/web/src/api/auth.ts`, add:

```ts
  signUp: (email: string, password: string, displayName: string) =>
    api<AuthResponse>("/auth/signup", {
      method: "POST",
      body: { email, password, display_name: displayName },
    }),
```

- [ ] **Step 5: Update auth store**

In `apps/web/src/stores/auth.ts`, add computed values:

```ts
  const approvalStatus = computed(() => user.value?.approval_status ?? null);
  const isApproved = computed(() => approvalStatus.value === "approved");
```

Add signup:

```ts
  async function signUp(email: string, password: string, displayName: string) {
    busy.value = true;
    error.value = null;
    try {
      const res = await authApi.signUp(email, password, displayName);
      access.value = res.access;
      refresh.value = res.refresh;
      user.value = res.user;
      save({ access: res.access, refresh: res.refresh, user: res.user });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sign-up failed";
      error.value = msg;
      throw e;
    } finally {
      busy.value = false;
    }
  }
```

Return:

```ts
return { access, refresh, user, error, busy, isSignedIn, approvalStatus, isApproved, signIn, signUp, signOut };
```

- [ ] **Step 6: Run store tests**

Run:

```bash
cd apps/web && npm test -- auth-store.test.ts
```

Expected: PASS.

## Task 6: Frontend Sign-Up UI And Pending Route Guard

**Files:**
- Modify: `apps/web/src/router.ts`
- Modify: `apps/web/src/pages/Signin.vue`
- Test: `apps/web/tests/auth-store.test.ts`

- [ ] **Step 1: Add route guard for pending users**

In `apps/web/src/router.ts`, update guard:

```ts
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.isSignedIn) {
    return { name: "signin", query: { next: to.fullPath } };
  }
  if (to.meta.requiresAuth && auth.isSignedIn && !auth.isApproved) {
    return { name: "signin", query: { pending: "1" } };
  }
  if (to.name === "signin" && auth.isSignedIn && auth.isApproved) {
    return { name: "workspace" };
  }
});
```

- [ ] **Step 2: Update Signin script**

In `apps/web/src/pages/Signin.vue`, add:

```ts
const instructorMode = ref<"signin" | "signup">("signin");
const confirmPassword = ref("");
const pendingNotice = ref(false);
```

Replace `submitInstructor` with:

```ts
async function submitInstructor(e: Event) {
  e.preventDefault();
  try {
    if (instructorMode.value === "signup") {
      if (password.value !== confirmPassword.value) {
        auth.error = "Passwords do not match.";
        return;
      }
      await auth.signUp(email.value, password.value, name.value);
    } else {
      await auth.signIn(email.value, password.value);
    }
    if (!auth.isApproved) {
      pendingNotice.value = true;
      return;
    }
    await router.push("/workspace");
  } catch {
    // error is in auth.error
  }
}
```

In `setMode`, reset:

```ts
pendingNotice.value = false;
```

- [ ] **Step 3: Update instructor template**

Inside the instructor form, add a secondary switch above fields:

```vue
<div class="auth-subswitch">
  <button type="button" :class="{ active: instructorMode === 'signin' }" @click="instructorMode = 'signin'">
    Sign in
  </button>
  <button type="button" :class="{ active: instructorMode === 'signup' }" @click="instructorMode = 'signup'">
    Sign up
  </button>
</div>
```

Change heading:

```vue
<div class="t-h3" :style="{ marginBottom: '24px' }">
  {{ instructorMode === "signin" ? "Welcome back." : "Request instructor access." }}
</div>
```

Add display name input only for signup before password:

```vue
<div v-if="instructorMode === 'signup'" :style="{ marginBottom: '14px' }">
  <label class="field-label">Display name</label>
  <input class="input" placeholder="Your name" v-model="name" required />
</div>
```

Add confirm password input:

```vue
<div v-if="instructorMode === 'signup'" :style="{ marginBottom: '18px' }">
  <label class="field-label">Confirm password</label>
  <input class="input" type="password" placeholder="••••••••" v-model="confirmPassword" required />
</div>
```

Add pending notice above submit:

```vue
<div v-if="pendingNotice || auth.approvalStatus === 'pending'" class="approval-note">
  Your instructor account is waiting for approval. You can sign in, but workspace access stays locked until an admin approves you.
</div>
```

Change submit label:

```vue
{{ auth.busy ? "Working…" : instructorMode === "signin" ? "Sign in" : "Sign up" }}
```

Add scoped styles at the end:

```vue
<style scoped>
.auth-subswitch {
  display: flex;
  gap: 4px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 3px;
  background: var(--paper);
  margin-bottom: 18px;
}
.auth-subswitch button {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--ink-soft);
  border-radius: 6px;
  padding: 7px 10px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.auth-subswitch button.active {
  background: var(--ink);
  color: var(--paper);
}
.approval-note {
  margin-bottom: 14px;
  border: 1px solid var(--accent);
  border-radius: var(--r-md);
  padding: 10px 12px;
  background: var(--accent-soft);
  color: var(--ink);
  font-size: 12px;
  line-height: 1.5;
}
</style>
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd apps/web && npm test -- auth-store.test.ts
```

Expected: PASS.

## Task 7: Verification And Documentation

**Files:**
- Modify: `docs/HANDOFF.md`
- Test: backend, frontend, build, local Supabase status

- [ ] **Step 1: Update handoff**

In `docs/HANDOFF.md`, update Current state and Quick start to mention:

```markdown
Instructor credentials are now handled by Supabase Auth. New instructor sign-ups create pending local `app_user` profiles and are blocked from workspace routes until `approval_status='approved'`. Audience guest join still uses the existing session-scoped SLAIDES guest token. Local Supabase Studio/Auth/Postgres services run via `make up`; Studio is at `http://localhost:54323`, Supabase API/Auth is at `http://localhost:54321`, and SLAIDES migrations run against Supabase Postgres at `localhost:54322`.
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
cd apps/api && uv run pytest
```

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd apps/web && npm test
```

Expected: all frontend tests pass.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd apps/web && npm run build
```

Expected: `vue-tsc --noEmit` and Vite build pass.

- [ ] **Step 5: Start Supabase local services**

Run:

```bash
make up
make supabase-status
```

Expected: output includes API URL `http://127.0.0.1:54321` and Studio URL `http://127.0.0.1:54323`.

- [ ] **Step 6: Start app services**

Run:

```bash
make up
make migrate
make seed
make api
make web
```

Expected: Supabase API/Auth on `http://localhost:54321`, Supabase Studio on `http://localhost:54323`, SLAIDES API on `http://localhost:8000`, and web on `http://localhost:5173`.

- [ ] **Step 7: Manual browser smoke**

In the browser:

1. Open `http://localhost:5173/signin`.
2. Sign in as `you@studio.press / slaides`; expected: workspace opens.
3. Sign out.
4. Sign up as `pending@example.com / secret123`; expected: pending approval note, no workspace route.
5. Run `cd apps/api && uv run python -m scripts.approve_user pending@example.com`.
6. Sign in as `pending@example.com / secret123`; expected: workspace opens.
7. Start a live session and join as audience; expected: guest join still works.

## Self-Review Notes

- Spec coverage: signup, approval gate, Supabase Auth delegation, local Supabase Studio, unchanged guest tokens, and verification are covered.
- Scope control: this plan does not add admin UI, RLS migration, social auth, reset password, or Supabase PostgREST data access.
- Type consistency: backend uses `approval_status`; frontend uses `ApprovalStatus`; auth response keeps `access`, `refresh`, `user` for compatibility.
