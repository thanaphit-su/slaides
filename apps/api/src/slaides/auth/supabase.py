from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, status

from ..settings import get_settings


MISSING_SESSION_DETAIL = "supabase auth response missing session"
_USER_CACHE_MAX = 1024
# Cap the local-JWT cache TTL so a Supabase admin who disables a user mid-
# session sees the change land within the hour rather than for the full
# token lifetime (Supabase access tokens default to 1h anyway).
_LOCAL_JWT_CACHE_TTL_CAP = 3600


@dataclass
class SupabaseSession:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


class SupabaseAuthClient:
    def __init__(self) -> None:
        # token -> (user_id, email, expires_at_monotonic)
        self._user_cache: dict[str, tuple[str, str, float]] = {}
        # Lazy-opened, shared across calls so we get HTTP keep-alive and
        # don't churn sockets on every Supabase round-trip. Closed in
        # aclose() during app shutdown.
        self._http: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _cache_get(self, token: str) -> tuple[str, str] | None:
        entry = self._user_cache.get(token)
        if entry is None:
            return None
        user_id, email, expires_at = entry
        if expires_at <= time.monotonic():
            self._user_cache.pop(token, None)
            return None
        return user_id, email

    def _cache_put(self, token: str, user_id: str, email: str, ttl: int) -> None:
        if ttl <= 0:
            return
        self._user_cache[token] = (user_id, email, time.monotonic() + ttl)
        while len(self._user_cache) > _USER_CACHE_MAX:
            oldest = next(iter(self._user_cache))
            self._user_cache.pop(oldest, None)

    def _cache_evict(self, token: str) -> None:
        self._user_cache.pop(token, None)

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
        cached = self._cache_get(access_token)
        if cached is not None:
            return cached

        # Fast path: verify the JWT locally with Supabase's HS256 secret.
        # Eliminates the per-request round-trip to /auth/v1/user that was
        # the dominant source of intermittent 502s on long-lived sessions
        # — any flake on that round-trip (timeout, rate-limit, 5xx)
        # surfaced as `502 supabase auth unavailable` even though the
        # token was still perfectly valid.
        settings = get_settings()
        if settings.supabase_jwt_secret:
            user_id, email, ttl = _verify_local_jwt(access_token, settings.supabase_jwt_secret)
            if user_id and email:
                self._cache_put(access_token, user_id, email, min(ttl, _LOCAL_JWT_CACHE_TTL_CAP))
                return user_id, email

        # Fallback: legacy remote path. Kept so deployments without a
        # SUPABASE_JWT_SECRET (and the test env's FakeSupabaseAuth) still
        # work — the test fakes override `_remote_get_user` and leave the
        # JWT secret unset, so this branch is what unit tests exercise.
        try:
            user_id, email = await self._remote_get_user(access_token)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                self._cache_evict(access_token)
            raise
        self._cache_put(access_token, user_id, email, settings.supabase_user_cache_ttl)
        return user_id, email

    async def _remote_get_user(self, access_token: str) -> tuple[str, str]:
        settings = get_settings()
        try:
            res = await self._http_client().get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable"
            ) from exc
        if res.status_code == 401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        if not res.is_success:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable")
        body = _json_body(res)
        user_id = body.get("id")
        email = body.get("email")
        if not user_id or not email:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth response missing user")
        return str(user_id), str(email).lower()

    async def _request_session(self, method: str, path: str, payload: dict[str, Any]) -> SupabaseSession:
        settings = get_settings()
        try:
            res = await self._http_client().request(
                method,
                f"{settings.supabase_url.rstrip('/')}/auth/v1{path}",
                headers={"apikey": settings.supabase_anon_key, "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable"
            ) from exc
        if res.status_code in {400, 401, 422}:
            detail = _auth_error_detail(res)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail or "bad credentials")
        if not res.is_success:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="supabase auth unavailable")
        body = _json_body(res)
        user = body.get("user") or {}
        if not isinstance(user, dict):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MISSING_SESSION_DETAIL)
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")
        user_id = user.get("id")
        email = user.get("email")
        if not access_token or not refresh_token or not user_id or not email:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=MISSING_SESSION_DETAIL)
        return SupabaseSession(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            user_id=str(user_id),
            email=str(email).lower(),
        )


def _verify_local_jwt(access_token: str, secret: str) -> tuple[str, str, int]:
    """Decode + verify a Supabase access token locally.

    Returns (user_id, email, ttl_seconds). On expired/invalid signature
    raises HTTPException(401). Returns ("", "", 0) when the token decoded
    cleanly but lacks the email claim, or when the token uses a signing
    algorithm this local verifier does not support. The caller then falls
    back to the remote Supabase /user path for those edge cases.
    """
    try:
        header = jwt.get_unverified_header(access_token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    if header.get("alg") != "HS256":
        return "", "", 0
    try:
        payload = jwt.decode(
            access_token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    user_id = str(payload.get("sub") or "")
    email = str(payload.get("email") or "").lower()
    if not user_id or not email:
        return "", "", 0
    ttl = max(0, int(payload["exp"]) - int(time.time()))
    return user_id, email, ttl


def _json_body(res: httpx.Response) -> dict[str, Any]:
    if not res.headers.get("content-type", "").startswith("application/json"):
        return {}
    try:
        body = res.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _auth_error_detail(res: httpx.Response) -> str | None:
    body = _json_body(res)
    for key in ("msg", "message", "error_description", "error"):
        value = body.get(key)
        if value:
            return str(value)
    return None


_client: SupabaseAuthClient = SupabaseAuthClient()


def get_supabase_auth() -> SupabaseAuthClient:
    return _client


def set_supabase_auth_for_tests(client: SupabaseAuthClient) -> None:
    global _client
    _client = client
