from __future__ import annotations

import asyncio
import json
from urllib.parse import quote
import uuid

import fakeredis.aioredis as fakeredis_async
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from slaides.sessions.ws import Hub, _Connection, _handle_client_event, hub as ws_hub


class _StubSocket:
    pass


class _ClosableSocket:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_hub_publishes_to_all_connections():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        session_id = uuid.uuid4()
        c1 = _Connection(socket=_StubSocket(), role="host", participant_id=None, participant_ref=None)
        c2 = _Connection(
            socket=_StubSocket(),
            role="participant",
            participant_id=uuid.uuid4(),
            participant_ref="abc",
        )
        c3 = _Connection(socket=_StubSocket(), role="mirror", participant_id=None, participant_ref=None)
        await hub.register(session_id, c1)
        await hub.register(session_id, c2)
        await hub.register(session_id, c3)

        await hub.publish(session_id, {"type": "slide.changed", "payload": {"slide_id": "x"}})

        async def drain(conn: _Connection) -> dict:
            msg = await asyncio.wait_for(conn.queue.get(), timeout=2.0)
            return json.loads(msg)

        got1 = await drain(c1)
        got2 = await drain(c2)
        got3 = await drain(c3)
        assert got1["type"] == "slide.changed"
        assert got2["type"] == "slide.changed"
        assert got3["type"] == "slide.changed"
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_hub_close_role_closes_only_matching_connections():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        session_id = uuid.uuid4()
        host_socket = _ClosableSocket()
        mirror_socket = _ClosableSocket()
        host = _Connection(socket=host_socket, role="host", participant_id=None, participant_ref=None)
        mirror = _Connection(socket=mirror_socket, role="mirror", participant_id=None, participant_ref=None)
        await hub.register(session_id, host)
        await hub.register(session_id, mirror)

        await hub.close_role_for_sessions([session_id], "mirror")

        assert mirror_socket.closed is True
        assert host_socket.closed is False
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_hub_host_only_events_do_not_reach_mirror():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        session_id = uuid.uuid4()
        host = _Connection(socket=_StubSocket(), role="host", participant_id=None, participant_ref=None)
        mirror = _Connection(socket=_StubSocket(), role="mirror", participant_id=None, participant_ref=None)
        await hub.register(session_id, host)
        await hub.register(session_id, mirror)

        await hub.publish_to_role(session_id, "host", {"type": "question_answer.new", "payload": {"text": "secret"}})
        got = json.loads(await asyncio.wait_for(host.queue.get(), timeout=2.0))
        assert got["type"] == "question_answer.new"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mirror.queue.get(), timeout=0.05)
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_hub_filters_presence_and_question_events_from_mirror():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        session_id = uuid.uuid4()
        host = _Connection(socket=_StubSocket(), role="host", participant_id=None, participant_ref=None)
        mirror = _Connection(socket=_StubSocket(), role="mirror", participant_id=None, participant_ref=None)
        await hub.register(session_id, host)
        await hub.register(session_id, mirror)

        blocked_types = ("participant.joined", "participant.left", "question.new", "question.answered")
        for event_type in blocked_types:
            await hub.publish(session_id, {"type": event_type, "payload": {"value": event_type}})
            got = json.loads(await asyncio.wait_for(host.queue.get(), timeout=2.0))
            assert got["type"] == event_type

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mirror.queue.get(), timeout=0.05)

        await hub.publish(session_id, {"type": "slide.changed", "payload": {"slide_id": "x"}})
        got_public = json.loads(await asyncio.wait_for(mirror.queue.get(), timeout=2.0))
        assert got_public["type"] == "slide.changed"
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_hub_presence_count_via_heartbeats():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        sid = uuid.uuid4()
        assert await hub.presence_count(sid) == 0
        await hub.heartbeat(sid, "ref-a")
        await hub.heartbeat(sid, "ref-b")
        assert await hub.presence_count(sid) == 2
        await hub.drop_presence(sid, "ref-a")
        assert await hub.presence_count(sid) == 1
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_mirror_connection_does_not_increment_presence():
    hub = Hub()
    hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    try:
        sid = uuid.uuid4()
        mirror = _Connection(socket=_StubSocket(), role="mirror", participant_id=None, participant_ref=None)
        await hub.register(sid, mirror)
        assert await hub.presence_count(sid) == 0
    finally:
        await hub.aclose()


async def _seed_poll_session(client, headers):
    """Helper: create a deck, open a session, launch a poll, return the
    poll session_slide's id and the session id."""
    deck = (await client.post("/api/v1/decks", json={"title": "WS"}, headers=headers)).json()
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=headers)
    ).json()
    poll = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/interactions",
            json={
                "kind": "poll",
                "spec": {
                    "type": "poll",
                    "question": "Pick",
                    "choices": [{"id": "c1", "label": "One"}, {"id": "c2", "label": "Two"}],
                    "config": {"allow_other": False, "show_results_live": True, "anonymous": True},
                },
                "inverted_theme": False,
            },
            headers=headers,
        )
    ).json()
    return uuid.UUID(session["id"]), uuid.UUID(poll["id"])


async def _session_mirror_token(session_id: str) -> str:
    from sqlalchemy import select

    from slaides.db import models
    from slaides.db.base import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        row = (
            await db.execute(select(models.Session).where(models.Session.id == uuid.UUID(session_id)))
        ).scalar_one()
        assert row.mirror_token
        return row.mirror_token


async def _drain(conn: _Connection, *, want: str, timeout: float = 2.0) -> dict:
    """Drain the connection queue until we see an event matching `want`."""
    while True:
        raw = await asyncio.wait_for(conn.queue.get(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("type") == want:
            return msg


async def test_widget_contribute_routes_through_aggregator_and_broadcasts_widget_state(
    client, auth_headers
):
    """Step 3 — both the legacy `interaction.vote` and the new
    `widget.contribute` wire protocols must produce identical state, and the
    new canonical `widget.state` event must fire alongside the existing
    `interaction.tally`."""
    session_id, poll_id = await _seed_poll_session(client, auth_headers)

    # Wire the WS hub to fakeredis so we can read the broadcast.
    fake = fakeredis_async.FakeRedis(decode_responses=True)
    ws_hub.set_redis(fake)
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    participant = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="alice-ref",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, participant)
    try:
        # Legacy path.
        await _handle_client_event(
            session_id,
            participant,
            {
                "type": "interaction.vote",
                "payload": {"session_slide_id": str(poll_id), "choice": "c1"},
            },
        )
        legacy_tally = await _drain(host, want="interaction.tally")
        legacy_state = await _drain(host, want="widget.state")
        assert legacy_tally["payload"]["results"]["tally"] == {"c1": 1}
        assert legacy_state["payload"]["placement_id"] == str(poll_id)
        assert legacy_state["payload"]["state_version"] >= 1
        assert legacy_state["payload"]["state"]["tally"] == {"c1": 1}

        # New unified path — same audience changes vote via widget.contribute.
        await _handle_client_event(
            session_id,
            participant,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": str(poll_id), "value": "c2"},
            },
        )
        new_tally = await _drain(host, want="interaction.tally")
        new_state = await _drain(host, want="widget.state")
        assert new_tally["payload"]["results"]["tally"] == {"c2": 1}
        assert new_state["payload"]["state"]["tally"] == {"c2": 1}
        assert new_state["payload"]["state_version"] > legacy_state["payload"]["state_version"]
    finally:
        await ws_hub.aclose()


async def test_widget_contribute_open_question_emits_widget_state(client, auth_headers):
    deck = (await client.post("/api/v1/decks", json={"title": "WS-q"}, headers=auth_headers)).json()
    session = (
        await client.post(
            "/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers
        )
    ).json()
    question = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/interactions",
            json={
                "kind": "question",
                "spec": {
                    "type": "question",
                    "prompt": "Thoughts?",
                    "config": {"anonymous": True},
                },
                "inverted_theme": False,
            },
            headers=auth_headers,
        )
    ).json()
    session_id = uuid.UUID(session["id"])
    ss_id = uuid.UUID(question["id"])

    fake = fakeredis_async.FakeRedis(decode_responses=True)
    ws_hub.set_redis(fake)
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    participant = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="bob-ref",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, participant)
    try:
        await _handle_client_event(
            session_id,
            participant,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": str(ss_id), "value": "first answer"},
            },
        )
        # Audience-broadcast widget.state carries the updated total_answers.
        state_msg = await _drain(host, want="widget.state")
        assert state_msg["payload"]["state"]["total_answers"] == 1
        # Host also receives the answer details on the host-only channel.
        host_only = await _drain(host, want="question_answer.new")
        assert host_only["payload"]["answer"]["text"] == "first answer"
    finally:
        await ws_hub.aclose()


async def test_mirror_role_cannot_send_contribution_or_question_events(client, auth_headers):
    from sqlalchemy import select

    from slaides.db import models
    from slaides.db.base import get_session_factory

    session_id, poll_id = await _seed_poll_session(client, auth_headers)
    fake = fakeredis_async.FakeRedis(decode_responses=True)
    ws_hub.set_redis(fake)
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    mirror = _Connection(socket=object(), role="mirror", participant_id=None, participant_ref=None)
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, mirror)
    try:
        for event in (
            {"type": "interaction.vote", "payload": {"session_slide_id": str(poll_id), "choice": "c1"}},
            {"type": "widget.contribute", "payload": {"placement_id": str(poll_id), "value": "c1"}},
            {"type": "question.raise", "payload": {"text": "should not land"}},
        ):
            await _handle_client_event(session_id, mirror, event)

        factory = get_session_factory()
        async with factory() as db:
            poll = (
                await db.execute(select(models.SessionSlide).where(models.SessionSlide.id == poll_id))
            ).scalar_one()
            questions = (
                await db.execute(select(models.Question).where(models.Question.session_id == session_id))
            ).scalars().all()
            logs = (
                await db.execute(select(models.InteractionLog).where(models.InteractionLog.session_id == session_id))
            ).scalars().all()
        assert poll.results == {}
        assert questions == []
        assert logs == []
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(host.queue.get(), timeout=0.05)
    finally:
        await ws_hub.aclose()


async def test_mirror_websocket_route_authorizes_link_token(client, auth_headers, app_with_db):
    deck = (await client.post("/api/v1/decks", json={"title": "Mirror WS"}, headers=auth_headers)).json()
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    access = await client.patch(
        f"/api/v1/decks/{deck['id']}/mirror-access",
        json={"mode": "link", "allowed_emails": []},
        headers=auth_headers,
    )
    assert access.status_code == 200, access.text
    mirror_token = await _session_mirror_token(session["id"])

    with TestClient(app_with_db) as sync_client:
        with sync_client.websocket_connect(
            f"/ws/sessions/{session['id']}?role=mirror&token={quote(mirror_token)}"
        ) as websocket:
            state = websocket.receive_json()
            assert state["type"] == "session.state"
            assert state["payload"]["current_slide_id"] == session["current_slide_id"]
            for event_type in ("participant.joined", "participant.left", "question.new", "question.answered"):
                await ws_hub.publish(
                    uuid.UUID(session["id"]),
                    {"type": event_type, "payload": {"value": event_type}},
                )
            await ws_hub.publish(
                uuid.UUID(session["id"]),
                {"type": "slide.changed", "payload": {"slide_id": session["current_slide_id"]}},
            )
            event = websocket.receive_json()
            assert event["type"] == "slide.changed"

        with pytest.raises(WebSocketDisconnect):
            with sync_client.websocket_connect(
                f"/ws/sessions/{session['id']}?role=mirror&token=wrong"
            ):
                pass
