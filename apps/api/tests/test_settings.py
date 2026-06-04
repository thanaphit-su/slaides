from __future__ import annotations

import subprocess

import pytest
from pydantic import ValidationError

import slaides.settings as settings_module
from slaides.settings import Settings


def test_local_supabase_keys_load_from_compose_env_when_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_local_supabase_compose_env",
        lambda: {
            "API_URL": "http://localhost:54321",
            "ANON_KEY": "compose-anon",
            "SERVICE_ROLE_KEY": "compose-service",
        },
    )

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:54322/postgres",
        supabase_anon_key="",
        supabase_service_role_key="",
    )

    assert settings.supabase_url == "http://localhost:54321"
    assert settings.supabase_anon_key == "compose-anon"
    assert settings.supabase_service_role_key == "compose-service"


def test_local_supabase_keys_fall_back_to_cli_status_when_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["supabase", "status", "-o", "env"],
            returncode=0,
            stdout=(
                'API_URL="http://127.0.0.1:54321"\n'
                'ANON_KEY="local-anon"\n'
                'SERVICE_ROLE_KEY="local-service"\n'
            ),
            stderr="",
        )

    monkeypatch.setattr(settings_module, "_local_supabase_compose_env", lambda: {})
    monkeypatch.setattr(subprocess, "run", fake_run)

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:54322/postgres",
        supabase_anon_key="",
        supabase_service_role_key="",
    )

    assert settings.supabase_url == "http://127.0.0.1:54321"
    assert settings.supabase_anon_key == "local-anon"
    assert settings.supabase_service_role_key == "local-service"


def test_production_settings_reject_dev_defaults():
    with pytest.raises(ValidationError, match="production settings are unsafe"):
        Settings(slaides_env="production")
