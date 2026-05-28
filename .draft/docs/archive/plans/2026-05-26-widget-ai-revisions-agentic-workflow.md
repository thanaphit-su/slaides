# Widget AI Revisions And Agentic Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile mutable AI widget editing with durable widget revisions, persisted AI context, human-in-the-loop clarification, behavior swaps, example props, and session-safe historical rendering.

**Architecture:** Widgets become stable identities pointing at immutable revisions. AI chat becomes a structured workflow that can emit clarification questions, plans, steps, reflections, drafts, and applies. Placements and live-session snapshots use explicit revision IDs so later widget edits do not rewrite history.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL/Supabase, SQLite test compatibility, Vue 3, Pinia, Vite, Vitest, SSE.

---

## Scope And Decisions

This plan intentionally separates durable data model work from the agentic UI. The model must land first because behavior swapping, persisted chat context, thumbnails, version rollback, and session replay all depend on storing exact widget revisions.

The current workspace at `/Users/thebook/Documents/slaides` is not a Git repository. Each task ends with a verification checkpoint instead of a commit. If the project is later run inside a Git worktree, commit at each checkpoint with the task title.

## Slow Rollout Gates

This is a "slow but sure" implementation. Do not remove or replace working behavior until the replacement path is proven.

1. **Contract gate:** Write the API/data contract and compatibility tests before the migration.
2. **Migration gate:** Add revision tables and backfill, but keep existing flattened widget fields working.
3. **Dual-write gate:** Create new revisions while still updating legacy `widget.html/js/css/props_schema/behavior` columns for compatibility.
4. **Read gate:** Switch internal reads to current revision only after old response-shape tests pass.
5. **AI gate:** Add structured workflow parsing and fail-closed behavior before removing the behavior picker.
6. **UI gate:** Remove the create-mode picker only after option-chip clarification is tested.
7. **History gate:** Add placement/session revision snapshots before exposing rollback as a user-facing feature.

## Non-Negotiable Invariants

- Existing `GET /widgets/:id`, deck payloads, audience rendering, and editor rendering must keep working during the rollout.
- Invalid Loud behavior must fail with 422 at create/patch time. It must never persist and rely on runtime silent drops.
- AI responses that are not valid structured envelopes must show an error or clarification state; they must not create a fallback widget draft.
- Every code-changing widget edit creates a new `widget_revision`.
- Live/session history must render from the revision captured by the placement/session, not from the mutable current widget.
- `.swidget` export/import must preserve `behavior`, `example_props`, and `ai_spec`.

## Target File Structure

- Create: `docs/architecture/widget-revisions-ai-workflow.md`: durable contract and rollout notes.
- Modify `apps/api/src/slaides/db/models.py`: add `WidgetRevision`, `WidgetAiThread`, `WidgetAiMessage`; add `Widget.current_revision_id`; add `SlideWidget.revision_id`.
- Create `apps/api/migrations/versions/0015_widget_revisions_ai_threads.py`: schema migration and backfill one revision per existing widget.
- Modify `apps/api/src/slaides/widgets/schemas.py`: expose flattened current revision fields, revision metadata, example props, AI spec, and thread/message contracts.
- Modify `apps/api/src/slaides/widgets/router.py`: create/patch widgets through revisions, add revision history/rollback endpoints, add thread/message endpoints, preserve old response shape.
- Modify `apps/api/src/slaides/widgets/package.py`: export/import behavior, AI spec, and example props.
- Modify `apps/api/src/slaides/llm/service.py`: structured widget workflow envelope, clarification question support, current spec/context, example props validation warnings.
- Modify `apps/web/src/api/types.ts`: add `WidgetRevision`, `WidgetAiThread`, `WidgetAiMessage`, structured AI workflow response types, `example_props`, `ai_spec`, `current_revision_id`.
- Modify `apps/web/src/api/widgets.ts`: revision, rollback, thread, and message API methods.
- Modify `apps/web/src/stores/widgets.ts`: cache current widget plus revision metadata and hydrate persisted AI thread.
- Modify `apps/web/src/components/WidgetCollection.vue`: remove create-mode behavior picker, render clarification option chips, render plan/step/reflection/spec panels, allow behavior apply in adjust mode.
- Modify `apps/web/src/components/WidgetThumbnail.vue`: render with `example_props` through the same boot path as `WidgetFrame` or a thumbnail-safe equivalent.
- Modify `apps/web/src/widgets/WidgetFrame.vue`: support thumbnail/preview role with boot props and no relay side effects if reused by thumbnails.
- Modify tests:
  - `apps/api/tests/test_widgets.py`
  - `apps/api/tests/test_llm.py`
  - `apps/api/tests/test_placement_state.py`
  - `apps/web/tests/widget-collection-loud-fallback.test.ts`
  - `apps/web/tests/widget-thumbnail.test.ts`
  - Create `apps/web/tests/widget-ai-thread.test.ts`
  - Create `apps/web/tests/widget-revisions.test.ts`

---

### Task 0: Freeze Architecture Contract And Compatibility Baseline

**Files:**

- Create: `docs/architecture/widget-revisions-ai-workflow.md`
- Modify: `apps/api/tests/test_widgets.py`
- Modify: `apps/web/tests/widget-collection-loud-fallback.test.ts`

- [X] **Step 1: Create architecture contract doc**

Create `docs/architecture/widget-revisions-ai-workflow.md`:

```markdown
# Widget Revisions And AI Workflow Contract

## Goal

Widgets are durable authored artifacts. A widget identity has metadata and points
to a current immutable revision. Each revision stores the executable source,
behavior contract, props schema, example props, and AI-readable spec.

## Data Ownership

- `widget` owns stable identity: deck, name, kind, description, tags, current revision.
- `widget_revision` owns versioned source and contract: html, js, css, props_schema,
  example_props, behavior, ai_spec.
- `slide_widget` owns placement: placement_id, widget_id, revision_id, props.
- `widget_ai_thread` owns durable conversation summary for a widget.
- `widget_ai_message` owns structured chat events: user, question, plan, step,
  reflection, draft, apply.

## Compatibility Rule

Until all render paths read revisions directly, API responses keep flattening the
current revision onto `WidgetOut` as `html`, `js`, `css`, `props_schema`, and
`behavior`.

## Behavior Rule

Quiet behavior is exactly `{ "kind": "quiet" }`.
Loud behavior requires `{ "kind": "loud", "aggregator": "tally",
"contribution_schema": {"type": "string"} }` or the equivalent shape for
another supported aggregator.
Invalid Loud behavior returns 422 and is never persisted.

## AI Workflow Rule

The widget AI returns a structured JSON envelope:

- `question`: AI needs user input and includes option chips.
- `draft`: AI is confident and includes `widget`, `ai_spec`, and `example_props`.
- `plan`, `step`, and `reflection`: optional progress records stored in the thread.

Plain prose is invalid for widget generation/adjustment.

## Session History Rule

Any live/session historical view renders the revision captured at placement or
session materialization time. Editing the widget later cannot alter past sessions.
```

- [X] **Step 2: Add compatibility baseline API test**

Add this test to `apps/api/tests/test_widgets.py` before adding revision tables:

```python
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
```

- [X] **Step 3: Add current UI baseline test**

In `apps/web/tests/widget-collection-loud-fallback.test.ts`, keep one test proving the current picker exists before the replacement task:

```ts
it("baseline: create mode still has behavior picker before structured workflow replaces it", async () => {
  const wrapper = await mountInCreateMode();
  expect(wrapper.find('button[title="Behavior"]').exists()).toBe(true);
});
```

- [X] **Step 4: Run baseline tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_api_baseline_keeps_flat_source_shape -q
cd ../web
npm test -- --run tests/widget-collection-loud-fallback.test.ts
```

Expected: PASS before migration work begins.

---

### Task 1: Add Widget Revision And AI Thread Schema

**Files:**

- Modify: `apps/api/src/slaides/db/models.py`
- Create: `apps/api/migrations/versions/0015_widget_revisions_ai_threads.py`
- Test: `apps/api/tests/test_widgets.py`

- [X] **Step 1: Write failing backend test for revision backfill expectations**

Add this test to `apps/api/tests/test_widgets.py` after `test_widget_crud`:

```python
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
```

- [X] **Step 2: Run the failing test**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_create_returns_current_revision_and_ai_fields -q
```

Expected: FAIL because `example_props`, `ai_spec`, and `current_revision_id` are not in the response schema.

- [X] **Step 3: Add ORM models**

In `apps/api/src/slaides/db/models.py`, add a nullable `current_revision_id` to `Widget` and define new models after `Widget`:

```python
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
```

```python
class WidgetRevision(Base):
    __tablename__ = "widget_revision"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    widget_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("widget.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    js: Mapped[str | None] = mapped_column(Text, nullable=True)
    css: Mapped[str | None] = mapped_column(Text, nullable=True)
    props_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    example_props: Mapped[dict] = mapped_column(JSON, default=dict)
    behavior: Mapped[dict] = mapped_column(JSON, default=lambda: {"kind": "quiet"}, nullable=False)
    ai_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    created_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("widget_id", "version_number", name="uq_widget_revision_version"),
        Index("ix_widget_revision_widget", "widget_id", "version_number"),
    )


class WidgetAiThread(Base):
    __tablename__ = "widget_ai_thread"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    widget_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("widget.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    compact_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WidgetAiMessage(Base):
    __tablename__ = "widget_ai_message"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=_uuid)
    thread_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("widget_ai_thread.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("widget_revision.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_widget_ai_message_thread_created", "thread_id", "created_at"),)
```

Also add `revision_id` to `SlideWidget`:

```python
    revision_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("widget_revision.id"), nullable=True)
```

- [X] **Step 4: Add migration**

Create `apps/api/migrations/versions/0015_widget_revisions_ai_threads.py` with:

```python
"""Add widget revisions and AI thread history.

Revision ID: 0015_widget_revisions_ai_threads
Revises: 0014_tutorial_v2_reseed
Create Date: 2026-05-26
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0015_widget_revisions_ai_threads"
down_revision = "0014_tutorial_v2_reseed"
branch_labels = None
depends_on = None


def _uuid() -> str:
    return str(uuid.uuid4())


def _uuid_type(dialect: str):
    return postgresql.UUID(as_uuid=True) if dialect == "postgresql" else sa.CHAR(36)


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = _uuid_type(bind.dialect.name)

    op.create_table(
        "widget_revision",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("widget_id", uuid_type, sa.ForeignKey("widget.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False, server_default=""),
        sa.Column("js", sa.Text(), nullable=True),
        sa.Column("css", sa.Text(), nullable=True),
        sa.Column("props_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("example_props", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "behavior",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{\"kind\": \"quiet\"}'"),
        ),
        sa.Column("ai_spec", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_reason", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("widget_id", "version_number", name="uq_widget_revision_version"),
    )
    op.create_index("ix_widget_revision_widget", "widget_revision", ["widget_id", "version_number"])

    with op.batch_alter_table("widget") as batch:
        batch.add_column(sa.Column("current_revision_id", uuid_type, nullable=True))
    with op.batch_alter_table("slide_widget") as batch:
        batch.add_column(sa.Column("revision_id", uuid_type, nullable=True))

    rows = bind.execute(
        sa.text("SELECT id, html, js, css, props_schema, behavior FROM widget")
    ).mappings().all()
    for row in rows:
        revision_id = _uuid()
        bind.execute(
            sa.text(
                """
                INSERT INTO widget_revision
                  (id, widget_id, version_number, html, js, css, props_schema, example_props,
                   behavior, ai_spec, created_reason)
                VALUES
                  (:id, :widget_id, 1, :html, :js, :css, :props_schema, :example_props,
                   :behavior, :ai_spec, :created_reason)
                """
            ),
            {
                "id": revision_id,
                "widget_id": str(row["id"]),
                "html": row["html"] or "",
                "js": row["js"],
                "css": row["css"],
                "props_schema": _json(row["props_schema"]),
                "example_props": json.dumps({}),
                "behavior": _json(row["behavior"] or {"kind": "quiet"}),
                "ai_spec": json.dumps({}),
                "created_reason": "migration_backfill",
            },
        )
        bind.execute(
            sa.text("UPDATE widget SET current_revision_id = :revision_id WHERE id = :widget_id"),
            {"revision_id": revision_id, "widget_id": str(row["id"])},
        )
        bind.execute(
            sa.text("UPDATE slide_widget SET revision_id = :revision_id WHERE widget_id = :widget_id"),
            {"revision_id": revision_id, "widget_id": str(row["id"])},
        )

    # Enforce revision pointers in Postgres. SQLite is used only for tests/dev
    # here; adding these FKs through batch mode rebuilds legacy tables and can
    # fail on older server-default syntax from previous migrations.
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_widget_current_revision",
            "widget",
            "widget_revision",
            ["current_revision_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_slide_widget_revision",
            "slide_widget",
            "widget_revision",
            ["revision_id"],
            ["id"],
        )

    op.create_table(
        "widget_ai_thread",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("widget_id", uuid_type, sa.ForeignKey("widget.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("compact_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "widget_ai_message",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("thread_id", uuid_type, sa.ForeignKey("widget_ai_thread.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("revision_id", uuid_type, sa.ForeignKey("widget_revision.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_widget_ai_message_thread_created", "widget_ai_message", ["thread_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_widget_ai_message_thread_created", table_name="widget_ai_message")
    op.drop_table("widget_ai_message")
    op.drop_table("widget_ai_thread")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_slide_widget_revision", "slide_widget", type_="foreignkey")
        op.drop_constraint("fk_widget_current_revision", "widget", type_="foreignkey")
    with op.batch_alter_table("slide_widget") as batch:
        batch.drop_column("revision_id")
    with op.batch_alter_table("widget") as batch:
        batch.drop_column("current_revision_id")
    op.drop_index("ix_widget_revision_widget", table_name="widget_revision")
    op.drop_table("widget_revision")
```

- [X] **Step 5: Run migration/tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_create_returns_current_revision_and_ai_fields -q
```

Expected: still FAIL until schemas/router are wired in Task 2.

---

### Task 2: Flatten Current Revision Through Existing Widget API

**Files:**

- Modify: `apps/api/src/slaides/widgets/schemas.py`
- Modify: `apps/api/src/slaides/widgets/router.py`
- Test: `apps/api/tests/test_widgets.py`

- [X] **Step 1: Extend schemas**

Add fields to `WidgetOut`, `WidgetCreate`, and `WidgetPatch` in `apps/api/src/slaides/widgets/schemas.py`.

For `WidgetOut`:

```python
    current_revision_id: uuid.UUID | None = None
    example_props: dict = Field(default_factory=dict)
    ai_spec: dict = Field(default_factory=dict)
```

For `WidgetCreate`:

```python
    example_props: dict = Field(default_factory=dict)
    ai_spec: dict = Field(default_factory=dict)
```

For `WidgetPatch`:

```python
    example_props: dict | None = None
    ai_spec: dict | None = None
```

- [X] **Step 2: Wire revision creation in router**

Import `func`, `WidgetRevision`, `flag_modified` if needed:

```python
from sqlalchemy import func, select, update
from ..db.models import WidgetRevision
```

Add helper functions to `apps/api/src/slaides/widgets/router.py`:

```python
async def _current_revision(session: AsyncSession, widget: Widget) -> WidgetRevision | None:
    if widget.current_revision_id is None:
        return None
    return (
        await session.execute(
            select(WidgetRevision).where(WidgetRevision.id == widget.current_revision_id)
        )
    ).scalar_one_or_none()


async def _next_revision_number(session: AsyncSession, widget_id: uuid.UUID) -> int:
    value = (
        await session.execute(
            select(func.max(WidgetRevision.version_number)).where(WidgetRevision.widget_id == widget_id)
        )
    ).scalar_one_or_none()
    return int(value or 0) + 1


async def _create_revision(
    session: AsyncSession,
    widget: Widget,
    *,
    html: str,
    js: str | None,
    css: str | None,
    props_schema: dict,
    example_props: dict,
    behavior: dict,
    ai_spec: dict,
    created_reason: str,
) -> WidgetRevision:
    rev = WidgetRevision(
        widget_id=widget.id,
        version_number=await _next_revision_number(session, widget.id),
        html=html or "",
        js=js,
        css=css,
        props_schema=props_schema or {},
        example_props=example_props or {},
        behavior=_normalise_behavior(behavior),
        ai_spec=ai_spec or {},
        created_reason=created_reason,
    )
    session.add(rev)
    await session.flush()
    widget.current_revision_id = rev.id
    widget.html = rev.html
    widget.js = rev.js
    widget.css = rev.css
    widget.props_schema = rev.props_schema
    widget.behavior = rev.behavior
    await session.flush()
    return rev
```

Update `_full(w)` to read from current revision when present and include `current_revision_id`, `example_props`, and `ai_spec`.

Keep the legacy columns updated inside `_create_revision` during this rollout. This dual-write compatibility is intentional until every rendering and export path has been moved to explicit revisions.

- [X] **Step 3: Make create endpoint create revision**

In `create_deck_widget`, create the `Widget` with metadata first, then call `_create_revision`:

```python
w = Widget(
    deck_id=deck.id,
    name=body.name,
    kind=body.kind,
    description=body.description,
    html="",
    js=None,
    css=None,
    props_schema={},
    tags=body.tags or [],
    behavior={"kind": "quiet"},
)
session.add(w)
await session.flush()
await _create_revision(
    session,
    w,
    html=body.html or "",
    js=body.js,
    css=body.css,
    props_schema=body.props_schema or {},
    example_props=body.example_props or {},
    behavior=body.behavior,
    ai_spec=body.ai_spec or {},
    created_reason="create",
)
await session.refresh(w)
return await _full_with_revision(session, w)
```

If `_full` cannot become async, create `_full_with_revision(session, w)` and use it for routes that need revision fields.

- [X] **Step 4: Make patch endpoint create revision when revisioned fields change**

In `patch_widget`, split metadata fields (`name`, `kind`, `description`, `tags`) from revision fields (`html`, `js`, `css`, `props_schema`, `example_props`, `behavior`, `ai_spec`).

Use current revision values as defaults:

```python
current = await _current_revision(session, w)
base = {
    "html": current.html if current else (w.html or ""),
    "js": current.js if current else w.js,
    "css": current.css if current else w.css,
    "props_schema": current.props_schema if current else (w.props_schema or {}),
    "example_props": current.example_props if current else {},
    "behavior": current.behavior if current else (w.behavior or {"kind": "quiet"}),
    "ai_spec": current.ai_spec if current else {},
}
```

If any revision field is present in `body`, call `_create_revision` with `created_reason="patch"`. Otherwise only update widget metadata.

- [X] **Step 5: Run API test**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_create_returns_current_revision_and_ai_fields -q
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_api_baseline_keeps_flat_source_shape tests/test_widgets.py::test_widget_create_returns_current_revision_and_ai_fields -q
uv run pytest tests/test_widgets.py -q
```

Observed: focused tests passed; full widget API suite passed with `22 passed`.

---

### Task 3: Enforce Strict Behavior Validation And Allow Behavior Swaps

**Files:**

- Modify: `apps/api/src/slaides/widgets/router.py`
- Modify: `apps/web/src/components/WidgetCollection.vue`
- Test: `apps/api/tests/test_widgets.py`
- Test: `apps/web/tests/widget-collection-loud-fallback.test.ts`

- [X] **Step 1: Add backend tests for malformed behavior**

Add to `apps/api/tests/test_widgets.py`:

```python
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
```

- [X] **Step 2: Replace `_normalise_behavior` with strict validator**

In `apps/api/src/slaides/widgets/router.py`:

```python
_LOUD_AGGREGATORS = {"tally", "latest_per_participant", "append", "set_union", "keyed_tally"}


def _normalise_behavior(raw: dict | None) -> dict:
    if raw is None:
        return {"kind": "quiet"}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="behavior must be an object")
    kind = raw.get("kind")
    if kind == "quiet":
        return {"kind": "quiet"}
    if kind != "loud":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="behavior.kind must be quiet or loud")
    aggregator = raw.get("aggregator")
    if aggregator not in _LOUD_AGGREGATORS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="behavior.aggregator is required for loud widgets")
    contribution_schema = raw.get("contribution_schema")
    if not isinstance(contribution_schema, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="behavior.contribution_schema is required for loud widgets")
    return {
        "kind": "loud",
        "aggregator": aggregator,
        "contribution_schema": contribution_schema,
    }
```

- [X] **Step 3: Allow adjust apply to include behavior**

In `apps/web/src/components/WidgetCollection.vue`, update the adjust patch allow-list:

```ts
for (const key of ["name", "kind", "description", "html", "js", "css", "props_schema", "example_props", "ai_spec", "tags", "behavior"] as const) {
  if (key in draft) (adjustPatch as Record<string, unknown>)[key] = draft[key];
}
```

- [X] **Step 4: Run tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_create_loud_widget_requires_valid_aggregator_and_contribution_schema tests/test_widgets.py::test_patch_widget_can_swap_quiet_to_loud -q
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_create_loud_widget_requires_valid_aggregator_and_contribution_schema tests/test_widgets.py::test_patch_widget_can_swap_quiet_to_loud -q
uv run pytest tests/test_widgets.py -q
cd ../web
npm test -- --run tests/widget-collection-loud-fallback.test.ts
npm test -- --run tests/behavior.test.ts tests/widget-collection-loud-fallback.test.ts
```

Observed: targeted behavior tests passed; full widget API suite passed with `24 passed`; focused web suite passed with `8 passed`; sanitizer plus widget collection suites passed with `19 passed`.

---

### Task 4: Persist AI Threads And Messages

**Files:**

- Modify: `apps/api/src/slaides/widgets/schemas.py`
- Modify: `apps/api/src/slaides/widgets/router.py`
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/widgets.ts`
- Test: `apps/api/tests/test_widgets.py`
- Test: `apps/web/tests/widget-ai-thread.test.ts`

- [X] **Step 1: Add backend thread test**

Add to `apps/api/tests/test_widgets.py`:

```python
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
```

- [X] **Step 2: Add schemas**

Add to `apps/api/src/slaides/widgets/schemas.py`:

```python
class WidgetAiThreadCreate(BaseModel):
    title: str | None = None
    compact_summary: dict = Field(default_factory=dict)


class WidgetAiMessageCreate(BaseModel):
    role: str
    message_type: str
    content: dict = Field(default_factory=dict)
    revision_id: uuid.UUID | None = None


class WidgetAiMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    thread_id: uuid.UUID
    role: str
    message_type: str
    content: dict
    revision_id: uuid.UUID | None = None


class WidgetAiThreadOut(BaseModel):
    id: uuid.UUID
    widget_id: uuid.UUID
    title: str | None = None
    compact_summary: dict
    messages: list[WidgetAiMessageOut] = Field(default_factory=list)
```

- [X] **Step 3: Add router endpoints**

Add endpoints:

```python
@router.post("/{widget_id}/ai-thread", response_model=WidgetAiThreadOut, status_code=status.HTTP_201_CREATED)
async def create_ai_thread(
    widget_id: uuid.UUID,
    body: WidgetAiThreadCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiThreadOut:
    widget = await _load_widget(session, user, widget_id)
    thread = WidgetAiThread(widget_id=widget.id, title=body.title, compact_summary=body.compact_summary or {})
    session.add(thread)
    await session.flush()
    await session.refresh(thread)
    return WidgetAiThreadOut(
        id=thread.id,
        widget_id=thread.widget_id,
        title=thread.title,
        compact_summary=thread.compact_summary or {},
        messages=[],
    )

@router.get("/{widget_id}/ai-thread", response_model=WidgetAiThreadOut | None)
async def get_ai_thread(
    widget_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiThreadOut | None:
    widget = await _load_widget(session, user, widget_id)
    thread = (
        await session.execute(
            select(WidgetAiThread)
            .where(WidgetAiThread.widget_id == widget.id)
            .order_by(WidgetAiThread.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if thread is None:
        return None
    rows = (
        await session.execute(
            select(WidgetAiMessage)
            .where(WidgetAiMessage.thread_id == thread.id)
            .order_by(WidgetAiMessage.created_at)
        )
    ).scalars().all()
    return WidgetAiThreadOut(
        id=thread.id,
        widget_id=thread.widget_id,
        title=thread.title,
        compact_summary=thread.compact_summary or {},
        messages=[WidgetAiMessageOut.model_validate(row) for row in rows],
    )

@router.post("/{widget_id}/ai-thread/{thread_id}/messages", response_model=WidgetAiMessageOut, status_code=status.HTTP_201_CREATED)
async def append_ai_message(
    widget_id: uuid.UUID,
    thread_id: uuid.UUID,
    body: WidgetAiMessageCreate,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetAiMessageOut:
    widget = await _load_widget(session, user, widget_id)
    thread = (
        await session.execute(
            select(WidgetAiThread).where(
                WidgetAiThread.id == thread_id,
                WidgetAiThread.widget_id == widget.id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI thread not found")
    msg = WidgetAiMessage(
        thread_id=thread.id,
        role=body.role,
        message_type=body.message_type,
        content=body.content or {},
        revision_id=body.revision_id,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return WidgetAiMessageOut.model_validate(msg)
```

Implementation rule: `_load_widget(session, user, widget_id)` must be called first for ownership. `thread_id` must belong to `widget_id`.

- [X] **Step 4: Add frontend API methods**

In `apps/web/src/api/widgets.ts`:

```ts
getAiThread: (widgetId: string) => api<WidgetAiThread | null>(`/widgets/${widgetId}/ai-thread`),
createAiThread: (widgetId: string, body: { title?: string | null; compact_summary?: Record<string, unknown> }) =>
  api<WidgetAiThread>(`/widgets/${widgetId}/ai-thread`, { method: "POST", body }),
appendAiMessage: (widgetId: string, threadId: string, body: { role: string; message_type: string; content: Record<string, unknown>; revision_id?: string | null }) =>
  api<WidgetAiMessage>(`/widgets/${widgetId}/ai-thread/${threadId}/messages`, { method: "POST", body }),
```

- [X] **Step 5: Run backend thread test**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_ai_thread_persists_messages -q
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_ai_thread_persists_messages -q
uv run pytest tests/test_widgets.py -q
python -m py_compile src/slaides/widgets/router.py src/slaides/widgets/schemas.py
cd ../web
npm test -- --run tests/widget-ai-thread.test.ts
npm test -- --run tests/widget-ai-thread.test.ts tests/widget-collection-loud-fallback.test.ts tests/behavior.test.ts
npm run build
```

Observed: backend thread test passed; full widget API suite passed with `25 passed`; focused frontend suites passed with `20 passed`; production build passed.

---

### Task 5: Structured AI Workflow Envelope

**Files:**

- Modify: `apps/api/src/slaides/llm/service.py`
- Modify: `apps/web/src/api/llm.ts`
- Modify: `apps/web/src/components/WidgetCollection.vue`
- Test: `apps/api/tests/test_llm.py`
- Test: `apps/web/tests/widget-ai-thread.test.ts`

- [X] **Step 1: Add LLM tests for clarification envelope and fail-closed parsing**

Add to `apps/api/tests/test_llm.py`:

```python
def test_widget_workflow_accepts_clarification_question_envelope():
    raw = '{"type":"question","question":"Should this be private or shared?","options":[{"id":"quiet","label":"Private"},{"id":"loud","label":"Shared"}]}'
    parsed = llm_service._parse_widget_workflow(raw)
    assert parsed["type"] == "question"
    assert parsed["options"][1]["id"] == "loud"


def test_widget_workflow_rejects_plain_prose():
    try:
        llm_service._parse_widget_workflow("I think this should be a poll.")
    except ValueError as exc:
        assert "workflow" in str(exc) or "JSON" in str(exc)
    else:
        raise AssertionError("plain prose must not become a fallback widget draft")
```

- [X] **Step 2: Add parser helper**

In `apps/api/src/slaides/llm/service.py`:

```python
def _parse_widget_workflow(text: str) -> dict:
    data = json.loads(_extract_first_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("workflow response must be an object")
    kind = data.get("type")
    if kind not in {"question", "plan", "step", "reflection", "draft"}:
        raise ValueError("workflow response type must be question, plan, step, reflection, or draft")
    if kind == "question":
        if not isinstance(data.get("question"), str):
            raise ValueError("question response requires question")
        if not isinstance(data.get("options"), list) or not data["options"]:
            raise ValueError("question response requires options")
    if kind == "draft":
        if not isinstance(data.get("widget"), dict):
            raise ValueError("draft response requires widget")
    return data
```

- [X] **Step 3: Update widget system prompt**

Change widget prompt from the current compact-widget-JSON instruction to:

```python
"You generate and revise SLAIDES widgets. Return only compact JSON in this envelope: "
'{"type":"question","question":"Should this be private or shared with the room?",'
'"options":[{"id":"quiet","label":"Private per viewer","value":{"behavior":{"kind":"quiet"}}},'
'{"id":"loud","label":"Shared live results","value":{"behavior":{"kind":"loud"}}}]} '
"when behavior or requirements are ambiguous; or "
'{"type":"draft","plan":["choose behavior","write props schema","write widget source"],'
'"reflection":"The widget uses props for all user-visible copy.",'
'"widget":{"name":"Poll","kind":"poll","html":"<section></section>","js":"","css":"",'
'"props_schema":{},"tags":[],"behavior":{"kind":"quiet"}},'
'"ai_spec":{"intent":"Private poll draft"},"example_props":{}} '
"when you are confident. Never answer with plain prose."
```

- [X] **Step 4: Update frontend parsing**

In `WidgetCollection.vue`, replace `parseDraft(raw, text)` usage with a parser that distinguishes:

```ts
type WidgetWorkflow =
  | { type: "question"; question: string; options: Array<{ id: string; label: string; value?: Record<string, unknown> }> }
  | { type: "draft"; plan?: string[]; reflection?: string; widget: Partial<Widget>; ai_spec?: Record<string, unknown>; example_props?: Record<string, unknown> };
```

If `type === "question"`, render option chips above the composer and do not create a draft card.

- [X] **Step 5: Remove fallback draft behavior for AI workflow responses**

In `WidgetCollection.vue`, keep `fallbackDraft()` only for legacy tests until the workflow parser lands, then stop calling it from widget AI responses. Invalid JSON or an unknown envelope type should set:

```ts
assistantMessage.text = "AI returned an invalid widget workflow response. Ask it to try again.";
assistantMessage.raw = raw;
error.value = "AI response was not a valid widget workflow.";
```

Do not attach `assistantMessage.draft` in this branch.

- [X] **Step 6: Run tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_llm.py::test_widget_workflow_accepts_clarification_question_envelope tests/test_llm.py::test_widget_workflow_rejects_plain_prose -q
cd ../web
npm test -- --run tests/widget-ai-thread.test.ts
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_llm.py::test_widget_workflow_accepts_clarification_question_envelope tests/test_llm.py::test_widget_workflow_rejects_plain_prose -q
uv run pytest tests/test_llm.py -q
uv run pytest tests/test_widgets.py -q
python -m py_compile src/slaides/llm/service.py
cd ../web
npm test -- --run tests/widget-collection-loud-fallback.test.ts
npm test -- --run tests/widget-collection-loud-fallback.test.ts tests/widget-ai-thread.test.ts tests/behavior.test.ts
npm run build
```

Observed: workflow parser tests passed; LLM suite passed with `35 passed`; full widget API suite passed with `25 passed`; focused frontend suites passed with `20 passed`; production build passed.

---

### Task 6: Remove Create-Mode Behavior Picker

**Files:**

- Modify: `apps/web/src/components/WidgetCollection.vue`
- Test: `apps/web/tests/widget-collection-loud-fallback.test.ts`

- [X] **Step 1: Add replacement UI test before deleting picker**

Add a test that stubs an AI `question` envelope and verifies option chips appear above the composer:

```ts
it("renders AI clarification options above the composer", async () => {
  const wrapper = await mountInCreateMode();
  llmMock.mockResolvedValue(JSON.stringify({
    type: "question",
    question: "Should this be private or shared?",
    options: [
      { id: "quiet", label: "Private per viewer", value: { behavior: { kind: "quiet" } } },
      { id: "loud", label: "Shared live results", value: { behavior: { kind: "loud" } } },
    ],
  }));
  await sendPrompt(wrapper);
  expect(wrapper.text()).toContain("Should this be private or shared?");
  expect(wrapper.text()).toContain("Private per viewer");
  expect(wrapper.text()).toContain("Shared live results");
});
```

- [X] **Step 2: Update deletion test expectation**

Replace tests that click `button[title="Behavior"]` with tests that assert it does not exist in create mode:

```ts
it("does not render a behavior picker in create mode", async () => {
  const wrapper = await mountInCreateMode();
  expect(wrapper.find('button[title="Behavior"]').exists()).toBe(false);
});
```

- [X] **Step 3: Remove behavior picker UI**

In `WidgetCollection.vue`, remove:

```vue
<button
  v-if="!adjusting"
  ref="behaviorAnchor"
  type="button"
  class="widget-tool-btn"
  title="Behavior"
>
```

and remove the behavior popover block.

- [X] **Step 4: Remove behavior_choice context**

In the LLM context, remove:

```ts
behavior_choice: {
  kind: behaviorKind.value,
  aggregator: behaviorKind.value === "loud" && aggregator.value !== "auto" ? aggregator.value : null,
},
```

Keep `current.behavior` in adjust mode so the model can preserve or intentionally change behavior.

- [X] **Step 5: Run frontend tests**

Run:

```bash
cd apps/web
npm test -- --run tests/widget-collection-loud-fallback.test.ts
```

Expected: update or delete old loud-picker fallback tests; new no-picker and question-chip tests PASS.

Checkpoint result:

```bash
cd apps/web
npm test -- --run tests/widget-collection-loud-fallback.test.ts
npm test -- --run tests/widget-collection-loud-fallback.test.ts tests/widget-ai-thread.test.ts tests/behavior.test.ts
npm run build
```

Observed: focused no-picker/question-chip suite passed with `8 passed`; related focused suites passed with `20 passed`; production build passed.

---

### Task 7: Example Props For Insert And Thumbnail Preview

**Files:**

- Modify: `apps/api/src/slaides/widgets/router.py`
- Modify: `apps/web/src/components/WidgetThumbnail.vue`
- Modify: `apps/web/src/widgets/WidgetFrame.vue`
- Test: `apps/api/tests/test_widgets.py`
- Test: `apps/web/tests/widget-thumbnail.test.ts`

- [X] **Step 1: Backend attach uses example props by default**

Add API test:

```python
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
```

- [X] **Step 2: Attach endpoint fallback**

In slide attach route, when `body.props` is empty, load current revision and use `revision.example_props`:

```python
incoming_props = body.props or {}
if not incoming_props:
    rev = await _current_revision(session, widget)
    incoming_props = dict((rev.example_props if rev else {}) or {})
validated_props = validate_props(incoming_props, widget.props_schema or {})
```

- [X] **Step 3: Thumbnail uses example props**

Prefer reusing `WidgetFrame` in a non-interactive wrapper, passing:

```vue
<WidgetFrame
  :widget="widget"
  placement-id="thumbnail"
  :boot-props="widget.example_props || {}"
  role="preview"
  :fill="true"
/>
```

If this causes runtime cost issues, create `WidgetStaticPreview.vue` that injects the bridge boot script but blocks outbound relay.

- [X] **Step 4: Run tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_attach_widget_defaults_to_example_props -q
cd ../web
npm test -- --run tests/widget-thumbnail.test.ts
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_attach_widget_defaults_to_example_props -q
uv run pytest tests/test_widgets.py -q
python -m py_compile src/slaides/widgets/router.py
cd ../web
npm test -- --run tests/widget-thumbnail.test.ts
npm test -- --run tests/widget-thumbnail.test.ts tests/widget-collection-loud-fallback.test.ts
npm run build
```

Observed: attach example-props test passed; full widget API suite passed with `26 passed`; thumbnail and related frontend suites passed with `13 passed`; production build passed.

---

### Task 8: Revision History And Rollback

**Files:**

- Modify: `apps/api/src/slaides/widgets/schemas.py`
- Modify: `apps/api/src/slaides/widgets/router.py`
- Modify: `apps/web/src/api/widgets.ts`
- Create: `apps/web/tests/widget-revisions.test.ts`
- Test: `apps/api/tests/test_widgets.py`

- [X] **Step 1: Add backend revision tests**

Add:

```python
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
```

- [X] **Step 2: Add endpoints**

Add:

```python
@router.get("/{widget_id}/revisions", response_model=list[WidgetRevisionOut])
async def list_widget_revisions(
    widget_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WidgetRevisionOut]:
    widget = await _load_widget(session, user, widget_id)
    rows = (
        await session.execute(
            select(WidgetRevision)
            .where(WidgetRevision.widget_id == widget.id)
            .order_by(WidgetRevision.version_number)
        )
    ).scalars().all()
    return [WidgetRevisionOut.model_validate(row) for row in rows]

@router.post("/{widget_id}/revisions/{revision_id}/rollback", response_model=WidgetOut)
async def rollback_widget_revision(
    widget_id: uuid.UUID,
    revision_id: uuid.UUID,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(db_session),
) -> WidgetOut:
    widget = await _load_widget(session, user, widget_id)
    source = (
        await session.execute(
            select(WidgetRevision).where(
                WidgetRevision.id == revision_id,
                WidgetRevision.widget_id == widget.id,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")
    await _create_revision(
        session,
        widget,
        html=source.html,
        js=source.js,
        css=source.css,
        props_schema=source.props_schema or {},
        example_props=source.example_props or {},
        behavior=source.behavior or {"kind": "quiet"},
        ai_spec=source.ai_spec or {},
        created_reason="rollback",
    )
    await session.refresh(widget)
    return await _full_with_revision(session, widget)
```

Rollback should create a new revision copied from the target revision with `created_reason="rollback"`, not mutate history or reuse the old revision as current.

- [X] **Step 3: Run backend revision test**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_patch_creates_new_revision_and_rollback_restores_old_source -q
```

Expected: PASS.

Checkpoint result:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_patch_creates_new_revision_and_rollback_restores_old_source -q
uv run pytest tests/test_widgets.py -q
python -m py_compile src/slaides/widgets/router.py src/slaides/widgets/schemas.py
cd ../web
npm test -- --run tests/widget-revisions.test.ts
npm test -- --run tests/widget-revisions.test.ts tests/widget-ai-thread.test.ts tests/widget-thumbnail.test.ts
npm run build
```

Observed: backend revision test passed; full widget API suite passed with `27 passed`; focused frontend revision/thread/thumbnail suites passed with `7 passed`; production build passed.

---

### Task 9: Session History Uses Revision Snapshots

**Files:**

- Modify: `apps/api/src/slaides/widgets/router.py`
- Modify: `apps/api/src/slaides/sessions/router.py`
- Modify: `apps/api/src/slaides/sessions/ws.py`
- Modify: `apps/web/src/api/types.ts`
- Test: `apps/api/tests/test_placement_state.py`

- [X] **Step 1: Add test proving session/placement remains on old revision**

Add:

```python
async def test_live_placement_uses_original_revision_after_widget_edit(client, auth_headers):
    deck = await _new_deck(client, auth_headers, "Session revision")
    slide_id = deck["slides"][0]["id"]
    w = await _create_widget(client, auth_headers, deck["id"], name="Live", html="<p>v1</p>")
    attach = await client.post(
        f"/api/v1/decks/{deck['id']}/slides/{slide_id}/widgets",
        json={"placement_id": "live-1", "widget_id": w["id"]},
        headers=auth_headers,
    )
    assert attach.status_code == 201
    original_revision_id = w["current_revision_id"]
    patch = await client.patch(
        f"/api/v1/widgets/{w['id']}",
        json={"html": "<p>v2</p>"},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    deck_after = await client.get(f"/api/v1/decks/{deck['id']}", headers=auth_headers)
    placement = deck_after.json()["slides"][0]["widgets"][0]
    assert placement["revision_id"] == original_revision_id
```

- [X] **Step 2: Add `revision_id` to `SlideWidgetOut`**

In `schemas.py`:

```python
    revision_id: uuid.UUID | None = None
```

- [X] **Step 3: Set placement revision on attach**

When attaching a widget, set `SlideWidget.revision_id = widget.current_revision_id`.

- [X] **Step 4: Make deck/session serializers include revision_id**

Where slide widgets are serialized, include `revision_id` so frontend can fetch/render exact revision later.

- [X] **Step 5: Run test**

Run:

```bash
cd apps/api
uv run pytest tests/test_placement_state.py::test_live_placement_uses_original_revision_after_widget_edit -q
```

Expected: PASS.

Checkpoint:

- Added `revision_id` to API/web placement shapes and serialize it through deck/session snapshots.
- Attach now captures `widget.current_revision_id`; placement patch responses return the same snapshot id.
- WebSocket widget contributions read Loud/Quiet behavior from the captured revision when available, with a regression test for loud placements edited to quiet later.
- Verified:
  - `cd apps/api && uv run pytest tests/test_placement_state.py::test_live_placement_uses_original_revision_after_widget_edit tests/test_placement_state.py::test_loud_placement_keeps_revision_behavior_after_widget_edit -q`
  - `cd apps/api && uv run pytest tests/test_placement_state.py tests/test_widgets.py -q`
  - `cd apps/api && python -m py_compile src/slaides/widgets/router.py src/slaides/widgets/schemas.py src/slaides/decks/service.py src/slaides/decks/schemas.py src/slaides/sessions/ws.py`
  - `cd apps/web && npm run build`

---

### Task 10: Package Export/Import Preserves Full Revision Contract

**Files:**

- Modify: `apps/api/src/slaides/widgets/package.py`
- Modify: `apps/api/src/slaides/widgets/router.py`
- Test: `apps/api/tests/test_widgets.py`

- [X] **Step 1: Add round-trip test**

Update `test_widget_export_import_round_trip` or add:

```python
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
    widget_id = create.json()["id"]
    export = await client.post(f"/api/v1/widgets/{widget_id}/export", headers=auth_headers)
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
```

- [X] **Step 2: Extend package dataclass**

Add fields:

```python
    example_props: dict
    behavior: dict
    ai_spec: dict
```

Add them to frontmatter in `pack()` and parse them in `unpack()`.

- [X] **Step 3: Update export/import routes**

Export from current revision. Import creates widget plus first revision with imported `behavior`, `example_props`, and `ai_spec`.

- [X] **Step 4: Run test**

Run:

```bash
cd apps/api
uv run pytest tests/test_widgets.py::test_widget_export_import_preserves_behavior_spec_and_example_props -q
```

Expected: PASS.

Checkpoint:

- `.swidget` frontmatter now carries `example_props`, `behavior`, and `ai_spec`.
- Export reads executable/source contract fields from the current revision.
- Import creates the widget plus an initial revision using imported behavior/spec/example props.
- Verified:
  - `cd apps/api && uv run pytest tests/test_widgets.py::test_widget_export_import_preserves_behavior_spec_and_example_props -q`
  - `cd apps/api && uv run pytest tests/test_widgets.py -q`
  - `cd apps/api && python -m py_compile src/slaides/widgets/package.py src/slaides/widgets/router.py`

---

### Task 11: Full Verification

**Files:**

- All modified files.

- [X] **Step 1: Run backend tests**

Run:

```bash
cd apps/api
uv run pytest -q
```

Expected: PASS.

- [X] **Step 2: Run frontend tests**

Run:

```bash
cd apps/web
npm test -- --run
```

Expected: PASS.

- [X] **Step 3: Manual smoke flow**

Run app stack:

```bash
make up
make migrate
make seed
```

Then verify manually:

1. Open editor.
2. Ask AI for a widget without specifying Quiet/Loud.
3. Confirm AI can ask a structured clarification question.
4. Choose the suggested option chip.
5. Insert the widget.
6. Confirm thumbnail uses example props.
7. Adjust widget from Quiet to Loud.
8. Start preview/live session.
9. Return to editor and confirm AI thread/spec context is still present.
10. Edit widget again and confirm revision history contains old and new revisions.

Expected: no silent Quiet downgrade, thread is persisted, and historical placement revision remains stable.

Checkpoint:

- Full backend verification passed after fixing migration `0014_tutorial_v2_reseed` to delete tutorial sessions before deleting tutorial decks.
- Full frontend verification initially exposed a stale pre-workflow-envelope test fixture in `widget-generation-loading.test.ts`; updated the fixture to return `{ type: "draft", widget: ... }`.
- Local stack smoke setup passed:
  - `make up`
  - `make migrate`
  - `make seed`
- API-level smoke against `http://127.0.0.1:8000/api/v1` passed for sign-in, widget creation with example props, AI thread persistence, placement attach, Quiet-to-Loud behavior swap, revision history, session creation, and placement revision stability.
- UI-click smoke was not completed in this environment because no browser automation tool was available in the session; the API smoke covered the same persisted data path but not visual interaction.
- Verified:
  - `cd apps/api && uv run pytest -q` -> 164 passed
  - `cd apps/web && npm test -- --run` -> 158 passed
  - `cd apps/web && npm run build` -> passed

Post-scrutinize fix checkpoint:

- Deck/placement payloads now embed the captured `WidgetRevision` source, so editor/live render paths can render the historical placement revision instead of silently resolving the mutable current widget body.
- Widget copy and onboarding tutorial creation now create and point at an initial revision instead of leaving `current_revision_id` empty.
- Adjust-mode AI chat now hydrates the persisted widget thread, accepts `plan` / `step` / `reflection` envelopes as progress instead of invalid responses, and appends user, assistant, and apply messages back to the widget AI thread.
- Create-mode widget save now snapshots the generated conversation into the newly created widget's AI thread before recording the apply event.
- Verified:
  - `cd apps/api && uv run pytest tests/test_placement_state.py::test_live_placement_uses_original_revision_after_widget_edit tests/test_widgets.py::test_copy_widget_into_another_deck_tracks_lineage tests/test_widgets.py::test_copy_widget_in_same_deck_creates_variant_with_suffix tests/test_onboarding.py::test_create_tutorial_for_builds_expected_deck -q` -> 4 passed
  - `cd apps/web && npm test -- --run tests/markdown.test.ts tests/widget-collection-loud-fallback.test.ts` -> 39 passed
  - `cd apps/web && npm run build` -> passed
  - `cd apps/api && uv run pytest -q` -> 164 passed
  - `cd apps/web && npm test -- --run` -> 162 passed

---

## Self-Review

Spec coverage:

- Human-in-loop behavior choice: Task 5 and Task 6.
- Behavior swapping during adjust: Task 3.
- Thread history: Task 4.
- Widget spec persistence: Task 1, Task 2, Task 4, Task 5.
- Agent plan/step/reflection UI: Task 5.
- Example props: Task 1, Task 2, Task 7.
- Widget version control: Task 1, Task 8.
- Present/session history foundation: Task 9.
- Export/import contract preservation: Task 10.

Known sequencing constraint:

- Task 2 depends on Task 1.
- Task 5 and later frontend changes depend on Task 4 API contracts.
- Task 9 depends on revision IDs being available in Task 1 and serialized in Task 2.

Risk:

- The migration uses `String(36)` UUID columns for portability; confirm it matches the project’s portable `GUID()` behavior in runtime models. If Alembic batch mode is needed for SQLite-only migrations, adapt before running full migration tests.
