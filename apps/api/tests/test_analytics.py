"""Tests for analytics module - session transcript and replay."""

import uuid

from slaides.analytics.crypto import (
    encrypt_for_transcript, decrypt_for_transcript,
    hash_for_transcript,
)


class TestCrypto:
    """Test transcript encryption/decryption - pure functions, no DB needed."""

    async def test_encrypt_decrypt_roundtrip(self):
        """Encrypted text can be decrypted back."""
        ws_id = uuid.uuid4()
        original = "sensitive selection text"
        encrypted = encrypt_for_transcript(ws_id, original)
        decrypted = decrypt_for_transcript(ws_id, encrypted)
        assert decrypted == original

    async def test_different_workspaces_different_keys(self):
        """Same text encrypted with different workspace IDs produces different ciphertext."""
        ws1 = uuid.uuid4()
        ws2 = uuid.uuid4()
        text = "same text"
        enc1 = encrypt_for_transcript(ws1, text)
        enc2 = encrypt_for_transcript(ws2, text)
        assert enc1 != enc2

    async def test_hash_deterministic(self):
        """Hash function is deterministic."""
        text = "test content"
        h1 = hash_for_transcript(text)
        h2 = hash_for_transcript(text)
        assert h1 == h2
        assert len(h1) == 64


class TestTranscriptEndpoints:
    """Integration tests for transcript API endpoints."""

    async def test_transcript_requires_auth(self, client):
        """Transcript endpoint requires authentication."""
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/sessions/{fake_id}/transcript")
        assert res.status_code == 401

    async def test_transcript_returns_404_for_unknown_session(self, client, auth_headers):
        """Transcript returns 404 for non-existent session."""
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/sessions/{fake_id}/transcript", headers=auth_headers)
        assert res.status_code == 404

    async def test_replay_requires_auth(self, client):
        """Replay endpoint requires authentication."""
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/sessions/{fake_id}/replay")
        assert res.status_code == 401

    async def test_transcript_csv_requires_auth(self, client):
        """CSV export requires authentication."""
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/sessions/{fake_id}/transcript.csv")
        assert res.status_code == 401

    async def test_transcript_json_requires_auth(self, client):
        """JSON export requires authentication."""
        fake_id = str(uuid.uuid4())
        res = await client.get(f"/api/v1/sessions/{fake_id}/transcript.json")
        assert res.status_code == 401

    async def test_transcript_pagination_params(self, client, auth_headers, seeded_user):
        """Transcript accepts limit/offset pagination params."""
        # Create a session first
        deck_res = await client.post("/api/v1/decks", json={"title": "Test"}, headers=auth_headers)
        assert deck_res.status_code == 201
        deck = deck_res.json()

        session_res = await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
        assert session_res.status_code == 201
        session = session_res.json()

        # Fetch transcript with pagination
        res = await client.get(
            f"/api/v1/sessions/{session['id']}/transcript?limit=10&offset=0",
            headers=auth_headers
        )
        assert res.status_code == 200
        body = res.json()
        assert "events" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body
        assert body["limit"] == 10
        assert body["offset"] == 0

    async def test_transcript_includes_pre_migration_warning_for_old_sessions(self, client, auth_headers, seeded_user):
        """Transcript includes warning for pre-migration sessions."""
        # Create a session
        deck_res = await client.post("/api/v1/decks", json={"title": "Test"}, headers=auth_headers)
        assert deck_res.status_code == 201
        deck = deck_res.json()

        session_res = await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
        assert session_res.status_code == 201
        session = session_res.json()

        # End the session immediately (no slide advances)
        end_res = await client.post(f"/api/v1/sessions/{session['id']}/end", headers=auth_headers)
        assert end_res.status_code == 200

        # Fetch transcript
        res = await client.get(f"/api/v1/sessions/{session['id']}/transcript", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        # Since session ended before any slide advances, should have warning
        assert "pre_migration_warning" in body
