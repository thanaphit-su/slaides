from __future__ import annotations

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from ..settings import get_settings


def _fernet(workspace_id: uuid.UUID) -> Fernet:
    settings = get_settings()
    root = settings.llm_encryption_secret or settings.jwt_secret
    digest = hashlib.sha256(f"{root}:{workspace_id}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_workspace_secret(workspace_id: uuid.UUID, secret: str) -> bytes:
    return _fernet(workspace_id).encrypt(secret.encode("utf-8"))


def decrypt_workspace_secret(workspace_id: uuid.UUID, encrypted: bytes | None) -> str | None:
    if not encrypted:
        return None
    return _fernet(workspace_id).decrypt(encrypted).decode("utf-8")
