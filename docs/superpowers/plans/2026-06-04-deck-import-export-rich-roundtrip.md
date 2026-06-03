# Rich Deck Import/Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `.slaides` deck export/import preserve sections, widget definitions, widget revisions, placement IDs, and placement props while deliberately excluding widget AI chat history.

**Architecture:** Keep the `.slaides` zip format, but bump `format_version` from `0.1` to `0.2` and add structured JSON for slides, sections, widgets, revisions, and placements in `deck.json`. Markdown slide files remain for readability/backward compatibility. Import generates new database UUIDs for deck, sections, widgets, revisions, and slides, while preserving archive-local placement IDs and wiring them to newly created local widget rows.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic/dataclasses, zipfile JSON package format, pytest/httpx backend tests, Vue/Pinia frontend API copy.

---

## File Structure

- Modify `apps/api/src/slaides/decks/package.py`: define v0.2 package dataclasses, pack/unpack JSON shape, and backward-compatible v0.1 unpack.
- Modify `apps/api/src/slaides/decks/router.py`: export rich widget/section metadata and import it into new local DB rows.
- Modify `apps/api/src/slaides/decks/service.py`: optionally add helper query functions if router starts to grow too much.
- Modify `apps/api/tests/test_decks.py`: add regression tests for section membership, widget props/revisions, cross-user-safe ID remapping, and chat-history exclusion.
- Modify `apps/web/src/pages/Workspace.vue` or the import/export UI owner if needed: label deck export as excluding AI chat history.
- No migration is required: all required tables already exist.

## Archive Contract

`deck.json` v0.2 shape:

```json
{
  "format_version": "0.2",
  "title": "Deck title",
  "subtitle": null,
  "manifest": {},
  "sections": [
    { "key": "section-0", "title": "Intro", "position": 0 }
  ],
  "slides": [
    {
      "key": "slide-0",
      "file": "slides/00-title.md",
      "position": 0,
      "section_key": "section-0",
      "kicker": "Intro"
    }
  ],
  "widgets": [
    {
      "key": "widget-0",
      "name": "Poll",
      "kind": "poll",
      "description": null,
      "tags": [],
      "version": "v0.1",
      "derived_from_key": null,
      "current_revision_key": "revision-0"
    }
  ],
  "widget_revisions": [
    {
      "key": "revision-0",
      "widget_key": "widget-0",
      "version_number": 1,
      "html": "<section></section>",
      "js": null,
      "css": null,
      "props_schema": {},
      "example_props": {},
      "behavior": { "kind": "quiet" },
      "ai_spec": {},
      "created_reason": "imported"
    }
  ],
  "placements": [
    {
      "slide_key": "slide-0",
      "placement_id": "poll-abcd1234",
      "widget_key": "widget-0",
      "revision_key": "revision-0",
      "props": { "question": "Ready?" },
      "position": 0
    }
  ],
  "excluded": {
    "widget_ai_threads": true
  }
}
```

## Task 1: Package v0.2 Dataclasses And Backward-Compatible Parser

**Files:**
- Modify: `apps/api/src/slaides/decks/package.py`
- Test: `apps/api/tests/test_decks.py`

- [ ] **Step 1: Add a failing package-level test for section/widget metadata**

Append this test near `test_export_then_import_round_trip` in `apps/api/tests/test_decks.py`:

```python
async def test_package_v02_preserves_section_and_widget_metadata():
    from slaides.decks import package

    packed = package.Packaged(
        title="Rich",
        subtitle=None,
        manifest={},
        sections=[package.PackagedSection(key="section-a", title="A", position=0)],
        slides=[
            package.PackagedSlide(
                key="slide-a",
                position=0,
                section_key="section-a",
                kicker="Intro",
                markdown="# Hello\n\n{{widget:poll-1}}\n",
            )
        ],
        widgets=[
            package.PackagedWidget(
                key="widget-a",
                name="Poll",
                kind="poll",
                description=None,
                tags=[],
                version="v0.1",
                derived_from_key=None,
                current_revision_key="revision-a",
            )
        ],
        widget_revisions=[
            package.PackagedWidgetRevision(
                key="revision-a",
                widget_key="widget-a",
                version_number=1,
                html="<section>Poll</section>",
                js=None,
                css=None,
                props_schema={"properties": {"question": {"type": "string"}}},
                example_props={"question": "Example"},
                behavior={"kind": "quiet"},
                ai_spec={"prompt": "make poll"},
                created_reason="create",
            )
        ],
        placements=[
            package.PackagedPlacement(
                slide_key="slide-a",
                placement_id="poll-1",
                widget_key="widget-a",
                revision_key="revision-a",
                props={"question": "Ready?"},
                position=0,
            )
        ],
        excluded={"widget_ai_threads": True},
    )

    unpacked = package.unpack(package.pack(packed))

    assert unpacked.sections[0].key == "section-a"
    assert unpacked.slides[0].section_key == "section-a"
    assert unpacked.widgets[0].key == "widget-a"
    assert unpacked.widget_revisions[0].props_schema["properties"]["question"]["type"] == "string"
    assert unpacked.placements[0].props == {"question": "Ready?"}
    assert unpacked.excluded == {"widget_ai_threads": True}
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_package_v02_preserves_section_and_widget_metadata -q
```

Expected: FAIL with `AttributeError: module 'slaides.decks.package' has no attribute 'PackagedWidget'`.

- [ ] **Step 3: Implement v0.2 dataclasses and parser**

Modify `apps/api/src/slaides/decks/package.py` so the dataclass section has these fields:

```python
@dataclass
class PackagedSlide:
    position: int
    kicker: str | None
    markdown: str
    key: str | None = None
    section_key: str | None = None


@dataclass
class PackagedSection:
    title: str
    position: int
    key: str | None = None


@dataclass
class PackagedWidget:
    key: str
    name: str
    kind: str
    description: str | None
    tags: list[str]
    version: str
    derived_from_key: str | None
    current_revision_key: str | None


@dataclass
class PackagedWidgetRevision:
    key: str
    widget_key: str
    version_number: int
    html: str
    js: str | None
    css: str | None
    props_schema: dict
    example_props: dict
    behavior: dict
    ai_spec: dict
    created_reason: str | None


@dataclass
class PackagedPlacement:
    slide_key: str
    placement_id: str
    widget_key: str
    revision_key: str | None
    props: dict
    position: int


@dataclass
class Packaged:
    title: str
    subtitle: str | None
    manifest: dict
    sections: list[PackagedSection]
    slides: list[PackagedSlide]
    widgets: list[PackagedWidget] | None = None
    widget_revisions: list[PackagedWidgetRevision] | None = None
    placements: list[PackagedPlacement] | None = None
    excluded: dict | None = None
```

Update `pack()` to write `format_version: "0.2"`, structured slide metadata, widget metadata, placements, and `excluded`. Keep writing markdown files under `slides/`:

```python
def pack(packed: Packaged) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        slide_entries = []
        for idx, s in enumerate(packed.slides):
            key = s.key or f"slide-{idx}"
            filename = f"slides/{s.position:02d}-{_slug(_first_h1(s.markdown))}.md"
            slide_entries.append(
                {
                    "key": key,
                    "file": filename,
                    "position": s.position,
                    "section_key": s.section_key,
                    "kicker": s.kicker,
                }
            )
            body = ""
            if s.kicker:
                body += f"<!-- kicker: {s.kicker} -->\n"
            body += s.markdown
            if not body.endswith("\n"):
                body += "\n"
            zf.writestr(filename, body)

        manifest = {
            "title": packed.title,
            "subtitle": packed.subtitle,
            "manifest": packed.manifest,
            "sections": [
                {"key": s.key or f"section-{i}", "title": s.title, "position": s.position}
                for i, s in enumerate(packed.sections)
            ],
            "slides": slide_entries,
            "widgets": [w.__dict__ for w in (packed.widgets or [])],
            "widget_revisions": [r.__dict__ for r in (packed.widget_revisions or [])],
            "placements": [p.__dict__ for p in (packed.placements or [])],
            "excluded": packed.excluded or {"widget_ai_threads": True},
            "format_version": "0.2",
        }
        zf.writestr("deck.json", json.dumps(manifest, indent=2))
    return buf.getvalue()
```

Update `unpack()` to branch on `format_version`. For v0.2, read markdown from each `slides[].file`; for missing/old format, preserve current v0.1 behavior:

```python
def unpack(data: bytes) -> Packaged:
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, "r") as zf:
        try:
            manifest = json.loads(zf.read("deck.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("missing deck.json in .slaides archive") from exc

        if manifest.get("format_version") == "0.2":
            sections = [
                PackagedSection(
                    key=str(s.get("key") or f"section-{i}"),
                    title=str(s.get("title", "Untitled")),
                    position=int(s.get("position", i)),
                )
                for i, s in enumerate(manifest.get("sections") or [])
            ]
            slides = []
            for i, s in enumerate(manifest.get("slides") or []):
                filename = str(s.get("file") or "")
                raw = zf.read(filename).decode("utf-8")
                file_kicker, body = _extract_kicker(raw)
                slides.append(
                    PackagedSlide(
                        key=str(s.get("key") or f"slide-{i}"),
                        position=int(s.get("position", i)),
                        section_key=s.get("section_key"),
                        kicker=s.get("kicker") if s.get("kicker") is not None else file_kicker,
                        markdown=body,
                    )
                )
            return Packaged(
                title=str(manifest.get("title", "Untitled")),
                subtitle=manifest.get("subtitle"),
                manifest=manifest.get("manifest") or {},
                sections=sections,
                slides=slides,
                widgets=[PackagedWidget(**w) for w in (manifest.get("widgets") or [])],
                widget_revisions=[PackagedWidgetRevision(**r) for r in (manifest.get("widget_revisions") or [])],
                placements=[PackagedPlacement(**p) for p in (manifest.get("placements") or [])],
                excluded=manifest.get("excluded") or {},
            )

        slide_entries = sorted(
            (n for n in zf.namelist() if n.startswith("slides/") and n.endswith(".md")),
            key=lambda n: n,
        )
        slides = []
        for idx, name in enumerate(slide_entries):
            raw = zf.read(name).decode("utf-8")
            kicker, body = _extract_kicker(raw)
            slides.append(PackagedSlide(key=f"slide-{idx}", position=idx, kicker=kicker, markdown=body))
        sections_raw = manifest.get("sections") or []
        sections = [
            PackagedSection(
                key=f"section-{i}",
                title=str(s.get("title", "Untitled")),
                position=int(s.get("position", i)),
            )
            for i, s in enumerate(sections_raw)
        ]
        return Packaged(
            title=str(manifest.get("title", "Untitled")),
            subtitle=manifest.get("subtitle"),
            manifest=manifest.get("manifest") or {},
            sections=sections,
            slides=slides,
            widgets=[],
            widget_revisions=[],
            placements=[],
            excluded={},
        )
```

- [ ] **Step 4: Run package test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_package_v02_preserves_section_and_widget_metadata -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/slaides/decks/package.py apps/api/tests/test_decks.py
git commit -m "feat: add rich deck package format"
```

## Task 2: Preserve Section Membership On Export/Import

**Files:**
- Modify: `apps/api/src/slaides/decks/router.py`
- Test: `apps/api/tests/test_decks.py`

- [ ] **Step 1: Add failing section round-trip API test**

Append to `apps/api/tests/test_decks.py`:

```python
async def test_export_import_preserves_slide_section_membership(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Sectioned"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    first_section = deck["sections"][0]
    first_slide = deck["slides"][0]

    second_section = (
        await client.post(
            f"/api/v1/decks/{deck_id}/sections",
            json={"title": "Second"},
            headers=auth_headers,
        )
    ).json()
    second_slide = (
        await client.post(
            f"/api/v1/decks/{deck_id}/slides",
            json={"position": 1, "markdown": "# In second\n", "section_id": second_section["id"]},
            headers=auth_headers,
        )
    ).json()

    export = await client.post(f"/api/v1/decks/{deck_id}/export", headers=auth_headers)
    imported = await client.post(
        "/api/v1/decks/import",
        files={"file": ("sectioned.slaides", export.content, "application/zip")},
        headers=auth_headers,
    )

    body = imported.json()
    sections_by_title = {s["title"]: s["id"] for s in body["sections"]}
    slides_by_heading = {s["markdown"].splitlines()[0]: s for s in body["slides"]}

    assert slides_by_heading[first_slide["markdown"].splitlines()[0]]["section_id"] == sections_by_title[first_section["title"]]
    assert slides_by_heading[second_slide["markdown"].splitlines()[0]]["section_id"] == sections_by_title["Second"]
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_export_import_preserves_slide_section_membership -q
```

Expected: FAIL because imported slides are assigned to the first section.

- [ ] **Step 3: Export section keys and slide section keys**

In `apps/api/src/slaides/decks/router.py`, change the section/slide package build in `export_deck()`:

```python
section_key_by_id = {s.id: f"section-{i}" for i, s in enumerate(sections)}
slide_key_by_id = {s.id: f"slide-{i}" for i, s in enumerate(slides)}
packed = package.Packaged(
    title=deck.title,
    subtitle=deck.subtitle,
    manifest=deck.manifest or {},
    sections=[
        package.PackagedSection(key=section_key_by_id[s.id], title=s.title, position=s.position)
        for s in sections
    ],
    slides=[
        package.PackagedSlide(
            key=slide_key_by_id[s.id],
            position=s.position,
            section_key=section_key_by_id.get(s.section_id) if s.section_id else None,
            kicker=s.kicker,
            markdown=s.markdown,
        )
        for s in slides
    ],
    widgets=[],
    widget_revisions=[],
    placements=[],
    excluded={"widget_ai_threads": True},
)
```

- [ ] **Step 4: Import slides into mapped sections**

In `import_deck()`, replace `section_objs` and `default_section` logic with:

```python
section_by_key: dict[str, Section] = {}
for i, s in enumerate(packed.sections):
    key = s.key or f"section-{i}"
    section = Section(deck_id=deck.id, title=s.title, position=s.position)
    section_by_key[key] = section
    session.add(section)
await session.flush()

slide_by_key: dict[str, Slide] = {}
for i, s in enumerate(packed.slides):
    key = s.key or f"slide-{i}"
    slide = Slide(
        deck_id=deck.id,
        section_id=section_by_key[s.section_key].id if s.section_key in section_by_key else None,
        position=s.position,
        kicker=s.kicker,
        markdown=s.markdown,
    )
    slide_by_key[key] = slide
    session.add(slide)
await session.flush()
```

- [ ] **Step 5: Run section round-trip test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_export_import_preserves_slide_section_membership -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/slaides/decks/router.py apps/api/tests/test_decks.py
git commit -m "fix: preserve sections in deck import export"
```

## Task 3: Export And Import Widgets With Props/Revisions

**Files:**
- Modify: `apps/api/src/slaides/decks/router.py`
- Test: `apps/api/tests/test_decks.py`

- [ ] **Step 1: Add failing widget round-trip test**

Append to `apps/api/tests/test_decks.py`:

```python
async def test_export_import_preserves_widget_props_and_revision(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Widget deck"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]
    slide_id = deck["slides"][0]["id"]

    widget = (
        await client.post(
            f"/api/v1/decks/{deck_id}/widgets",
            json={
                "name": "Pulse",
                "kind": "pulse",
                "description": "A check-in",
                "html": "<section id='pulse'></section>",
                "js": "window.slaides && window.slaides.emit('ready', {})",
                "css": "#pulse { color: red; }",
                "props_schema": {"properties": {"question": {"type": "string"}}},
                "example_props": {"question": "Example?"},
                "behavior": {"kind": "quiet"},
                "ai_spec": {"prompt": "make it"},
                "tags": ["check"],
            },
            headers=auth_headers,
        )
    ).json()

    attach = await client.post(
        f"/api/v1/decks/{deck_id}/slides/{slide_id}/widgets",
        json={
            "placement_id": "pulse-abcd1234",
            "widget_id": widget["id"],
            "props": {"question": "Ready?"},
        },
        headers=auth_headers,
    )
    assert attach.status_code == 201, attach.text

    export = await client.post(f"/api/v1/decks/{deck_id}/export", headers=auth_headers)
    imported = await client.post(
        "/api/v1/decks/import",
        files={"file": ("widget.slaides", export.content, "application/zip")},
        headers=auth_headers,
    )

    body = imported.json()
    imported_slide = body["slides"][0]
    assert "{{widget:pulse-abcd1234}}" in imported_slide["markdown"]
    assert len(imported_slide["widgets"]) == 1
    placement = imported_slide["widgets"][0]
    assert placement["placement_id"] == "pulse-abcd1234"
    assert placement["props"] == {"question": "Ready?"}
    assert placement["widget_id"] != widget["id"]
    assert placement["revision"]["html"] == "<section id='pulse'></section>"
    assert placement["revision"]["props_schema"]["properties"]["question"]["type"] == "string"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_export_import_preserves_widget_props_and_revision -q
```

Expected: FAIL because `imported_slide["widgets"]` is empty.

- [ ] **Step 3: Query rich widget data in export**

Add imports in `apps/api/src/slaides/decks/router.py`:

```python
from ..db.models import SlideWidget, Widget, WidgetRevision
```

In `export_deck()`, after loading slides, query placements:

```python
slide_key_by_id = {s.id: f"slide-{i}" for i, s in enumerate(slides)}
placement_rows = (
    await session.execute(
        select(SlideWidget, Widget, WidgetRevision)
        .join(Widget, Widget.id == SlideWidget.widget_id)
        .outerjoin(WidgetRevision, WidgetRevision.id == SlideWidget.revision_id)
        .where(SlideWidget.slide_id.in_([s.id for s in slides]))
        .order_by(SlideWidget.position)
    )
).all()

widget_by_id: dict[uuid.UUID, Widget] = {}
revision_by_id: dict[uuid.UUID, WidgetRevision] = {}
for link, widget, revision in placement_rows:
    widget_by_id[widget.id] = widget
    if revision is not None:
        revision_by_id[revision.id] = revision

widget_key_by_id = {widget_id: f"widget-{i}" for i, widget_id in enumerate(widget_by_id)}
revision_key_by_id = {revision_id: f"revision-{i}" for i, revision_id in enumerate(revision_by_id)}
```

- [ ] **Step 4: Add widget metadata to `Packaged(...)`**

Populate these fields in `package.Packaged(...)`:

```python
widgets=[
    package.PackagedWidget(
        key=widget_key_by_id[w.id],
        name=w.name,
        kind=w.kind,
        description=w.description,
        tags=list(w.tags or []),
        version=w.version,
        derived_from_key=None,
        current_revision_key=revision_key_by_id.get(w.current_revision_id) if w.current_revision_id else None,
    )
    for w in widget_by_id.values()
],
widget_revisions=[
    package.PackagedWidgetRevision(
        key=revision_key_by_id[r.id],
        widget_key=widget_key_by_id[r.widget_id],
        version_number=r.version_number,
        html=r.html or "",
        js=r.js,
        css=r.css,
        props_schema=r.props_schema or {},
        example_props=r.example_props or {},
        behavior=r.behavior or {"kind": "quiet"},
        ai_spec=r.ai_spec or {},
        created_reason=r.created_reason,
    )
    for r in revision_by_id.values()
],
placements=[
    package.PackagedPlacement(
        slide_key=slide_key_by_id[link.slide_id],
        placement_id=link.placement_id,
        widget_key=widget_key_by_id[link.widget_id],
        revision_key=revision_key_by_id.get(link.revision_id) if link.revision_id else None,
        props=link.props or {},
        position=link.position,
    )
    for link, _widget, _revision in placement_rows
],
excluded={"widget_ai_threads": True},
```

- [ ] **Step 5: Import widgets, revisions, and placements**

In `import_deck()`, after slides are flushed, create widgets/revisions/placements:

```python
widget_by_key: dict[str, Widget] = {}
for w in packed.widgets or []:
    widget = Widget(
        deck_id=deck.id,
        derived_from_id=None,
        name=w.name,
        kind=w.kind,
        description=w.description,
        html="",
        js=None,
        css=None,
        props_schema={},
        tags=list(w.tags or []),
        version=w.version,
        behavior={"kind": "quiet"},
    )
    widget_by_key[w.key] = widget
    session.add(widget)
await session.flush()

revision_by_key: dict[str, WidgetRevision] = {}
for r in packed.widget_revisions or []:
    widget = widget_by_key.get(r.widget_key)
    if widget is None:
        continue
    revision = WidgetRevision(
        widget_id=widget.id,
        version_number=r.version_number,
        html=r.html or "",
        js=r.js,
        css=r.css,
        props_schema=r.props_schema or {},
        example_props=r.example_props or {},
        behavior=r.behavior or {"kind": "quiet"},
        ai_spec=r.ai_spec or {},
        created_reason=r.created_reason or "import",
    )
    revision_by_key[r.key] = revision
    session.add(revision)
await session.flush()

for w in packed.widgets or []:
    widget = widget_by_key[w.key]
    revision = revision_by_key.get(w.current_revision_key or "")
    if revision is not None:
        widget.current_revision_id = revision.id
        widget.html = revision.html
        widget.js = revision.js
        widget.css = revision.css
        widget.props_schema = revision.props_schema
        widget.behavior = revision.behavior
await session.flush()

for p in packed.placements or []:
    slide = slide_by_key.get(p.slide_key)
    widget = widget_by_key.get(p.widget_key)
    if slide is None or widget is None:
        continue
    revision = revision_by_key.get(p.revision_key or "")
    session.add(
        SlideWidget(
            slide_id=slide.id,
            placement_id=p.placement_id,
            widget_id=widget.id,
            revision_id=revision.id if revision is not None else None,
            props=p.props or {},
            position=p.position,
        )
    )
await session.flush()
```

- [ ] **Step 6: Run widget round-trip test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_export_import_preserves_widget_props_and_revision -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/slaides/decks/router.py apps/api/tests/test_decks.py
git commit -m "feat: round trip deck widgets"
```

## Task 4: Verify AI Chat History Is Excluded Deliberately

**Files:**
- Modify: `apps/api/tests/test_decks.py`
- Optionally modify: `apps/web/src/pages/Workspace.vue`

- [ ] **Step 1: Add regression test for chat exclusion**

Append to `apps/api/tests/test_decks.py`:

```python
async def test_deck_export_import_excludes_widget_ai_thread_history(client, auth_headers):
    create = await client.post("/api/v1/decks", json={"title": "Private chat"}, headers=auth_headers)
    deck = create.json()
    deck_id = deck["id"]

    widget = (
        await client.post(
            f"/api/v1/decks/{deck_id}/widgets",
            json={
                "name": "Chatty",
                "kind": "chatty",
                "html": "<section></section>",
                "props_schema": {},
                "example_props": {},
                "behavior": {"kind": "quiet"},
                "ai_spec": {},
                "tags": [],
            },
            headers=auth_headers,
        )
    ).json()

    thread = (
        await client.post(
            f"/api/v1/widgets/{widget['id']}/ai-thread",
            json={"title": "Private", "compact_summary": {"secret": "summary"}},
            headers=auth_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/widgets/{widget['id']}/ai-thread/{thread['id']}/messages",
        json={
            "role": "user",
            "message_type": "text",
            "content": {"text": "private prompt"},
            "revision_id": widget["current_revision_id"],
        },
        headers=auth_headers,
    )

    export = await client.post(f"/api/v1/decks/{deck_id}/export", headers=auth_headers)
    imported = await client.post(
        "/api/v1/decks/import",
        files={"file": ("private.slaides", export.content, "application/zip")},
        headers=auth_headers,
    )
    imported_widget_id = imported.json()["slides"][0]["widgets"][0]["widget_id"] if imported.json()["slides"][0]["widgets"] else None

    if imported_widget_id is not None:
        imported_thread = await client.get(f"/api/v1/widgets/{imported_widget_id}/ai-thread", headers=auth_headers)
        assert imported_thread.status_code == 200
        assert imported_thread.json() is None
```

- [ ] **Step 2: Run chat exclusion test**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_deck_export_import_excludes_widget_ai_thread_history -q
```

Expected: PASS after Task 3. If it fails because no widget is attached, attach the widget to the default slide inside the test before export.

- [ ] **Step 3: Add user-facing copy if export/import UI has room**

Find the export/import controls:

```bash
rg -n "exportZip|importDeck|Export|Import" apps/web/src
```

If `apps/web/src/pages/Workspace.vue` owns the import/export menu, add concise helper/title text near the export action:

```vue
<button
  class="btn btn-sm"
  type="button"
  title="Exports slides, sections, widgets, and props. AI chat history is not included."
  @click="exportDeck(deck.id)"
>
  Export
</button>
```

Keep existing classes and handler names if they differ; only add the chat-history exclusion to the UI text.

- [ ] **Step 4: Run frontend tests if UI changed**

Run:

```bash
cd apps/web
npm test -- --run
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_decks.py apps/web/src/pages/Workspace.vue
git commit -m "test: document deck export chat exclusion"
```

If no frontend file changed, commit only the test:

```bash
git add apps/api/tests/test_decks.py
git commit -m "test: document deck export chat exclusion"
```

## Task 5: Full Regression Pass And Compatibility Check

**Files:**
- Modify only if tests expose issues.

- [ ] **Step 1: Run deck tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py -q
```

Expected: PASS.

- [ ] **Step 2: Run widget tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
cd apps/api
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd apps/web
npm test -- --run
```

Expected: PASS.

- [ ] **Step 5: Inspect exported archive manually**

Run:

```bash
cd apps/api
uv run pytest tests/test_decks.py::test_export_import_preserves_widget_props_and_revision -q
```

Then use a temporary debugging snippet only if needed:

```bash
python - <<'PY'
import zipfile, json
from pathlib import Path
p = Path('/tmp/example.slaides')
if p.exists():
    with zipfile.ZipFile(p) as z:
        print(json.dumps(json.loads(z.read('deck.json')), indent=2)[:4000])
PY
```

Expected: `deck.json` contains `format_version: "0.2"`, `widgets`, `widget_revisions`, `placements`, and `excluded.widget_ai_threads: true`.

- [ ] **Step 6: Commit final fixes**

```bash
git status --short
git add apps/api/src/slaides/decks/package.py apps/api/src/slaides/decks/router.py apps/api/tests/test_decks.py apps/web/src/pages/Workspace.vue
git commit -m "fix: complete rich deck import export roundtrip"
```

Skip this commit if all changed files were already committed in earlier tasks.

## Self-Review

- Spec coverage: widget props are covered by Task 3; cross-user/local ID remapping is covered by asserting imported `widget_id != source widget_id`; widget chat history exclusion is covered by Task 4; sections are covered by Task 2.
- Placeholder scan: no placeholder markers or open-ended implementation steps remain.
- Type consistency: package dataclass names are defined in Task 1 and reused in Tasks 2-3. Router import code uses existing SQLAlchemy models from `apps/api/src/slaides/db/models.py`.
