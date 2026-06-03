from __future__ import annotations

import uuid


async def _new_deck(client, auth_headers, title: str = "T") -> dict:
    res = await client.post("/api/v1/decks", json={"title": title}, headers=auth_headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _create_widget(client, auth_headers, deck_id: str, **overrides) -> dict:
    body = {"name": "W", "kind": "custom", "html": "<p>w</p>"}
    body.update(overrides)
    res = await client.post(
        f"/api/v1/decks/{deck_id}/widgets", json=body, headers=auth_headers
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_widget_crud(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Widgety")
    create = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Quick poll",
            "kind": "poll",
            "description": "A test poll",
            "html": "<p>hi</p>",
            "tags": ["live"],
        },
        headers=auth_headers,
    )
    assert create.status_code == 201
    w = create.json()
    assert w["kind"] == "poll"
    assert w["html"] == "<p>hi</p>"
    assert w["tags"] == ["live"]
    assert w["deck_id"] == deck["id"]
    assert w["behavior"]["kind"] == "quiet"

    # Workspace-wide listing returns widgets across all decks.
    listed = await client.get("/api/v1/widgets", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == w["id"] for item in listed.json())

    # Deck-scoped listing only returns widgets in this deck.
    deck_listed = await client.get(
        f"/api/v1/decks/{deck['id']}/widgets", headers=auth_headers
    )
    assert deck_listed.status_code == 200
    assert {item["id"] for item in deck_listed.json()} == {w["id"]}

    patched = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={"name": "Renamed", "html": "<p>updated</p>"},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["html"] == "<p>updated</p>"

    deleted = await client.delete(f"/api/v1/widgets/{w['id']}", headers=auth_headers)
    assert deleted.status_code == 204


async def test_widget_api_baseline_keeps_flat_source_shape(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Baseline")
    w = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Baseline widget",
        kind="custom",
        html="<section>one</section>",
        js="console.log('one');",
        css="section{color:var(--foreground)}",
        props_schema={"title": {"type": "string"}},
        behavior={"kind": "quiet"},
    )
    fetched = await client.get(f"/api/v1/widgets/{w['id']}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["html"] == "<section>one</section>"
    assert body["js"] == "console.log('one');"
    assert body["css"] == "section{color:var(--foreground)}"
    assert body["props_schema"] == {"title": {"type": "string"}}
    assert body["behavior"] == {"kind": "quiet"}


async def test_widget_create_returns_current_revision_and_ai_fields(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Revisioned")
    res = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Revisioned poll",
            "kind": "poll",
            "html": "<section>poll</section>",
            "js": "window.slaides?.contribute?.('a');",
            "css": ".poll{color:var(--foreground)}",
            "props_schema": {"question": {"type": "string", "default": "Pick one"}},
            "example_props": {"question": "Lunch?"},
            "ai_spec": {"intent": "Audience chooses one lunch option"},
            "behavior": {
                "kind": "loud",
                "aggregator": "tally",
                "contribution_schema": {"type": "string"},
            },
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["current_revision_id"]
    assert body["html"] == "<section>poll</section>"
    assert body["example_props"] == {"question": "Lunch?"}
    assert body["ai_spec"]["intent"] == "Audience chooses one lunch option"
    assert body["behavior"]["kind"] == "loud"


async def test_create_loud_widget_requires_valid_aggregator_and_contribution_schema(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Bad loud")
    res = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Bad loud",
            "kind": "poll",
            "html": "<section>x</section>",
            "behavior": {"kind": "loud"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "aggregator" in res.text


async def test_create_collect_widget_normalises_behavior(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Collect")
    res = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Question Board",
            "kind": "custom",
            "html": "<section>board</section>",
            "js": (
                "if (window.slaides.role === 'instructor') {"
                "  window.slaides.on('state', function(){});"
                "} else {"
                "  window.slaides.contribute('hi');"
                "}"
            ),
            "behavior": {
                "kind": "collect",
                "contribution_schema": {"type": "string"},
            },
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    # The AI doesn't pick an aggregator for collect — the server fixes it.
    assert body["behavior"]["kind"] == "collect"
    assert body["behavior"]["aggregator"] == "collect"
    assert body["behavior"]["contribution_schema"] == {"type": "string"}


async def test_create_collect_widget_requires_contribution_schema(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Bad collect")
    res = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Bad collect",
            "kind": "custom",
            "html": "<section>x</section>",
            "behavior": {"kind": "collect"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "contribution_schema" in res.text


async def test_patch_widget_can_swap_quiet_to_loud(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Swap")
    w = await _create_widget(client, auth_headers, deck["id"], name="Quiet", kind="custom")
    res = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={
            "behavior": {
                "kind": "loud",
                "aggregator": "append",
                "contribution_schema": {"type": "object"},
            },
            "js": "window.slaides.contribute({text:'hello'}); window.slaides.on('state', function(){});",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["behavior"]["kind"] == "loud"
    assert res.json()["behavior"]["aggregator"] == "append"


async def test_widget_ai_thread_persists_messages(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Thread")
    w = await _create_widget(client, auth_headers, deck["id"], name="Threaded")
    create_thread = await client.post(
        f"/api/v1/widgets/{w['id']}/ai-thread",
        json={"title": "Build poll", "compact_summary": {"intent": "poll"}},
        headers=auth_headers,
    )
    assert create_thread.status_code == 201, create_thread.text
    thread = create_thread.json()
    add_message = await client.post(
        f"/api/v1/widgets/{w['id']}/ai-thread/{thread['id']}/messages",
        json={
            "role": "assistant",
            "message_type": "plan",
            "content": {"steps": ["infer behavior", "draft widget"]},
        },
        headers=auth_headers,
    )
    assert add_message.status_code == 201, add_message.text
    listed = await client.get(f"/api/v1/widgets/{w['id']}/ai-thread", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["messages"][0]["message_type"] == "plan"


async def test_widget_patch_creates_new_revision_and_rollback_restores_old_source(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Rollback")
    w = await _create_widget(client, auth_headers, deck["id"], name="R", html="<p>v1</p>")
    v1 = w["current_revision_id"]
    patched = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={"html": "<p>v2</p>", "ai_spec": {"summary": "second"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    v2 = patched.json()["current_revision_id"]
    assert v2 != v1
    history = await client.get(f"/api/v1/widgets/{w['id']}/revisions", headers=auth_headers)
    assert history.status_code == 200
    assert [r["version_number"] for r in history.json()] == [1, 2]
    rollback = await client.post(
        f"/api/v1/widgets/{w['id']}/revisions/{v1}/rollback",
        headers=auth_headers,
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["html"] == "<p>v1</p>"


async def test_attach_widget_to_slide_and_one_max(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Widgety")
    slide_id = deck["slides"][0]["id"]
    w1 = await _create_widget(client, auth_headers, deck["id"], name="Poll A", kind="poll")

    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "p1", "widget_id": w1["id"], "props": {"q": "hi"}},
        headers=auth_headers,
    )
    assert attach.status_code == 201, attach.text
    body = attach.json()
    assert body["placement_id"] == "p1"
    assert body["kind"] == "poll"

    # Markdown should now contain the placeholder.
    deck_after = await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)
    target = next(s for s in deck_after.json()["slides"] if s["id"] == slide_id)
    assert "{{widget:p1}}" in target["markdown"]
    assert target["widgets"][0]["placement_id"] == "p1"

    # Second attach must fail with 409 — one widget per slide.
    w2 = await _create_widget(client, auth_headers, deck["id"], name="Poll B", kind="poll")
    second = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "p2", "widget_id": w2["id"]},
        headers=auth_headers,
    )
    assert second.status_code == 409

    # Detach removes the placement and strips the markdown placeholder.
    detach = await client.delete(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/p1", headers=auth_headers
    )
    assert detach.status_code == 204

    deck_final = await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)
    target = next(s for s in deck_final.json()["slides"] if s["id"] == slide_id)
    assert "{{widget:p1}}" not in target["markdown"]
    assert target["widgets"] == []


async def test_attach_widget_defaults_to_example_props(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Example props")
    slide_id = deck["slides"][0]["id"]
    widget = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Card",
        props_schema={"title": {"type": "string"}},
        example_props={"title": "Preview title"},
    )
    res = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "card-1", "widget_id": widget["id"]},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["props"] == {"title": "Preview title"}


async def test_attach_rejects_widget_from_another_deck(client, auth_headers):
    deck_a = await _new_deck(client, auth_headers, "A")
    deck_b = await _new_deck(client, auth_headers, "B")
    widget_in_a = await _create_widget(client, auth_headers, deck_a["id"], name="A-widget")

    cross = await client.post(
        f"/api/v1/decks/{deck_b['id']}/slides/{deck_b['slides'][0]['id']}/widgets",
        json={"placement_id": "p-x", "widget_id": widget_in_a["id"]},
        headers=auth_headers,
    )
    assert cross.status_code == 409
    detail = cross.json()["detail"]
    assert detail["error"] == "cross_deck_attach"


async def test_copy_widget_into_another_deck_tracks_lineage(client, auth_headers):
    deck_a = await _new_deck(client, auth_headers, "A")
    deck_b = await _new_deck(client, auth_headers, "B")
    source = await _create_widget(
        client, auth_headers, deck_a["id"], name="Original", html="<p>orig</p>"
    )

    copy = await client.post(
        f"/api/v1/decks/{deck_b['id']}/widgets/copy",
        json={"source_widget_id": source["id"]},
        headers=auth_headers,
    )
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["id"] != source["id"]
    assert body["deck_id"] == deck_b["id"]
    assert body["derived_from_id"] == source["id"]
    assert body["name"] == "Original"
    assert body["html"] == "<p>orig</p>"
    assert body["current_revision_id"]

    # Editing the source does NOT mutate the copy.
    await client.patch(
        f"/api/v1/widgets/{source['id']}",
        json={"html": "<p>changed source</p>"},
        headers=auth_headers,
    )
    after_copy = await client.get(f"/api/v1/widgets/{body['id']}", headers=auth_headers)
    assert after_copy.json()["html"] == "<p>orig</p>"


async def test_copy_widget_in_same_deck_creates_variant_with_suffix(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Variants")
    source = await _create_widget(
        client, auth_headers, deck["id"], name="Poll", html="<p>poll</p>"
    )

    # First in-deck duplicate → " (copy)" suffix.
    first = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets/copy",
        json={"source_widget_id": source["id"]},
        headers=auth_headers,
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["id"] != source["id"]
    assert first_body["deck_id"] == deck["id"]
    assert first_body["derived_from_id"] == source["id"]
    assert first_body["name"] == "Poll (copy)"
    assert first_body["html"] == "<p>poll</p>"
    assert first_body["current_revision_id"]

    # Editing the source does NOT mutate the in-deck clone.
    await client.patch(
        f"/api/v1/widgets/{source['id']}",
        json={"html": "<p>changed</p>"},
        headers=auth_headers,
    )
    after = await client.get(f"/api/v1/widgets/{first_body['id']}", headers=auth_headers)
    assert after.json()["html"] == "<p>poll</p>"

    # Second in-deck duplicate of the same source → " (copy 2)".
    second = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets/copy",
        json={"source_widget_id": source["id"]},
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["name"] == "Poll (copy 2)"

    # And a third → " (copy 3)".
    third = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets/copy",
        json={"source_widget_id": source["id"]},
        headers=auth_headers,
    )
    assert third.status_code == 201, third.text
    assert third.json()["name"] == "Poll (copy 3)"


async def test_patch_placement_props_validates_against_schema(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Props")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Quiz",
        kind="poll",
        html="<section></section>",
        props_schema={
            "properties": {
                "question": {"type": "string", "minLength": 1, "default": "Pick"},
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                        },
                    },
                    "default": [],
                },
                "correct_answer": {"type": "string", "enum.from": "choices.id"},
            }
        },
    )

    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={
            "placement_id": "quiz-1",
            "widget_id": w["id"],
            "props": {
                "question": "Capital of France?",
                "choices": [
                    {"id": "a", "label": "Paris"},
                    {"id": "b", "label": "Rome"},
                ],
                "correct_answer": "a",
            },
        },
        headers=auth_headers,
    )
    assert attach.status_code == 201, attach.text

    patched = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/quiz-1",
        json={
            "props": {
                "question": "Capital of Italy?",
                "choices": [
                    {"id": "a", "label": "Paris"},
                    {"id": "b", "label": "Rome"},
                ],
                "correct_answer": "b",
            }
        },
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["props"]["question"] == "Capital of Italy?"
    assert patched.json()["props"]["correct_answer"] == "b"

    bad_type = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/quiz-1",
        json={"props": {"question": 42}},
        headers=auth_headers,
    )
    assert bad_type.status_code == 422
    assert "question" in bad_type.json()["detail"]

    bad_enum = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/quiz-1",
        json={
            "props": {
                "choices": [{"id": "a", "label": "Paris"}],
                "correct_answer": "z",
            }
        },
        headers=auth_headers,
    )
    assert bad_enum.status_code == 422
    assert "correct_answer" in bad_enum.json()["detail"]


async def test_patch_placement_props_404_for_missing_placement(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "x")
    res = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{deck['slides'][0]['id']}/widgets/never",
        json={"props": {}},
        headers=auth_headers,
    )
    assert res.status_code == 404


async def test_widget_export_import_round_trip(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Import target")
    create = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Round trip widget",
            "kind": "custom",
            "description": "for tests",
            "html": "<p>html</p>",
            "js": "console.log('x');",
            "css": "p { color: red; }",
            "tags": ["test"],
        },
        headers=auth_headers,
    )
    widget_id = create.json()["id"]

    export = await client.post(f"/api/v1/widgets/{widget_id}/export", headers=auth_headers)
    assert export.status_code == 200
    assert b"slaides-widget" in export.content

    imported = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets/import",
        files={"file": ("widget.swidget", export.content, "text/html")},
        headers=auth_headers,
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["deck_id"] == deck["id"]
    assert body["name"] == "Round trip widget"
    assert body["html"].strip() == "<p>html</p>"
    assert "console.log" in body["js"]
    assert "color: red" in body["css"]
    assert body["tags"] == ["test"]


async def test_widget_export_import_preserves_behavior_spec_and_example_props(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Export contract")
    create = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets",
        json={
            "name": "Export loud",
            "kind": "poll",
            "html": "<section>x</section>",
            "example_props": {"question": "Q?"},
            "ai_spec": {"intent": "shared poll"},
            "behavior": {
                "kind": "loud",
                "aggregator": "tally",
                "contribution_schema": {"type": "string"},
            },
        },
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    widget_id = create.json()["id"]

    export = await client.post(f"/api/v1/widgets/{widget_id}/export", headers=auth_headers)
    assert export.status_code == 200, export.text
    imported = await client.post(
        f"/api/v1/decks/{deck['id']}/widgets/import",
        files={"file": ("widget.swidget", export.content, "text/html")},
        headers=auth_headers,
    )

    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["behavior"]["kind"] == "loud"
    assert body["behavior"]["aggregator"] == "tally"
    assert body["example_props"] == {"question": "Q?"}
    assert body["ai_spec"] == {"intent": "shared poll"}


async def test_delete_widget_conflicts_when_in_use(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Use it")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(client, auth_headers, deck["id"], name="In-use", kind="poll")

    attach_res = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "in-use-1", "widget_id": w["id"], "props": {}},
        headers=auth_headers,
    )
    assert attach_res.status_code == 201

    conflict = await client.delete(f"/api/v1/widgets/{w['id']}", headers=auth_headers)
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["error"] == "widget_in_use"
    assert detail["usage_count"] == 1

    listed = await client.get("/api/v1/widgets", headers=auth_headers)
    assert any(item["id"] == w["id"] for item in listed.json())
    slide_after = (await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)).json()["slides"][0]
    assert "{{widget:in-use-1}}" in slide_after["markdown"]


async def test_delete_widget_force_cascades_and_strips_placeholders(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Force it")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(client, auth_headers, deck["id"], name="Cascade", kind="poll")

    attach_res = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "force-1", "widget_id": w["id"], "props": {}},
        headers=auth_headers,
    )
    assert attach_res.status_code == 201

    deleted = await client.delete(
        f"/api/v1/widgets/{w['id']}?force=true", headers=auth_headers
    )
    assert deleted.status_code == 204

    listed = await client.get("/api/v1/widgets", headers=auth_headers)
    assert all(item["id"] != w["id"] for item in listed.json())
    slide_after = (await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)).json()["slides"][0]
    assert "{{widget:force-1}}" not in slide_after["markdown"]
    assert slide_after["widgets"] == []


async def test_delete_widget_clears_ai_thread_messages_before_revisions(client, auth_headers):
    """Regression: deleting a widget that has an AI thread with messages
    referencing its revisions must not leave the messages pointing at a
    cascade-deleted revision. SQLite tests don't enforce the FK, but Postgres
    rejected the chain because `widget_ai_message.revision_id` (NO ACTION)
    blocked the `widget_revision` cascade before the thread cascade cleared
    the messages. Endpoint must drop the threads explicitly first."""
    deck = await _new_deck(client, auth_headers, "AI thread delete")
    w = await _create_widget(client, auth_headers, deck["id"], name="WithThread", kind="poll")

    thread = (
        await client.post(
            f"/api/v1/widgets/{w['id']}/ai-thread",
            json={"title": "draft", "compact_summary": {}},
            headers=auth_headers,
        )
    ).json()
    msg = await client.post(
        f"/api/v1/widgets/{w['id']}/ai-thread/{thread['id']}/messages",
        json={
            "role": "assistant",
            "message_type": "plan",
            "content": {"text": "v1"},
            "revision_id": w["current_revision_id"],
        },
        headers=auth_headers,
    )
    assert msg.status_code == 201, msg.text

    deleted = await client.delete(f"/api/v1/widgets/{w['id']}", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text
    listed = await client.get("/api/v1/widgets", headers=auth_headers)
    assert all(item["id"] != w["id"] for item in listed.json())


async def _seed_open_placement_state(
    deck_id: str, widget_id: str, *, placement_id: str = "live-1", code: str = "SLD-LIVE"
) -> str:
    """Create an open session + placement_state row for `widget_id`. Returns
    the session id as a string."""
    from slaides.db.base import get_session_factory
    from slaides.db import models as _m

    factory = get_session_factory()
    async with factory() as db:
        deck_row = (
            await db.execute(_m.Deck.__table__.select().where(_m.Deck.id == uuid.UUID(deck_id)))
        ).first()
        sess = _m.Session(
            deck_id=deck_row.id,
            owner_id=deck_row.owner_id,
            workspace_id=deck_row.workspace_id,
            code=code,
            salt="s",
        )
        db.add(sess)
        await db.flush()
        db.add(
            _m.PlacementState(
                session_id=sess.id,
                placement_id=placement_id,
                widget_id=uuid.UUID(widget_id),
                aggregator="tally",
                state={"tally": {"a": 1}},
                contribution_count=1,
                state_version=1,
            )
        )
        await db.commit()
        return str(sess.id)


async def _count_open_placement_states(widget_id: str) -> int:
    from slaides.db.base import get_session_factory
    from slaides.db import models as _m
    from sqlalchemy import select as _select

    factory = get_session_factory()
    async with factory() as db:
        rows = (
            await db.execute(
                _select(_m.PlacementState).where(
                    _m.PlacementState.widget_id == uuid.UUID(widget_id),
                    _m.PlacementState.closed_at.is_(None),
                )
            )
        ).scalars().all()
        return len(rows)


async def test_patch_widget_any_field_blocked_while_session_open(client, auth_headers):
    """Per WIDGETS_V2 decision log, any mid-session widget edit resets the
    audience tally with a confirm. The PATCH route enforces this by refusing
    with 409 unless ?reset_state=true is set — for ALL fields, not just
    behavior. A typo fix and a behavior flip both go through the same gate."""
    deck = await _new_deck(client, auth_headers, "Live")
    loud = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Loud poll",
        kind="poll",
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    await _seed_open_placement_state(deck["id"], loud["id"])

    # Even a metadata-only edit is refused while the placement_state is open.
    blocked = await client.patch(
        f"/api/v1/widgets/{loud['id']}",
        json={"name": "Renamed"},
        headers=auth_headers,
    )
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["error"] == "edit_requires_reset"
    assert detail["open_session_count"] == 1
    assert detail["open_placement_count"] == 1

    # Behavior change is also refused under the same error code.
    blocked_b = await client.patch(
        f"/api/v1/widgets/{loud['id']}",
        json={"behavior": {"kind": "quiet"}},
        headers=auth_headers,
    )
    assert blocked_b.status_code == 409
    assert blocked_b.json()["detail"]["error"] == "edit_requires_reset"


async def test_patch_widget_with_reset_state_drops_placement_state(client, auth_headers):
    """With ?reset_state=true, the PATCH applies the edit AND drops the open
    placement_state row(s). The row deletion is what makes audience iframes
    drop their cached projection (via the widget.reset broadcast)."""
    deck = await _new_deck(client, auth_headers, "Live")
    loud = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Loud",
        kind="poll",
        behavior={
            "kind": "loud",
            "aggregator": "tally",
            "contribution_schema": {"type": "string"},
        },
    )
    await _seed_open_placement_state(deck["id"], loud["id"])
    assert await _count_open_placement_states(loud["id"]) == 1

    res = await client.patch(
        f"/api/v1/widgets/{loud['id']}?reset_state=true",
        json={"name": "Renamed live", "html": "<section>new</section>"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Renamed live"
    assert res.json()["html"] == "<section>new</section>"
    assert await _count_open_placement_states(loud["id"]) == 0


async def test_patch_widget_allowed_when_no_open_state(client, auth_headers):
    """Authoring outside a live session: PATCH any field freely."""
    deck = await _new_deck(client, auth_headers, "Quiet authoring")
    w = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Editable",
        kind="poll",
        behavior={"kind": "quiet"},
    )
    res = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={
            "behavior": {
                "kind": "loud",
                "aggregator": "tally",
                "contribution_schema": {"type": "string"},
            }
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["behavior"]["kind"] == "loud"
    assert res.json()["behavior"]["aggregator"] == "tally"


async def test_removing_widget_placeholder_from_markdown_drops_the_placement(client, auth_headers):
    """Regression: when the user manually deletes the `{{widget:...}}` line
    from the slide markdown, the SlideWidget row must be cleaned up so the
    slide stops counting as 'already has a widget' and the next attach can
    proceed instead of hitting the 1-widget-per-slide 409."""
    deck = await _new_deck(client, auth_headers, "Edit md")
    slide_id = deck["slides"][0]["id"]
    w1 = await _create_widget(client, auth_headers, deck["id"], name="First", kind="poll")
    w2 = await _create_widget(client, auth_headers, deck["id"], name="Second", kind="quiz")

    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "poll-aaaa1111", "widget_id": w1["id"], "props": {}},
        headers=auth_headers,
    )
    assert attach.status_code == 201

    # Confirm the canonical "1 widget per slide" 409 fires before the cleanup.
    blocked = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "quiz-bbbb2222", "widget_id": w2["id"], "props": {}},
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    # Simulate the user deleting the {{widget:...}} line from the markdown
    # editor — the PUT carries markdown without any placeholder.
    edited = await client.put(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}",
        json={"markdown": "# Just a heading\n\nplain text only"},
        headers=auth_headers,
    )
    assert edited.status_code == 200

    # The orphaned placement should be gone — next attach succeeds.
    second = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "quiz-bbbb2222", "widget_id": w2["id"], "props": {}},
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text


async def test_keeping_widget_placeholder_in_markdown_leaves_the_placement(client, auth_headers):
    """Round-trip: a markdown update that still contains the placeholder
    must NOT drop the row (otherwise typo fixes would silently break)."""
    deck = await _new_deck(client, auth_headers, "Keep md")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(client, auth_headers, deck["id"], name="Keep", kind="poll")
    await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "poll-keep1234", "widget_id": w["id"], "props": {}},
        headers=auth_headers,
    )
    edited = await client.put(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}",
        json={"markdown": "# Updated heading\n\n{{widget:poll-keep1234}}\n"},
        headers=auth_headers,
    )
    assert edited.status_code == 200
    returned_slide = edited.json()["slides"][0]
    assert any(p["placement_id"] == "poll-keep1234" for p in returned_slide["widgets"])

    # Placement survives — re-fetch the deck and confirm the slide widgets list
    # still has the placement_id.
    deck_after = (await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)).json()
    slide_after = next(s for s in deck_after["slides"] if s["id"] == slide_id)
    assert any(p["placement_id"] == "poll-keep1234" for p in slide_after["widgets"])


async def test_detach_gcs_orphan_drop_copy(client, auth_headers):
    """Detaching the last placement of a drop-spawned copy (a widget that
    has `derived_from_id` set and zero remaining slide_widget rows) drops
    the widget row itself. Stops the deck library from accumulating orphan
    duplicates after repeated drag-replace cycles."""
    deck_a = await _new_deck(client, auth_headers, "Source")
    source = await _create_widget(client, auth_headers, deck_a["id"], name="Carousel", kind="carousel")

    deck_b = await _new_deck(client, auth_headers, "Target")
    # Copy source into deck B → creates a derived widget row.
    copy_res = await client.post(
        f"/api/v1/decks/{deck_b['id']}/widgets/copy",
        json={"source_widget_id": source["id"]},
        headers=auth_headers,
    )
    assert copy_res.status_code == 201
    copy = copy_res.json()
    assert copy["derived_from_id"] == source["id"]

    # Attach the copy to a slide in deck B, then detach.
    slide_id = deck_b["slides"][0]["id"]
    await client.post(
        f"/api/v1/decks/{deck_b['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "carousel-aaaa1111", "widget_id": copy["id"], "props": {}},
        headers=auth_headers,
    )
    detach = await client.delete(
        f"/api/v1/decks/{deck_b['id']}/slides/{slide_id}/widgets/carousel-aaaa1111",
        headers=auth_headers,
    )
    assert detach.status_code == 204

    # The copy is GC'd — gone from the deck library.
    deck_b_after = (await client.get(f"/api/v1/decks/{deck_b['id']}/widgets", headers=auth_headers)).json()
    assert all(w["id"] != copy["id"] for w in deck_b_after)
    # Source widget in deck A is untouched.
    deck_a_after = (await client.get(f"/api/v1/decks/{deck_a['id']}/widgets", headers=auth_headers)).json()
    assert any(w["id"] == source["id"] for w in deck_a_after)


async def test_detach_keeps_hand_authored_widget(client, auth_headers):
    """A widget without `derived_from_id` is hand-authored (or seeded) — the
    user owns it via the library. Detaching from a slide must not delete
    the widget row."""
    deck = await _new_deck(client, auth_headers, "Hand")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(client, auth_headers, deck["id"], name="Mine", kind="poll")
    await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "poll-cccc3333", "widget_id": w["id"], "props": {}},
        headers=auth_headers,
    )
    detach = await client.delete(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/poll-cccc3333",
        headers=auth_headers,
    )
    assert detach.status_code == 204

    # Widget row still present in the deck library.
    deck_after = (await client.get(f"/api/v1/decks/{deck['id']}/widgets", headers=auth_headers)).json()
    assert any(item["id"] == w["id"] for item in deck_after)


async def test_detach_keeps_copy_when_other_placements_remain(client, auth_headers):
    """If the drop-spawned copy is still attached to another slide, the
    detach should NOT GC it — only the detached placement is removed."""
    deck_src = await _new_deck(client, auth_headers, "Src")
    source = await _create_widget(client, auth_headers, deck_src["id"], name="Src", kind="poll")
    deck = await _new_deck(client, auth_headers, "Multi-placements")
    copy = (
        await client.post(
            f"/api/v1/decks/{deck['id']}/widgets/copy",
            json={"source_widget_id": source["id"]},
            headers=auth_headers,
        )
    ).json()

    # Insert two slides + attach the copy to both.
    slide_a = deck["slides"][0]["id"]
    slide_b_res = await client.post(
        f"/api/v1/decks/{deck['id']}/slides",
        json={"position": 1, "markdown": "# B"},
        headers=auth_headers,
    )
    slide_b = slide_b_res.json()["id"]
    await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_a}/widgets",
        json={"placement_id": "poll-aaaa1111", "widget_id": copy["id"], "props": {}},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_b}/widgets",
        json={"placement_id": "poll-bbbb2222", "widget_id": copy["id"], "props": {}},
        headers=auth_headers,
    )
    # Detach one — the other placement keeps the widget alive.
    await client.delete(
        f"/api/v1/decks/{deck['id']}/slides/{slide_a}/widgets/poll-aaaa1111",
        headers=auth_headers,
    )
    deck_after = (await client.get(f"/api/v1/decks/{deck['id']}/widgets", headers=auth_headers)).json()
    assert any(item["id"] == copy["id"] for item in deck_after)


async def test_patch_widget_kind_is_writable(client, auth_headers):
    """`kind` is a patchable field on the widget row — previously the route's
    field loop omitted it and silently dropped the update on the floor."""
    deck = await _new_deck(client, auth_headers, "Kind patch")
    w = await _create_widget(client, auth_headers, deck["id"], name="K", kind="poll")
    assert w["kind"] == "poll"
    res = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={"kind": "quiz"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["kind"] == "quiz"


async def test_patch_placement_props_blocked_until_reset_confirmed(client, auth_headers):
    """The placement-props PATCH is governed by the same gate, scoped to the
    specific placement_id rather than every placement of the widget."""
    deck = await _new_deck(client, auth_headers, "Live props")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(
        client,
        auth_headers,
        deck["id"],
        name="Quiz",
        kind="quiz",
        props_schema={
            "type": "object",
            "properties": {"question": {"type": "string"}},
        },
    )
    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "props-live-1", "widget_id": w["id"], "props": {"question": "old"}},
        headers=auth_headers,
    )
    assert attach.status_code == 201

    await _seed_open_placement_state(deck["id"], w["id"], placement_id="props-live-1", code="SLD-PROPS")

    blocked = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/props-live-1",
        json={"props": {"question": "new"}},
        headers=auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "edit_requires_reset"

    ok = await client.patch(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets/props-live-1?reset_state=true",
        json={"props": {"question": "new"}},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["props"]["question"] == "new"
    assert await _count_open_placement_states(w["id"]) == 0
