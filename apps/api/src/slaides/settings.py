from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:54322/postgres"
    database_pool_size: int = 3
    database_max_overflow: int = 1
    database_pool_timeout: int = 10
    slaides_env: str = "development"
    jwt_secret: str = "dev-jwt-secret-change-me"
    guest_jwt_secret: str = "dev-guest-jwt-secret-change-me"
    jwt_access_ttl: int = 900
    jwt_refresh_ttl: int = 2_592_000
    cors_origins: str = "http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    session_audience_cap: int = 500
    llm_encryption_secret: str | None = None
    llm_workspace_rate_limit: int = 60
    llm_widget_user_rate_limit: int = 6
    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_issuer: str = "http://localhost:54321/auth/v1"
    # HS256 secret Supabase signs access tokens with. When set, the backend
    # verifies tokens locally instead of round-tripping to /auth/v1/user on
    # every authenticated request — that round-trip was the source of
    # intermittent 502s on long-lived sessions.
    supabase_jwt_secret: str = ""
    # Seconds to cache (access_token → user) lookups so authenticated REST
    # requests don't round-trip to Supabase on every call. 0 disables.
    # Only used by the legacy remote path; the local-JWT path caches until
    # the token's own `exp` (capped at 1h).
    supabase_user_cache_ttl: int = 60

    @model_validator(mode="after")
    def load_local_supabase_keys(self) -> Settings:
        if not self._uses_local_supabase_db():
            return self
        if self.supabase_anon_key and self.supabase_service_role_key and self.supabase_jwt_secret:
            return self
        values = _local_supabase_status_env()
        self.supabase_url = values.get("API_URL", self.supabase_url)
        self.supabase_anon_key = self.supabase_anon_key or values.get("ANON_KEY", "")
        self.supabase_service_role_key = self.supabase_service_role_key or values.get("SERVICE_ROLE_KEY", "")
        self.supabase_jwt_secret = self.supabase_jwt_secret or values.get("JWT_SECRET", "")
        return self

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> Settings:
        if self.slaides_env.strip().lower() != "production":
            return self
        unsafe: list[str] = []
        if self.jwt_secret == "dev-jwt-secret-change-me" or len(self.jwt_secret) < 32:
            unsafe.append("JWT_SECRET")
        if (
            self.guest_jwt_secret == "dev-guest-jwt-secret-change-me"
            or len(self.guest_jwt_secret) < 32
            or self.guest_jwt_secret == self.jwt_secret
        ):
            unsafe.append("GUEST_JWT_SECRET")
        if "localhost" in self.cors_origins or "127.0.0.1" in self.cors_origins:
            unsafe.append("CORS_ORIGINS")
        if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
            unsafe.append("DATABASE_URL")
        if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
            unsafe.append("REDIS_URL")
        if self.supabase_jwt_secret and len(self.supabase_jwt_secret) < 32:
            unsafe.append("SUPABASE_JWT_SECRET")
        if unsafe:
            names = ", ".join(sorted(set(unsafe)))
            raise ValueError(f"production settings are unsafe: {names}")
        return self

    def _uses_local_supabase_db(self) -> bool:
        return "localhost:54322" in self.database_url or "127.0.0.1:54322" in self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _local_supabase_status_env() -> dict[str, str]:
    values = _local_supabase_compose_env()
    if values:
        return values
    try:
        res = subprocess.run(
            ["supabase", "status", "-o", "env"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if res.returncode != 0:
        return {}
    return _parse_supabase_env(res.stdout)


def _local_supabase_compose_env() -> dict[str, str]:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[4] / "docker" / "supabase" / ".env.slaides",
        here.parents[4] / "docker" / "supabase" / ".env",
    ]
    for path in candidates:
        if path.exists():
            values = _parse_supabase_env(path.read_text())
            if values:
                return {
                    "API_URL": values.get("SUPABASE_PUBLIC_URL", "http://localhost:54321"),
                    "ANON_KEY": values.get("ANON_KEY", ""),
                    "SERVICE_ROLE_KEY": values.get("SERVICE_ROLE_KEY", ""),
                    "JWT_SECRET": values.get("JWT_SECRET", ""),
                }
    return {}


def _parse_supabase_env(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if key:
            values[key] = value
    return values
