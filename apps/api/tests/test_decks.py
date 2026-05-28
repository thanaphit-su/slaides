from __future__ import annotations


async def test_create_and_list_deck(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "My deck"}, headers=auth_headers)
    assert create.status_code == 201
    deck = create.json()
    assert deck["title"] == "My deck"
    assert len(deck["slides"]) == 1
    assert deck["slides"][0]["position"] == 0

    listed = await client.get("/api/v1/decks", headers=auth_headers)
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == deck["id"]
    assert items[0]["slide_count"] == 1
    assert items[0]["preview_markdown"] == "# Untitled\n"
    assert items[0]["preview_kicker"] is None


async def test_get_patch_delete_deck(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "X"}, headers=auth_headers)
    deck_id = create.json()["id"]

    patched = await client.patch(
        f"/api/v1/decks/{deck_id}", json={"title": "X — renamed"}, headers=auth_headers
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "X — renamed"

    got = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["title"] == "X — renamed"

    delete = await client.delete(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert delete.status_code == 204

    missing = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert missing.status_code == 404

    listed = await client.get("/api/v1/decks", headers=auth_headers)
    assert listed.status_code == 200
    assert deck_id not in {item["id"] for item in listed.json()}


async def test_delete_deck_persists_with_session_and_widget_rows(client, auth_headers, seeded_user):
    """Workspace deck deletion must survive refresh even when runtime rows exist.

    The UI removes the card after DELETE succeeds, then reloads /decks on page
    refresh. This regression test verifies the backend commit really persists
    for decks that have the related rows production decks usually collect.
    """
    from sqlalchemy import select as _select

    from slaides.db import models
    from slaides.db.base import get_session_factory

    create = await client.post("/api/v1/decks", json={"title": "Delete me"}, headers=auth_headers)
    assert create.status_code == 201
    deck = create.json()
    deck_id = deck["id"]
    slide_id = deck["slides"][0]["id"]

    session_res = await client.post(
        "/api/v1/sessions",
        json={"deck_id": deck_id},
        headers=auth_headers,
    )
    assert session_res.status_code == 201, session_res.text
    session_id = session_res.json()["id"]

    factory = get_session_factory()
    async with factory() as db:
        import uuid as _uuid

        widget = models.Widget(
            deck_id=_uuid.UUID(deck_id),
            name="Deck delete widget",
            kind="deck-delete-widget",
            description=None,
            html="<div>Widget</div>",
            js=None,
            css=None,
            props_schema={},
            tags=[],
            version="v0.1",
        )
        db.add(widget)
        await db.flush()
        db.add(
            models.SlideWidget(
                slide_id=_uuid.UUID(slide_id),
                placement_id="delete-test",
                widget_id=widget.id,
                props={},
                position=0,
            )
        )
        db.add(
            models.Participant(
                session_id=_uuid.UUID(session_id),
                email="audience@example.com",
                display_name="Audience",
                anon=False,
                ref="audience-ref",
            )
        )
        db.add(
            models.Question(
                session_id=_uuid.UUID(session_id),
                slide_id=_uuid.UUID(slide_id),
                participant_ref="audience-ref",
                anon=False,
                text="Question",
            )
        )
        db.add(
            models.InteractionLog(
                session_id=_uuid.UUID(session_id),
                slide_id=_uuid.UUID(slide_id),
                participant_ref="audience-ref",
                kind="vote",
                payload={"choice": 1},
            )
        )
        db.add(
            models.SessionSlide(
                session_id=_uuid.UUID(session_id),
                parent_slide_id=_uuid.UUID(slide_id),
                widget_id=widget.id,
                position=0,
                kind="poll",
                spec={},
                results={},
            )
        )
        db.add(
            models.LlmCall(
                workspace_id=seeded_user["workspace_id"],
                user_id=seeded_user["user_id"],
                session_id=_uuid.UUID(session_id),
                purpose="interpret",
                model="test-model",
            )
        )
        await db.commit()

    delete = await client.delete(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert delete.status_code == 204, delete.text

    missing = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert missing.status_code == 404

    listed = await client.get("/api/v1/decks", headers=auth_headers)
    assert listed.status_code == 200
    assert deck_id not in {item["id"] for item in listed.json()}

    async with factory() as db:
        assert (await db.execute(_select(models.Slide))).scalars().all() == []
        assert (await db.execute(_select(models.Section))).scalars().all() == []
        assert (await db.execute(_select(models.Deck))).scalars().all() == []
        assert (await db.execute(_select(models.Session))).scalars().all() == []
        assert (await db.execute(_select(models.Participant))).scalars().all() == []
        assert (await db.execute(_select(models.Question))).scalars().all() == []
        assert (await db.execute(_select(models.InteractionLog))).scalars().all() == []
        assert (await db.execute(_select(models.SessionSlide))).scalars().all() == []
        assert (await db.execute(_select(models.SlideWidget))).scalars().all() == []
        llm_call = (await db.execute(_select(models.LlmCall))).scalars().one()
        assert llm_call.session_id is None


async def test_slide_update_does_not_split(client, auth_headers):
    """User typing must NEVER auto-split a slide. Multiple H1s in the markdown
    are stored verbatim on the same slide; new slides are created only via the
    explicit insert endpoint."""
    create = await client.post("/api/v1/decks", json={"title": "No splitter"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    first_slide_id = deck["slides"][0]["id"]

    body = {"markdown": "# Alpha\nLine.\n\n# Beta\nWord.\n\n# Gamma\nEnd."}
    res = await client.put(
        f"/api/v1/decks/{deck_id}/slides/{first_slide_id}", json=body, headers=auth_headers
    )
    assert res.status_code == 200
    slides_after = res.json()["slides"]
    assert len(slides_after) == 1
    assert slides_after[0]["id"] == first_slide_id
    assert slides_after[0]["markdown"] == body["markdown"]

    full = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert len(full.json()["slides"]) == 1


async def test_create_and_delete_slide(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Slides"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]

    inserted = await client.post(
        f"/api/v1/decks/{deck_id}/slides",
        json={"position": 0, "markdown": "# New\n"},
        headers=auth_headers,
    )
    assert inserted.status_code == 201

    full = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    slides = full.json()["slides"]
    assert len(slides) == 2
    assert slides[0]["markdown"].startswith("# New")

    delete = await client.delete(
        f"/api/v1/decks/{deck_id}/slides/{slides[1]['id']}", headers=auth_headers
    )
    assert delete.status_code == 204
    full2 = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert len(full2.json()["slides"]) == 1
    assert full2.json()["slides"][0]["position"] == 0


async def test_export_then_import_round_trip(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Round trip"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    slide_id = deck["slides"][0]["id"]
    await client.put(
        f"/api/v1/decks/{deck_id}/slides/{slide_id}",
        json={"markdown": "# Hello *world*\n\nA paragraph.\n", "kicker": "Intro"},
        headers=auth_headers,
    )

    export = await client.post(f"/api/v1/decks/{deck_id}/export", headers=auth_headers)
    assert export.status_code == 200
    blob = export.content
    assert blob[:2] == b"PK"

    imported = await client.post(
        "/api/v1/decks/import",
        files={"file": ("deck.slaides", blob, "application/zip")},
        headers=auth_headers,
    )
    assert imported.status_code == 201, imported.text
    new_deck = imported.json()
    assert new_deck["title"] == "Round trip"
    assert any("Hello *world*" in s["markdown"] for s in new_deck["slides"])
    assert new_deck["slides"][0]["kicker"] == "Intro"


async def test_duplicate_deck(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Original"}, headers=auth_headers)
    deck_id = create.json()["id"]
    dup = await client.post(f"/api/v1/decks/{deck_id}/duplicate", headers=auth_headers)
    assert dup.status_code == 200
    assert dup.json()["title"] == "Original (copy)"


async def test_section_crud_and_reorder(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Sections"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    # Deck creation already produces one default section at position 0.
    assert len(deck["sections"]) == 1
    default_section = deck["sections"][0]
    assert default_section["position"] == 0

    # Create two more sections.
    a = await client.post(
        f"/api/v1/decks/{deck_id}/sections",
        json={"title": "Alpha"},
        headers=auth_headers,
    )
    assert a.status_code == 201
    assert a.json()["position"] == 1
    b = await client.post(
        f"/api/v1/decks/{deck_id}/sections",
        json={"title": "Beta", "position": 0},
        headers=auth_headers,
    )
    assert b.status_code == 201
    assert b.json()["position"] == 0

    full = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    titles_in_order = [s["title"] for s in full.json()["sections"]]
    assert titles_in_order == ["Beta", "Untitled section", "Alpha"]

    # Rename.
    rename = await client.patch(
        f"/api/v1/decks/{deck_id}/sections/{a.json()['id']}",
        json={"title": "Alpha — renamed"},
        headers=auth_headers,
    )
    assert rename.status_code == 200
    assert rename.json()["title"] == "Alpha — renamed"

    # Bulk reorder.
    order = [a.json()["id"], default_section["id"], b.json()["id"]]
    reorder = await client.post(
        f"/api/v1/decks/{deck_id}/sections/reorder",
        json={"order": order},
        headers=auth_headers,
    )
    assert reorder.status_code == 200
    reordered = reorder.json()
    assert [s["id"] for s in reordered] == order
    assert [s["position"] for s in reordered] == [0, 1, 2]

    # Reorder with missing/extra ids rejects.
    bad = await client.post(
        f"/api/v1/decks/{deck_id}/sections/reorder",
        json={"order": [a.json()["id"]]},
        headers=auth_headers,
    )
    assert bad.status_code == 400


async def test_section_delete_unsections_slides(client, auth_headers):
    """Deleting a section nulls section_id on its slides instead of cascading."""
    create = await client.post("/api/v1/decks", json={"title": "Detach"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    default_section = deck["sections"][0]
    default_slide_id = deck["slides"][0]["id"]
    assert deck["slides"][0]["section_id"] == default_section["id"]

    delete = await client.delete(
        f"/api/v1/decks/{deck_id}/sections/{default_section['id']}",
        headers=auth_headers,
    )
    assert delete.status_code == 204

    after = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    body = after.json()
    assert body["sections"] == []
    # The slide survives; its section_id is now NULL.
    surviving = [s for s in body["slides"] if s["id"] == default_slide_id]
    assert len(surviving) == 1
    assert surviving[0]["section_id"] is None


async def test_delete_slide_clears_session_references(client, auth_headers):
    """Deleting a slide must null out FK columns on question/interaction_log/session_slide
    so historical session rows survive without violating the FK."""
    from slaides.db.base import get_session_factory
    from slaides.db import models

    create = await client.post(
        "/api/v1/decks",
        json={"title": "With sessions"},
        headers=auth_headers,
    )
    deck = create.json()
    deck_id = deck["id"]
    # Add a second slide so we can delete the first one.
    extra = await client.post(
        f"/api/v1/decks/{deck_id}/slides",
        json={"position": 1, "markdown": "# Second\n"},
        headers=auth_headers,
    )
    assert extra.status_code == 201

    first_slide_id = deck["slides"][0]["id"]

    # Start a session and write a question + interaction_log + session_slide
    # all referencing the slide we're about to delete.
    session_res = await client.post(
        "/api/v1/sessions",
        json={"deck_id": deck_id},
        headers=auth_headers,
    )
    session_id = session_res.json()["id"]

    factory = get_session_factory()
    async with factory() as db:
        import uuid as _uuid

        db.add(
            models.Question(
                session_id=_uuid.UUID(session_id),
                slide_id=_uuid.UUID(first_slide_id),
                participant_ref="abc",
                anon=False,
                text="A question.",
            )
        )
        db.add(
            models.InteractionLog(
                session_id=_uuid.UUID(session_id),
                slide_id=_uuid.UUID(first_slide_id),
                participant_ref="abc",
                kind="vote",
                payload={"option": 0},
            )
        )
        db.add(
            models.SessionSlide(
                session_id=_uuid.UUID(session_id),
                parent_slide_id=_uuid.UUID(first_slide_id),
                position=0,
                kind="poll",
                spec={},
                results={},
            )
        )
        await db.commit()

    # Delete the slide — must NOT throw FK violation.
    delete = await client.delete(
        f"/api/v1/decks/{deck_id}/slides/{first_slide_id}",
        headers=auth_headers,
    )
    assert delete.status_code == 204, delete.text

    # And the historical rows survive with slide_id = NULL.
    async with factory() as db:
        from sqlalchemy import select as _select

        q = (await db.execute(_select(models.Question))).scalars().first()
        assert q is not None
        assert q.slide_id is None
        il = (await db.execute(_select(models.InteractionLog))).scalars().first()
        assert il is not None
        assert il.slide_id is None
        ss = (await db.execute(_select(models.SessionSlide))).scalars().first()
        assert ss is not None
        assert ss.parent_slide_id is None


async def test_slide_reorder_across_sections(client, auth_headers):
    """Reorder rewrites positions and can reassign section_id in one call."""
    create = await client.post("/api/v1/decks", json={"title": "Reorder"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    default_section_id = deck["sections"][0]["id"]
    s1_id = deck["slides"][0]["id"]

    # Create a second section + two more slides.
    sec2 = await client.post(
        f"/api/v1/decks/{deck_id}/sections",
        json={"title": "Two"},
        headers=auth_headers,
    )
    sec2_id = sec2.json()["id"]
    s2 = await client.post(
        f"/api/v1/decks/{deck_id}/slides",
        json={"position": 1, "markdown": "# B\n"},
        headers=auth_headers,
    )
    s2_id = s2.json()["id"]
    s3 = await client.post(
        f"/api/v1/decks/{deck_id}/slides",
        json={"position": 2, "markdown": "# C\n"},
        headers=auth_headers,
    )
    s3_id = s3.json()["id"]

    # Reorder: put s3 first (in section 2), then s1, then s2 (in section 2).
    reorder = await client.post(
        f"/api/v1/decks/{deck_id}/slides/reorder",
        json={
            "order": [
                {"id": s3_id, "section_id": sec2_id},
                {"id": s1_id, "section_id": default_section_id},
                {"id": s2_id, "section_id": sec2_id},
            ]
        },
        headers=auth_headers,
    )
    assert reorder.status_code == 200, reorder.text
    slides = reorder.json()
    assert [s["id"] for s in slides] == [s3_id, s1_id, s2_id]
    assert [s["position"] for s in slides] == [0, 1, 2]
    assert [s["section_id"] for s in slides] == [sec2_id, default_section_id, sec2_id]

    # Missing slide in payload → 400.
    bad = await client.post(
        f"/api/v1/decks/{deck_id}/slides/reorder",
        json={"order": [{"id": s1_id, "section_id": None}]},
        headers=auth_headers,
    )
    assert bad.status_code == 400

    # section_id from another deck → 400.
    other_deck = await client.post(
        "/api/v1/decks", json={"title": "Other"}, headers=auth_headers
    )
    other_section_id = other_deck.json()["sections"][0]["id"]
    bad2 = await client.post(
        f"/api/v1/decks/{deck_id}/slides/reorder",
        json={
            "order": [
                {"id": s1_id, "section_id": other_section_id},
                {"id": s2_id, "section_id": sec2_id},
                {"id": s3_id, "section_id": sec2_id},
            ]
        },
        headers=auth_headers,
    )
    assert bad2.status_code == 400


async def test_section_cross_workspace_rejected(client, auth_headers, app_with_db, fake_supabase_auth):
    """A section belonging to another workspace's deck returns 404, never leaks."""
    from slaides.db.base import get_session_factory
    from slaides.db import models

    create = await client.post("/api/v1/decks", json={"title": "Mine"}, headers=auth_headers)
    deck_id = create.json()["id"]
    section_id = create.json()["sections"][0]["id"]

    # Spin up a second workspace + user and sign in as them.
    factory = get_session_factory()
    async with factory() as session:
        ws2 = models.Workspace(name="Other Workspace")
        session.add(ws2)
        await session.flush()
        other = models.AppUser(
            workspace_id=ws2.id,
            email="bob@example.com",
            display_name="Bob",
            role="owner",
        )
        session.add(other)
        await session.commit()
    fake_supabase_auth.add_user(
        email="bob@example.com",
        password="hunter2",
        user_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    signin = await client.post(
        "/api/v1/auth/signin",
        json={"email": "bob@example.com", "password": "hunter2"},
    )
    other_headers = {"Authorization": f"Bearer {signin.json()['access']}"}

    res = await client.patch(
        f"/api/v1/decks/{deck_id}/sections/{section_id}",
        json={"title": "stolen"},
        headers=other_headers,
    )
    assert res.status_code == 404
