from __future__ import annotations


async def _create_deck(client, headers):
    res = await client.post(
        "/api/v1/decks",
        json={"title": "Session deck"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_session_returns_snapshot_with_code(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    res = await client.post(
        "/api/v1/sessions",
        json={"deck_id": deck["id"]},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["deck_id"] == deck["id"]
    assert body["deck_title"] == "Session deck"
    assert body["code"].startswith("SLD-")
    assert body["ended_at"] is None
    assert body["current_slide_id"] == deck["slides"][0]["id"]
    assert body["audience_count"] == 0


async def test_audience_snapshot_includes_interpret_quick_options(client, auth_headers):
    settings = await client.patch(
        "/api/v1/workspace",
        headers=auth_headers,
        json={
            "interpret_quick_options": [
                {"label": "Define", "instruction": "show a simple definition"},
                {"label": "Why", "instruction": "explain why this matters"},
            ],
        },
    )
    assert settings.status_code == 200, settings.text
    deck = await _create_deck(client, auth_headers)
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    guest = await client.post(
        "/api/v1/auth/guest",
        json={"code": session["code"], "email": "audience@example.com", "anonymous": True},
    )
    assert guest.status_code == 200, guest.text

    snapshot = await client.get(
        f"/api/v1/sessions/{session['id']}/audience",
        headers={"Authorization": f"Bearer {guest.json()['token']}"},
    )
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["interpret_quick_options"] == [
        {"label": "Define", "instruction": "show a simple definition"},
        {"label": "Why", "instruction": "explain why this matters"},
    ]


async def test_create_session_rejects_second_active_real_session_until_ended(client, auth_headers):
    first_deck = await _create_deck(client, auth_headers)
    second_deck = await _create_deck(client, auth_headers)
    first = await client.post(
        "/api/v1/sessions",
        json={"deck_id": first_deck["id"]},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text

    blocked = await client.post(
        "/api/v1/sessions",
        json={"deck_id": second_deck["id"]},
        headers=auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "end active live session before starting a new one"

    ended = await client.post(
        f"/api/v1/sessions/{first.json()['id']}/end",
        headers=auth_headers,
    )
    assert ended.status_code == 200, ended.text

    allowed = await client.post(
        "/api/v1/sessions",
        json={"deck_id": second_deck["id"]},
        headers=auth_headers,
    )
    assert allowed.status_code == 201, allowed.text


async def test_get_by_code_is_public_and_guest_join_returns_token(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    code = session["code"]

    # by-code is unauthenticated.
    peek = await client.get(f"/api/v1/sessions/by-code/{code}")
    assert peek.status_code == 200
    assert peek.json()["id"] == session["id"]

    join = await client.post(
        "/api/v1/auth/guest",
        json={
            "code": code,
            "email": "bob@example.com",
            "display_name": "Bob",
            "anonymous": False,
        },
    )
    assert join.status_code == 200, join.text
    body = join.json()
    assert body["session_id"] == session["id"]
    assert len(body["participant_ref"]) == 64
    assert body["token"]

    # Anonymous: same email + salt → same ref; participant row is upserted.
    anon = await client.post(
        "/api/v1/auth/guest",
        json={
            "code": code,
            "email": "bob@example.com",
            "display_name": "Bob",
            "anonymous": True,
        },
    )
    assert anon.json()["participant_ref"] == body["participant_ref"]
    assert anon.json()["anon"] is True


async def test_advance_slide_updates_session(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    # Add a second slide so there's something to advance to.
    add = await client.post(
        f"/api/v1/decks/{deck['id']}/slides",
        json={"markdown": "# Slide two\n"},
        headers=auth_headers,
    )
    second_slide = add.json()["id"]

    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()

    adv = await client.post(
        f"/api/v1/sessions/{session['id']}/advance",
        json={"slide_id": second_slide},
        headers=auth_headers,
    )
    assert adv.status_code == 200, adv.text
    assert adv.json()["current_slide_id"] == second_slide


async def test_open_interaction_inserts_after_current_slide(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    second = await client.post(
        f"/api/v1/decks/{deck['id']}/slides",
        json={"markdown": "# Topic two\n"},
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    second_slide_id = second.json()["id"]
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    adv = await client.post(
        f"/api/v1/sessions/{session['id']}/advance",
        json={"slide_id": second_slide_id},
        headers=auth_headers,
    )
    assert adv.status_code == 200, adv.text

    res = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions",
        json={
            "kind": "poll",
            "spec": {
                "type": "poll",
                "question": "Sun or moon?",
                "choices": [{"id": "c1", "label": "Sun"}, {"id": "c2", "label": "Moon"}],
            },
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "poll"
    assert body["inverted_theme"] is False
    assert body["spec"]["question"] == "Sun or moon?"
    assert [c["label"] for c in body["spec"]["choices"]] == ["Sun", "Moon"]
    assert body["parent_slide_id"] == second_slide_id
    assert body["position"] == 0

    followup = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions",
        json={
            "kind": "question",
            "spec": {
                "type": "question",
                "prompt": "What is unclear?",
                "config": {"anonymous": True},
            },
        },
        headers=auth_headers,
    )
    assert followup.status_code == 201, followup.text
    followup_body = followup.json()
    assert followup_body["parent_slide_id"] == second_slide_id
    assert followup_body["position"] == 1

    snap = (
        await client.get(f"/api/v1/sessions/{session['id']}", headers=auth_headers)
    ).json()
    assert len(snap["session_slides"]) == 2
    assert [s["id"] for s in snap["session_slides"]] == [body["id"], followup_body["id"]]
    assert snap["current_slide_id"] == followup_body["id"]


async def test_open_random_audience_picks_active_participants(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    for name in ("Ada", "Ben", "Cy"):
        join = await client.post(
            "/api/v1/auth/guest",
            json={
                "code": session["code"],
                "email": f"{name.lower()}@example.com",
                "display_name": name,
                "anonymous": False,
            },
        )
        assert join.status_code == 200, join.text

    res = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions",
        json={"kind": "random", "spec": {"type": "random", "count": 2}},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "random"
    assert body["spec"] == {"type": "random", "count": 2}
    assert body["results"]["requested_count"] == 2
    assert body["results"]["eligible_count"] == 3
    assert len(body["results"]["picked"]) == 2
    assert {p["display_name"] for p in body["results"]["picked"]}.issubset({"Ada", "Ben", "Cy"})

    snap = (
        await client.get(f"/api/v1/sessions/{session['id']}", headers=auth_headers)
    ).json()
    assert snap["current_slide_id"] == body["id"]


async def test_end_session_sets_ended_at(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()
    guest = await client.post(
        "/api/v1/auth/guest",
        json={"code": session["code"], "email": "audience@example.com", "anonymous": True},
    )
    assert guest.status_code == 200, guest.text
    guest_headers = {"Authorization": f"Bearer {guest.json()['token']}"}

    audience_snapshot = await client.get(
        f"/api/v1/sessions/{session['id']}/audience", headers=guest_headers
    )
    assert audience_snapshot.status_code == 200

    end = await client.post(f"/api/v1/sessions/{session['id']}/end", headers=auth_headers)
    assert end.status_code == 200
    assert end.json()["ended_at"] is not None

    # Guest join into ended session is rejected.
    join = await client.post(
        "/api/v1/auth/guest",
        json={"code": session["code"], "email": "x@y.z", "anonymous": True},
    )
    assert join.status_code == 410

    # Previously issued guest tokens cannot bypass the ended-session guard via
    # direct /audience/:sessionId route snapshot fetches.
    stale_snapshot = await client.get(
        f"/api/v1/sessions/{session['id']}/audience", headers=guest_headers
    )
    assert stale_snapshot.status_code == 410


async def test_workspace_scoping_blocks_other_workspace(client, auth_headers, seeded_user, fake_supabase_auth):
    # Create a second workspace + user, then try to read first user's sessions.
    from slaides.db.base import get_session_factory
    from slaides.db import models

    factory = get_session_factory()
    async with factory() as db:
        ws = models.Workspace(name="Other Workspace")
        db.add(ws)
        await db.flush()
        other = models.AppUser(
            workspace_id=ws.id,
            email="mallory@example.com",
            role="owner",
        )
        db.add(other)
        await db.commit()
        other_id = other.id  # noqa: F841
    fake_supabase_auth.add_user(
        email="mallory@example.com",
        password="hunter2",
        user_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    deck = await _create_deck(client, auth_headers)
    session = (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers)
    ).json()

    other_token = (
        await client.post(
            "/api/v1/auth/signin",
            json={"email": "mallory@example.com", "password": "hunter2"},
        )
    ).json()["access"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = await client.get(f"/api/v1/sessions/{session['id']}", headers=other_headers)
    assert res.status_code == 404


# ---- Live interactions: dedicated poll + open question ----


async def _open_poll(client, headers, session_id, **overrides):
    spec = {
        "type": "poll",
        "question": overrides.get("question", "Best pizza?"),
        "choices": overrides.get(
            "choices",
            [
                {"id": "c1", "label": "Margherita"},
                {"id": "c2", "label": "Hawaiian"},
            ],
        ),
        "config": overrides.get("config", {"allow_other": True, "anonymous": True, "show_results_live": True}),
    }
    res = await client.post(
        f"/api/v1/sessions/{session_id}/interactions",
        json={"kind": "poll", "spec": spec},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _open_question(client, headers, session_id, prompt="What still feels unclear?"):
    spec = {"type": "question", "prompt": prompt, "config": {"anonymous": True}}
    res = await client.post(
        f"/api/v1/sessions/{session_id}/interactions",
        json={"kind": "question", "spec": spec},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _new_session(client, headers):
    deck = await _create_deck(client, headers)
    return (
        await client.post("/api/v1/sessions", json={"deck_id": deck["id"]}, headers=headers)
    ).json()


async def test_poll_vote_updates_tally_and_is_idempotent(client, auth_headers):
    """Voting is upsert-style: re-voting overwrites instead of double-counting,
    and the tally lives on session_slide.results so the audience snapshot
    returns the current counts for late joiners.
    """
    session = await _new_session(client, auth_headers)
    poll = await _open_poll(client, auth_headers, session["id"])

    from slaides.db.base import get_session_factory
    from slaides.db import models as _m
    from sqlalchemy import select as _sel
    import uuid as _uuid

    factory = get_session_factory()
    async with factory() as db:
        slide = (
            await db.execute(_sel(_m.SessionSlide).where(_m.SessionSlide.id == _uuid.UUID(poll["id"])))
        ).scalar_one()
        # Vote three times from two refs (alice re-votes).
        from slaides.sessions import service as svc

        await svc.record_poll_vote(db, slide, "alice-ref", "c1")
        await svc.record_poll_vote(db, slide, "bob-ref", "c2")
        results = await svc.record_poll_vote(db, slide, "alice-ref", "c2")  # alice changes mind
        await db.commit()
        await db.refresh(slide)

    assert results["tally"] == {"c2": 2}
    assert results["voters"] == 2

    # Audience snapshot returns the same tally — late-joiner correctness.
    guest = await client.post(
        "/api/v1/auth/guest",
        json={"code": session["code"], "email": "audience@example.com", "anonymous": True},
    )
    guest_headers = {"Authorization": f"Bearer {guest.json()['token']}"}
    snap = await client.get(f"/api/v1/sessions/{session['id']}/audience", headers=guest_headers)
    poll_in_snap = next(s for s in snap.json()["session_slides"] if s["id"] == poll["id"])
    assert poll_in_snap["results"]["tally"] == {"c2": 2}
    assert poll_in_snap["results"]["voters"] == 2


async def test_choices_lock_after_first_vote_and_reset_unlocks(client, auth_headers):
    session = await _new_session(client, auth_headers)
    poll = await _open_poll(client, auth_headers, session["id"])

    # PATCH choices before any vote — allowed.
    pre = await client.patch(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}",
        json={
            "choices": [
                {"id": "c1", "label": "Cheese"},
                {"id": "c2", "label": "Pepperoni"},
                {"id": "c3", "label": "Veggie"},
            ]
        },
        headers=auth_headers,
    )
    assert pre.status_code == 200, pre.text
    assert len(pre.json()["spec"]["choices"]) == 3

    # Now land a vote, then PATCH choices — rejected with 409.
    from slaides.db.base import get_session_factory
    from slaides.db import models as _m
    from sqlalchemy import select as _sel
    from slaides.sessions import service as svc
    import uuid as _uuid

    factory = get_session_factory()
    async with factory() as db:
        slide = (
            await db.execute(_sel(_m.SessionSlide).where(_m.SessionSlide.id == _uuid.UUID(poll["id"])))
        ).scalar_one()
        await svc.record_poll_vote(db, slide, "voter", "c1")
        await db.commit()

    locked = await client.patch(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}",
        json={"choices": [{"id": "c1", "label": "X"}, {"id": "c2", "label": "Y"}]},
        headers=auth_headers,
    )
    assert locked.status_code == 409

    # Reset re-unlocks the choices and clears the tally.
    reset = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}/reset",
        headers=auth_headers,
    )
    assert reset.status_code == 200
    body = reset.json()
    assert body["spec"]["state"]["choices_locked"] is False
    assert body["results"]["tally"] == {}

    again = await client.patch(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}",
        json={"choices": [{"id": "c1", "label": "A"}, {"id": "c2", "label": "B"}]},
        headers=auth_headers,
    )
    assert again.status_code == 200


async def test_close_and_reopen_voting(client, auth_headers):
    session = await _new_session(client, auth_headers)
    poll = await _open_poll(client, auth_headers, session["id"])

    closed = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}/close",
        headers=auth_headers,
    )
    assert closed.status_code == 200
    assert closed.json()["spec"]["state"]["voting_closed"] is True

    reopened = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions/{poll['id']}/reopen",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["spec"]["state"]["voting_closed"] is False


async def test_open_question_moderation_audience_only_sees_promoted(client, auth_headers):
    session = await _new_session(client, auth_headers)
    q = await _open_question(client, auth_headers, session["id"])

    # Audience submits an answer through the service layer (mirrors WS path).
    from slaides.db.base import get_session_factory
    from slaides.db import models as _m
    from sqlalchemy import select as _sel
    from slaides.sessions import service as svc
    import uuid as _uuid

    factory = get_session_factory()
    async with factory() as db:
        slide = (
            await db.execute(_sel(_m.SessionSlide).where(_m.SessionSlide.id == _uuid.UUID(q["id"])))
        ).scalar_one()
        row1 = await svc.record_open_answer(db, slide, "aud-1", "Residuals are confusing")
        row2 = await svc.record_open_answer(db, slide, "aud-2", "Tally normalization?")
        await db.commit()
        row1_id, row2_id = int(row1.id), int(row2.id)

    # Presenter lists all answers via the host-only endpoint.
    listed = await client.get(
        f"/api/v1/sessions/{session['id']}/interactions/{q['id']}/answers",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    answers = listed.json()
    assert {a["text"] for a in answers} == {"Residuals are confusing", "Tally normalization?"}
    assert all(a["promoted"] is False for a in answers)

    # Audience snapshot at this point does NOT contain the answer texts —
    # only the prompt + the (currently empty) promoted list.
    guest = await client.post(
        "/api/v1/auth/guest",
        json={"code": session["code"], "email": "audience@example.com", "anonymous": True},
    )
    guest_headers = {"Authorization": f"Bearer {guest.json()['token']}"}
    snap = (await client.get(f"/api/v1/sessions/{session['id']}/audience", headers=guest_headers)).json()
    q_in_snap = next(s for s in snap["session_slides"] if s["id"] == q["id"])
    assert q_in_snap["results"].get("promoted", []) == []
    assert q_in_snap["results"].get("total_answers") == 2

    # Promote the first answer.
    promoted = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions/{q['id']}/promote/{row1_id}",
        headers=auth_headers,
    )
    assert promoted.status_code == 200
    snap2 = (await client.get(f"/api/v1/sessions/{session['id']}/audience", headers=guest_headers)).json()
    q_in_snap2 = next(s for s in snap2["session_slides"] if s["id"] == q["id"])
    promoted_texts = [p["text"] for p in q_in_snap2["results"]["promoted"]]
    assert promoted_texts == ["Residuals are confusing"]

    # Hide the second answer — removes from interaction_log + audience never sees it.
    hide = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions/{q['id']}/hide/{row2_id}",
        headers=auth_headers,
    )
    assert hide.status_code == 200
    re_list = await client.get(
        f"/api/v1/sessions/{session['id']}/interactions/{q['id']}/answers",
        headers=auth_headers,
    )
    assert {a["text"] for a in re_list.json()} == {"Residuals are confusing"}


async def test_save_poll_to_library(client, auth_headers):
    session = await _new_session(client, auth_headers)
    poll = await _open_poll(client, auth_headers, session["id"], question="Quiz: 2+2?", choices=[
        {"id": "a", "label": "3"},
        {"id": "b", "label": "4"},
    ])

    saved = await client.post(
        "/api/v1/widgets/from-interaction",
        json={"session_slide_id": poll["id"]},
        headers=auth_headers,
    )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["kind"] == "poll"
    assert body["props_schema"]["question"]["default"] == "Quiz: 2+2?"
    assert body["props_schema"]["options"]["default"] == ["3", "4"]
    # The widget is a valid library entry — listing it works.
    lst = await client.get("/api/v1/widgets", headers=auth_headers)
    assert any(w["id"] == body["id"] for w in lst.json())


async def test_create_preview_returns_session_and_fake_guests(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    res = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 3},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["session_id"]
    assert body["code"].startswith("SLD-")
    assert len(body["fake_guests"]) == 3
    names = [g["display_name"] for g in body["fake_guests"]]
    assert names == ["Alice", "Bob", "Carol"]
    for g in body["fake_guests"]:
        assert g["token"]
        assert len(g["participant_ref"]) == 64

    # The session is flagged as preview in the DB so the next preview run
    # can recognise it and tear it down.
    from slaides.db.base import get_session_factory
    from slaides.db import models
    from sqlalchemy import select
    import uuid as _uuid

    factory = get_session_factory()
    async with factory() as db:
        row = (
            await db.execute(
                select(models.Session).where(models.Session.id == _uuid.UUID(body["session_id"]))
            )
        ).scalar_one()
        assert row.is_preview is True


async def test_preview_rejects_second_active_preview_until_ended(client, auth_headers):
    first_deck = await _create_deck(client, auth_headers)
    second_deck = await _create_deck(client, auth_headers)
    first = (await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": first_deck["id"], "audience_count": 2},
        headers=auth_headers,
    )).json()
    blocked = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": second_deck["id"], "audience_count": 4},
        headers=auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "end active preview session before starting a new one"

    ended = await client.post(
        f"/api/v1/sessions/{first['session_id']}/end",
        headers=auth_headers,
    )
    assert ended.status_code == 200, ended.text

    second = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": second_deck["id"], "audience_count": 4},
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    assert len(second.json()["fake_guests"]) == 4


async def test_preview_leaves_real_sessions_intact(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    # Real session the instructor might still be hosting.
    real = (await client.post(
        "/api/v1/sessions",
        json={"deck_id": deck["id"]},
        headers=auth_headers,
    )).json()

    # Creating a preview session is separate from real-session hosting.
    preview = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 1},
        headers=auth_headers,
    )
    assert preview.status_code == 201, preview.text

    # The real session is untouched.
    snap = await client.get(f"/api/v1/sessions/{real['id']}", headers=auth_headers)
    assert snap.status_code == 200


async def test_active_endpoint_ignores_preview_sessions(client, auth_headers):
    """Preview sessions are ephemeral — the editor's Start/Resume button must
    never see them, or it'll offer to resume a deck-test sandbox in front of
    a live audience."""
    deck = await _create_deck(client, auth_headers)

    # No real session, no preview — `active` is null.
    res = await client.get(
        f"/api/v1/sessions/active?deck_id={deck['id']}", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json() is None

    # Spin up a preview session.
    prev = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 2},
        headers=auth_headers,
    )
    assert prev.status_code == 201

    # `active` still null — preview session doesn't count.
    res = await client.get(
        f"/api/v1/sessions/active?deck_id={deck['id']}", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json() is None

    # Now start a real session: `active` flips to its id, NOT the preview's.
    real = await client.post(
        "/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers
    )
    real_id = real.json()["id"]
    res = await client.get(
        f"/api/v1/sessions/active?deck_id={deck['id']}", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["id"] == real_id


async def test_list_sessions_excludes_preview(client, auth_headers):
    """`GET /sessions` is the back end for the (future) sessions history UI —
    preview sessions are clutter there too."""
    deck = await _create_deck(client, auth_headers)
    real = await client.post(
        "/api/v1/sessions", json={"deck_id": deck["id"]}, headers=auth_headers
    )
    await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 1},
        headers=auth_headers,
    )

    res = await client.get("/api/v1/sessions", headers=auth_headers)
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()]
    assert ids == [real.json()["id"]]


async def test_preview_rejects_audience_count_out_of_range(client, auth_headers):
    deck = await _create_deck(client, auth_headers)
    too_few = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 0},
        headers=auth_headers,
    )
    assert too_few.status_code == 422
    too_many = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 6},
        headers=auth_headers,
    )
    assert too_many.status_code == 422


async def test_preview_requires_owned_deck(client, auth_headers, seeded_user, fake_supabase_auth):
    from slaides.db.base import get_session_factory
    from slaides.db import models

    factory = get_session_factory()
    async with factory() as db:
        ws = models.Workspace(name="Other Workspace Preview")
        db.add(ws)
        await db.flush()
        other = models.AppUser(
            workspace_id=ws.id,
            email="eve@example.com",
            role="owner",
        )
        db.add(other)
        await db.commit()
    fake_supabase_auth.add_user(
        email="eve@example.com",
        password="hunter2",
        user_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
    )

    deck = await _create_deck(client, auth_headers)
    other_token = (
        await client.post(
            "/api/v1/auth/signin",
            json={"email": "eve@example.com", "password": "hunter2"},
        )
    ).json()["access"]
    res = await client.post(
        "/api/v1/sessions/preview",
        json={"deck_id": deck["id"], "audience_count": 1},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res.status_code == 404


async def test_invalid_poll_spec_rejected(client, auth_headers):
    session = await _new_session(client, auth_headers)
    # Only one choice — schema requires min 2.
    res = await client.post(
        f"/api/v1/sessions/{session['id']}/interactions",
        json={"kind": "poll", "spec": {"type": "poll", "question": "?", "choices": [{"id": "c1", "label": "Only"}]}},
        headers=auth_headers,
    )
    assert res.status_code == 422
