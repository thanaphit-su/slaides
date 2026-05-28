from __future__ import annotations

import uuid

from slaides.db import models
from slaides.db.base import get_session_factory
from slaides.sessions.ws import _supabase_host_from_token


async def test_signin_success(client, seeded_user):
    res = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == seeded_user["email"]
    assert body["access"]
    assert body["refresh"]


async def test_signin_bad_password(client, seeded_user):
    res = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": "wrong"},
    )
    assert res.status_code == 401


async def test_refresh_issues_new_pair(client, seeded_user):
    signin = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )
    refresh_token = signin.json()["refresh"]
    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    body = res.json()
    assert body["access"]
    assert body["refresh"]


async def test_me_requires_auth(client):
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


async def test_me_returns_user(client, auth_headers, seeded_user):
    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == seeded_user["email"]


async def test_workspace_endpoint(client, auth_headers):
    res = await client.get("/api/v1/workspace", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Test Workspace"


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


async def test_supabase_401_does_not_fallback_to_legacy_signin(client, seeded_user, fake_supabase_auth):
    fake_supabase_auth.users.pop(seeded_user["email"], None)

    res = await client.post(
        "/api/v1/auth/signin",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )

    assert res.status_code == 401


async def test_unrecognized_refresh_token_returns_401(client, seeded_user, fake_supabase_auth):
    res = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )

    assert res.status_code == 401


async def test_unrecognized_bearer_token_returns_401(client, seeded_user, fake_supabase_auth):
    res = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert res.status_code == 401


async def test_unrecognized_token_does_not_authenticate_ws_host(seeded_user, fake_supabase_auth):
    factory = get_session_factory()
    async with factory() as session:
        row = models.Session(
            deck_id=uuid.uuid4(),
            owner_id=seeded_user["user_id"],
            workspace_id=seeded_user["workspace_id"],
            code="SLD-WS-401",
            salt="salt",
        )
        session.add(row)
        await session.flush()

        user = await _supabase_host_from_token("not-a-real-token", row, session)

    assert user is None


async def test_repeated_me_calls_hit_supabase_once(client, auth_headers, fake_supabase_auth):
    start = fake_supabase_auth.remote_get_user_calls
    for _ in range(3):
        res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200

    assert fake_supabase_auth.remote_get_user_calls - start == 1


async def test_cache_expiry_forces_fresh_lookup(client, auth_headers, fake_supabase_auth):
    start = fake_supabase_auth.remote_get_user_calls
    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200

    # Expire every cached entry without waiting on real time.
    fake_supabase_auth._user_cache.clear()

    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert fake_supabase_auth.remote_get_user_calls - start == 2


async def test_supabase_401_evicts_cached_entry(client, auth_headers, fake_supabase_auth, seeded_user):
    # Warm the cache.
    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    assert token in fake_supabase_auth._user_cache

    # Revoke the user upstream and force the next request to re-hit the
    # remote (e.g. cache expired). The 401 from upstream must propagate AND
    # evict any prior cache entry so a still-valid token from a different
    # user can never be served from a stale slot.
    fake_supabase_auth.users.pop(seeded_user["email"], None)
    fake_supabase_auth._user_cache.clear()

    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 401
    assert token not in fake_supabase_auth._user_cache


# ---- Local JWT verification (Supabase access tokens) ----
#
# These tests cover the fast path that eliminated the long-session 502s:
# when SUPABASE_JWT_SECRET is configured, `get_user` decodes the token
# locally instead of round-tripping to /auth/v1/user. We use a stock
# `SupabaseAuthClient` (not the FakeSupabaseAuth subclass) and verify the
# remote path is not invoked when the local branch succeeds.


def _supabase_jwt(secret: str, *, sub: str, email: str, exp_offset: int = 3600) -> str:
    import time as _t

    import jwt as _jwt

    return _jwt.encode(
        {
            "sub": sub,
            "email": email,
            "aud": "authenticated",
            "exp": int(_t.time()) + exp_offset,
            "iat": int(_t.time()),
        },
        secret,
        algorithm="HS256",
    )


async def test_local_jwt_branch_short_circuits_remote_call():
    """When SUPABASE_JWT_SECRET is configured and the token verifies, the
    remote /auth/v1/user call must NOT happen — that's the whole point of
    the change."""
    from slaides.auth.supabase import SupabaseAuthClient
    from slaides.settings import get_settings

    secret = "x" * 40
    settings = get_settings()
    prior = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = secret
    try:
        called = {"n": 0}

        class CountingClient(SupabaseAuthClient):
            async def _remote_get_user(self, access_token: str) -> tuple[str, str]:  # type: ignore[override]
                called["n"] += 1
                return "remote-uid", "remote@example.com"

        client = CountingClient()
        token = _supabase_jwt(secret, sub="11111111-1111-1111-1111-111111111111", email="Alice@Example.com")
        uid, email = await client.get_user(token)
        assert uid == "11111111-1111-1111-1111-111111111111"
        assert email == "alice@example.com"  # normalized to lowercase
        assert called["n"] == 0
        # Cached for the token's whole lifetime — second call still no remote.
        await client.get_user(token)
        assert called["n"] == 0
    finally:
        settings.supabase_jwt_secret = prior


async def test_local_jwt_expired_returns_401_not_502():
    """An expired Supabase access token must surface as 401 (so the
    frontend's refresh path engages) and never as 502."""
    from fastapi import HTTPException

    from slaides.auth.supabase import SupabaseAuthClient
    from slaides.settings import get_settings

    secret = "y" * 40
    settings = get_settings()
    prior = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = secret
    try:
        client = SupabaseAuthClient()
        token = _supabase_jwt(secret, sub="u-1", email="u@x.com", exp_offset=-60)
        try:
            await client.get_user(token)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        settings.supabase_jwt_secret = prior


async def test_local_jwt_bad_signature_returns_401():
    """A token signed with the wrong secret must be rejected as 401 —
    a malicious tampered token shouldn't reach the remote fallback."""
    from fastapi import HTTPException

    from slaides.auth.supabase import SupabaseAuthClient
    from slaides.settings import get_settings

    settings = get_settings()
    prior = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = "the-real-secret-aaaaaaaaaaaaaaaaa"
    try:
        client = SupabaseAuthClient()
        # Signed with a different secret.
        token = _supabase_jwt("wrong-secret-bbbbbbbbbbbbbbbbbbbbbb", sub="u-1", email="u@x.com")
        try:
            await client.get_user(token)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        settings.supabase_jwt_secret = prior


async def test_no_jwt_secret_configured_falls_back_to_remote():
    """When SUPABASE_JWT_SECRET is unset (legacy deployments, the test
    env), get_user must fall through to _remote_get_user as before."""
    from slaides.auth.supabase import SupabaseAuthClient
    from slaides.settings import get_settings

    settings = get_settings()
    prior = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = ""
    try:
        called = {"n": 0}

        class CountingClient(SupabaseAuthClient):
            async def _remote_get_user(self, access_token: str) -> tuple[str, str]:  # type: ignore[override]
                called["n"] += 1
                return "legacy-uid", "legacy@example.com"

        client = CountingClient()
        # Token contents don't matter; the secret isn't configured.
        uid, email = await client.get_user("opaque-token")
        assert uid == "legacy-uid"
        assert email == "legacy@example.com"
        assert called["n"] == 1
    finally:
        settings.supabase_jwt_secret = prior
