"""Transcript-specific encryption wrappers."""

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from ..llm.crypto import _fernet
from ..settings import get_settings


def _transcript_fernet(workspace_id: uuid.UUID) -> Fernet:
    """Derive a separate Fernet key for transcript encryption.
    
    This allows LLM API key rotation without bricking historical transcripts.
    """
    settings = get_settings()
    root = settings.llm_encryption_secret or settings.jwt_secret
    digest = hashlib.sha256(f"{root}:transcript:{workspace_id}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def hash_for_transcript(text: str) -> str:
    """SHA-256 hash for transcript deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def encrypt_for_transcript(workspace_id: uuid.UUID, text: str) -> str:
    """Encrypt text for transcript storage (returns base64 string)."""
    encrypted = _transcript_fernet(workspace_id).encrypt(text.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_for_transcript(workspace_id: uuid.UUID, encrypted: str) -> str:
    """Decrypt transcript text."""
    return _transcript_fernet(workspace_id).decrypt(encrypted.encode("utf-8")).decode("utf-8")
