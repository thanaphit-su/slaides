from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")

from slaides.db.base import Base, get_engine, get_session_factory, reset_engine_for_tests  # noqa: E402
from slaides.db import models  # noqa: F401, E402
from slaides.auth import supabase as supabase_auth  # noqa: E402
from slaides.main import create_app  # noqa: E402
from slaides.sessions.ws import hub as _ws_hub  # noqa: E402
from slaides.llm import service as llm_service  # noqa: E402


@dataclass
class FakeSupabaseUser:
    email: str
    password: str
    user_id: str


class FakeSupabaseAuth(supabase_auth.SupabaseAuthClient):
    def __init__(self) -> None:
        super().__init__()
        self.users: dict[str, FakeSupabaseUser] = {}
        self.remote_get_user_calls: int = 0

    def add_user(self, *, email: str, password: str, user_id: str) -> None:
        lowered = email.lower()
        self.users[lowered] = FakeSupabaseUser(email=lowered, password=password, user_id=user_id)

    async def sign_up(self, email: str, password: str, display_name: str | None) -> supabase_auth.SupabaseSession:
        lowered = email.lower()
        user = self.users.get(lowered)
        if user is None:
            user = FakeSupabaseUser(email=lowered, password=password, user_id=str(uuid.uuid4()))
            self.users[lowered] = user
        return self._session(user)

    async def sign_in(self, email: str, password: str) -> supabase_auth.SupabaseSession:
        user = self.users.get(email.lower())
        if user is None or user.password != password:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad credentials")
        return self._session(user)

    async def refresh(self, refresh_token: str) -> supabase_auth.SupabaseSession:
        prefix = "sb-refresh:"
        if not refresh_token.startswith(prefix):
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        user_id = refresh_token.removeprefix(prefix)
        for user in self.users.values():
            if user.user_id == user_id:
                return self._session(user)
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    async def _remote_get_user(self, access_token: str) -> tuple[str, str]:
        self.remote_get_user_calls += 1
        prefix = "sb-access:"
        if not access_token.startswith(prefix):
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        user_id = access_token.removeprefix(prefix)
        for user in self.users.values():
            if user.user_id == user_id:
                return user.user_id, user.email
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    def _session(self, user: FakeSupabaseUser) -> supabase_auth.SupabaseSession:
        return supabase_auth.SupabaseSession(
            access_token=f"sb-access:{user.user_id}",
            refresh_token=f"sb-refresh:{user.user_id}",
            user_id=user.user_id,
            email=user.email,
        )


@pytest.fixture
def fake_supabase_auth() -> Iterator[FakeSupabaseAuth]:
    fake = FakeSupabaseAuth()
    supabase_auth.set_supabase_auth_for_tests(fake)
    try:
        yield fake
    finally:
        supabase_auth.set_supabase_auth_for_tests(supabase_auth.SupabaseAuthClient())


@pytest_asyncio.fixture
async def app_with_db():
    fd, path = tempfile.mkstemp(prefix=f"slaides-{uuid.uuid4().hex}-", suffix=".db")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{path}"
    reset_engine_for_tests(db_url)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Swap the WS hub + LLM rate limiter onto fakeredis so tests don't need a real Redis.
    import fakeredis.aioredis as _fakeredis

    fake = _fakeredis.FakeRedis(decode_responses=True)
    fake_llm = _fakeredis.FakeRedis(decode_responses=True)
    _ws_hub.set_redis(fake)
    llm_service.set_redis(fake_llm)

    app = create_app()
    try:
        yield app
    finally:
        await _ws_hub.aclose()
        try:
            await fake_llm.aclose()
        except Exception:
            pass
        llm_service.set_redis(None)
        await engine.dispose()
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest_asyncio.fixture
async def client(app_with_db) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seeded_user(app_with_db, fake_supabase_auth):
    supabase_user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_supabase_auth.add_user(
        email="alice@example.com",
        password="hunter2",
        user_id=str(supabase_user_id),
    )
    factory = get_session_factory()
    async with factory() as session:
        ws = models.Workspace(name="Test Workspace")
        session.add(ws)
        await session.flush()
        user = models.AppUser(
            workspace_id=ws.id,
            supabase_user_id=supabase_user_id,
            email="alice@example.com",
            display_name="Alice",
            role="owner",
            approval_status="approved",
            approved_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
        return {
            "email": "alice@example.com",
            "password": "hunter2",
            "workspace_id": ws.id,
            "user_id": user.id,
            "supabase_user_id": supabase_user_id,
        }


@pytest_asyncio.fixture
async def auth_headers(client, seeded_user):
    res = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access"]
    return {"Authorization": f"Bearer {token}"}
