"""Widgets v2 Step 4 — placement_state read/write + Loud-widget round-trip
through the WS layer."""
from __future__ import annotations

import asyncio
import json
import uuid

import fakeredis.aioredis as fakeredis_async
import pytest

from slaides.sessions.placement_state_service import (
    placement_state_select_for_update,
    contribute_to_placement,
    list_session_placement_states,
    load_placement_state,
)
from slaides.sessions.ws import _Connection, _handle_client_event, hub as ws_hub


async def _drain(conn: _Connection, *, want: str, timeout: float = 2.0) -> dict:
    while True:
        raw = await asyncio.wait_for(conn.queue.get(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("type") == want:
            return msg


async def _seed_loud_widget(client, headers, *, behavior: dict):
    """Create a deck, attach a Loud widget to the first slide, open a session,
    and return the placement_id + session_id."""
    deck = (await client.post("/api/v1/decks", json={"title": "Loud"}, headers=headers)).json()
    slide_id = deck["slides"][0]["id"]

    widget = (
        await client.post(
            f"/api/v1/decks/{deck['id']}/widgets",
            json={
                "name": "Loud W",
                "kind": "custom",
                "html": "<section></section>",
                "behavior": behavior,
            },
            headers=headers,
        )
    ).json()

    placement_id = "loud-1"
    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": placement_id, "widget_id": widget["id"]},
        headers=headers,
    )
    assert attach.status_code == 201, attach.text

    session = (
        await client.post(
            "/api/v1/sessions", json={"deck_id": deck["id"]}, headers=headers
        )
    ).json()
    return {
        "deck": deck,
        "widget": widget,
        "placement_id": placement_id,
        "session_id": uuid.UUID(session["id"]),
        "code": session["code"],
    }


async def _new_deck(client, headers, title: str = "Deck"):
    res = await client.post("/api/v1/decks", json={"title": title}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _create_widget(client, headers, deck_id: str, **overrides):
    payload = {
        "name": "Widget",
        "kind": "custom",
        "html": "<section>widget</section>",
        "behavior": {"kind": "quiet"},
    }
    payload.update(overrides)
    res = await client.post(
        f"/api/v1/decks/{deck_id}/widgets",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_live_placement_uses_original_revision_after_widget_edit(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Session revision")
    slide_id = deck["slides"][0]["id"]
    widget = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Live",
        html="<p>v1</p>",
    )
    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "live-1", "widget_id": widget["id"]},
        headers=auth_headers,
    )
    assert attach.status_code == 201, attach.text

    original_revision_id = widget["current_revision_id"]
    patch = await client.patch(
        f"/api/v1/widgets/{widget['id']}",
        json={"html": "<p>v2</p>"},
        headers=auth_headers,
    )
    assert patch.status_code == 200, patch.text

    deck_after = await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)
    assert deck_after.status_code == 200, deck_after.text
    placement = deck_after.json()["slides"][0]["widgets"][0]
    assert placement["revision_id"] == original_revision_id
    assert placement["revision"]["html"] == "<p>v1</p>"


async def test_placement_state_tally_round_trip(client, auth_headers, app_with_db):
    """End-to-end: an iframe-style widget.contribute event arrives over the
    WS, the placement_state row gets created + updated, and widget.state
    fires for the host. Late-joiner snapshot returns the same state."""
    seeded = await _seed_loud_widget(
        client,
        auth_headers,
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    session_id = seeded["session_id"]
    placement_id = seeded["placement_id"]

    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    audience = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="alice",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, audience)

    try:
        await _handle_client_event(
            session_id,
            audience,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": placement_id, "value": "yes"},
            },
        )
        msg = await _drain(host, want="widget.state")
        assert msg["payload"]["placement_id"] == placement_id
        assert msg["payload"]["state"]["tally"] == {"yes": 1}
        assert msg["payload"]["state_version"] == 1
        assert msg["payload"]["closed"] is False

        # Second voter; a third "alice re-vote" overwrites her previous one.
        another = _Connection(
            socket=object(),
            role="participant",
            participant_id=uuid.uuid4(),
            participant_ref="bob",
        )
        await ws_hub.register(session_id, another)
        await _handle_client_event(
            session_id,
            another,
            {"type": "widget.contribute", "payload": {"placement_id": placement_id, "value": "no"}},
        )
        await _drain(host, want="widget.state")
        await _handle_client_event(
            session_id,
            audience,
            {"type": "widget.contribute", "payload": {"placement_id": placement_id, "value": "no"}},
        )
        final = await _drain(host, want="widget.state")
        assert final["payload"]["state"]["tally"] == {"no": 2}
        assert final["payload"]["state_version"] >= 3
    finally:
        await ws_hub.aclose()

    # Late-joiner snapshot: guest token → audience endpoint should now return
    # the placement_state in the placement_states[] array.
    guest = (
        await client.post(
            "/api/v1/auth/guest",
            json={"code": seeded["code"], "email": "late@example.com", "anonymous": True},
        )
    ).json()
    snap = await client.get(
        f"/api/v1/sessions/{seeded['session_id']}/audience",
        headers={"Authorization": f"Bearer {guest['token']}"},
    )
    body = snap.json()
    entry = next((p for p in body["placement_states"] if p["placement_id"] == placement_id), None)
    assert entry is not None
    assert entry["aggregator"] == "tally"
    assert entry["state"]["tally"] == {"no": 2}
    assert entry["state_version"] >= 3
    assert entry["closed"] is False


async def test_collect_widget_is_host_only_and_hidden_from_audience(
    client, auth_headers, app_with_db
):
    """A `collect` widget delivers contributions to the presenter only. The
    audience must never receive another participant's answer — not over the WS
    (host-only broadcast) and not in the /audience snapshot (privacy gate)."""
    seeded = await _seed_loud_widget(
        client,
        auth_headers,
        behavior={"kind": "collect", "contribution_schema": {"type": "string"}},
    )
    session_id = seeded["session_id"]
    placement_id = seeded["placement_id"]

    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    alice = _Connection(
        socket=object(), role="participant", participant_id=uuid.uuid4(), participant_ref="alice"
    )
    bob = _Connection(
        socket=object(), role="participant", participant_id=uuid.uuid4(), participant_ref="bob"
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, alice)
    await ws_hub.register(session_id, bob)

    try:
        await _handle_client_event(
            session_id,
            alice,
            {"type": "widget.contribute", "payload": {"placement_id": placement_id, "value": "alice answer"}},
        )
        await _handle_client_event(
            session_id,
            bob,
            {"type": "widget.contribute", "payload": {"placement_id": placement_id, "value": "bob answer"}},
        )

        # Presenter sees every entry.
        msg = await _drain(host, want="widget.state")
        entries = msg["payload"]["state"]["entries"]
        # Drain until both answers are present (events arrive incrementally).
        while len(entries) < 2:
            msg = await _drain(host, want="widget.state")
            entries = msg["payload"]["state"]["entries"]
        values = {e["value"] for e in entries}
        assert values == {"alice answer", "bob answer"}

        # The audience must NOT have received any widget.state over the WS.
        with pytest.raises(asyncio.TimeoutError):
            await _drain(bob, want="widget.state", timeout=0.5)

        # Liveness check: prove bob's subscriber is live (so the absence above
        # is real, not a dead subscriber) — an all-broadcast still reaches him.
        await ws_hub.publish(session_id, {"type": "liveness.probe", "payload": {}})
        await _drain(bob, want="liveness.probe")
    finally:
        await ws_hub.aclose()

    # Audience snapshot must EXCLUDE the collect placement entirely.
    guest = (
        await client.post(
            "/api/v1/auth/guest",
            json={"code": seeded["code"], "email": "late@example.com", "anonymous": True},
        )
    ).json()
    aud_snap = await client.get(
        f"/api/v1/sessions/{session_id}/audience",
        headers={"Authorization": f"Bearer {guest['token']}"},
    )
    aud_entry = next(
        (p for p in aud_snap.json()["placement_states"] if p["placement_id"] == placement_id),
        None,
    )
    assert aud_entry is None, "collect answers leaked into the audience snapshot"

    # Host snapshot must INCLUDE it, with every answer.
    host_snap = await client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers)
    host_entry = next(
        (p for p in host_snap.json()["placement_states"] if p["placement_id"] == placement_id),
        None,
    )
    assert host_entry is not None
    assert host_entry["aggregator"] == "collect"
    assert {e["value"] for e in host_entry["state"]["entries"]} == {"alice answer", "bob answer"}


async def test_quiet_widget_contributions_are_silently_dropped(client, auth_headers):
    seeded = await _seed_loud_widget(
        client, auth_headers, behavior={"kind": "quiet"}
    )
    session_id = seeded["session_id"]

    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    audience = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="alice",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, audience)
    try:
        await _handle_client_event(
            session_id,
            audience,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": seeded["placement_id"], "value": "ignored"},
            },
        )
        # Give the dispatcher a tick; no widget.state should arrive.
        with pytest.raises(asyncio.TimeoutError):
            await _drain(host, want="widget.state", timeout=0.2)
    finally:
        await ws_hub.aclose()

    # And the table stays empty.
    from slaides.db.base import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        row = await load_placement_state(db, session_id, seeded["placement_id"])
        assert row is None


async def test_loud_placement_keeps_revision_behavior_after_widget_edit(client, auth_headers):
    seeded = await _seed_loud_widget(
        client,
        auth_headers,
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    patch = await client.patch(
        f"/api/v1/widgets/{seeded['widget']['id']}",
        json={"behavior": {"kind": "quiet"}},
        headers=auth_headers,
    )
    assert patch.status_code == 200, patch.text

    session_id = seeded["session_id"]
    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    audience = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="alice",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, audience)
    try:
        await _handle_client_event(
            session_id,
            audience,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": seeded["placement_id"], "value": "yes"},
            },
        )
        msg = await _drain(host, want="widget.state")
        assert msg["payload"]["placement_id"] == seeded["placement_id"]
        assert msg["payload"]["state"]["tally"] == {"yes": 1}
    finally:
        await ws_hub.aclose()


async def test_cross_session_placement_id_is_rejected(client, auth_headers):
    seeded = await _seed_loud_widget(
        client,
        auth_headers,
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    other_session_id = uuid.uuid4()  # not seeded["session_id"] — wrong session.

    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    audience = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="snooper",
    )
    await ws_hub.register(other_session_id, host)
    await ws_hub.register(other_session_id, audience)
    try:
        await _handle_client_event(
            other_session_id,
            audience,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": seeded["placement_id"], "value": "yes"},
            },
        )
        with pytest.raises(asyncio.TimeoutError):
            await _drain(host, want="widget.state", timeout=0.2)
    finally:
        await ws_hub.aclose()

    from slaides.db.base import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        # No row in either session — the wrong-session contribution was
        # dropped at the audience-scope guard.
        assert (await list_session_placement_states(db, other_session_id)) == []
        assert (await list_session_placement_states(db, seeded["session_id"])) == []


async def test_contribute_to_placement_locks_aggregator(app_with_db):
    """A placement's aggregator is sticky after the first contribution — a
    widget can't switch shape mid-session and corrupt state."""
    from slaides.db.base import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        # Build minimal session row (no slides etc — we're hitting placement
        # state directly).
        from slaides.db import models as _m
        ws = _m.Workspace(name="t")
        db.add(ws)
        await db.flush()
        user = _m.AppUser(workspace_id=ws.id, email="x@x", role="owner", approval_status="approved")
        db.add(user)
        await db.flush()
        deck = _m.Deck(workspace_id=ws.id, owner_id=user.id, title="t")
        db.add(deck)
        await db.flush()
        sess = _m.Session(
            deck_id=deck.id, owner_id=user.id, workspace_id=ws.id, code="SLD-T-1", salt="s"
        )
        db.add(sess)
        await db.flush()

        await contribute_to_placement(
            db,
            session_id=sess.id,
            placement_id="p1",
            widget_id=None,
            aggregator="tally",
            value="a",
            participant_ref="ref1",
        )
        await db.commit()

        with pytest.raises(ValueError, match="aggregator"):
            await contribute_to_placement(
                db,
                session_id=sess.id,
                placement_id="p1",
                widget_id=None,
                aggregator="append",
                value="something",
                participant_ref="ref1",
            )


def test_placement_state_lookup_uses_row_lock_for_writes():
    stmt = placement_state_select_for_update(uuid.uuid4(), "live-poll")

    assert stmt._for_update_arg is not None


async def test_cross_deck_placement_id_collision_resolves_to_current_session_deck(
    client, auth_headers
):
    """BUG 4 regression. `placement_id` is only unique per (slide_id, _);
    if two decks both attach a placement called `live-poll`, the WS handler
    used to fetch whichever row Postgres returned first and then drop the
    contribution when its deck didn't match. The fix deck-scopes the lookup
    against the session's deck up front."""
    # First deck — Loud poll attached as placement `live-poll`. We don't
    # open a session here; this deck exists to compete with the same
    # placement_id in the lookup.
    deck_a = (
        await client.post("/api/v1/decks", json={"title": "Deck A"}, headers=auth_headers)
    ).json()
    widget_a = (
        await client.post(
            f"/api/v1/decks/{deck_a['id']}/widgets",
            json={
                "name": "Poll A",
                "kind": "live-poll",
                "html": "<section></section>",
                "behavior": {
                    "kind": "loud",
                    "aggregator": "tally",
                    "contribution_schema": {"type": "string"},
                },
            },
            headers=auth_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/decks/{deck_a['id']}/slides/{deck_a['slides'][0]['id']}/widgets",
        json={"placement_id": "live-poll", "widget_id": widget_a["id"]},
        headers=auth_headers,
    )

    # Second deck — same placement_id, different widget id. Open a session
    # on THIS deck and contribute.
    seeded = await _seed_loud_widget(
        client,
        auth_headers,
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    # Reattach using the same placement_id as deck_a (loud-1 → live-poll).
    # The seed helper used `loud-1`; we rename through a fresh widget attach.
    deck_b = seeded["deck"]
    widget_b = seeded["widget"]
    # Drop the original attach and re-attach with our colliding placement id.
    await client.delete(
        f"/api/v1/decks/{deck_b['id']}/slides/{deck_b['slides'][0]['id']}/widgets/{seeded['placement_id']}",
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/decks/{deck_b['id']}/slides/{deck_b['slides'][0]['id']}/widgets",
        json={"placement_id": "live-poll", "widget_id": widget_b["id"]},
        headers=auth_headers,
    )

    session_id = seeded["session_id"]
    ws_hub.set_redis(fakeredis_async.FakeRedis(decode_responses=True))
    host = _Connection(socket=object(), role="host", participant_id=None, participant_ref=None)
    audience = _Connection(
        socket=object(),
        role="participant",
        participant_id=uuid.uuid4(),
        participant_ref="alice",
    )
    await ws_hub.register(session_id, host)
    await ws_hub.register(session_id, audience)
    try:
        await _handle_client_event(
            session_id,
            audience,
            {
                "type": "widget.contribute",
                "payload": {"placement_id": "live-poll", "value": "go"},
            },
        )
        # The deck-scoped lookup pins the contribution to deck_b's placement,
        # so widget.state arrives with the new tally — *not* dropped because
        # the lookup happened to hit deck_a's placement first.
        msg = await _drain(host, want="widget.state")
        assert msg["payload"]["state"]["tally"] == {"go": 1}
    finally:
        await ws_hub.aclose()
