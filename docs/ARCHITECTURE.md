# SLAIDES — Architecture

## System overview

```
                      ┌──────────────────────────────────────────────────────┐
                      │                                                      │
                      │   Browser (Vue 3 + Vite)                             │
                      │                                                      │
                      │   ┌──────────┐  ┌──────────┐  ┌──────────┐          │
                      │   │ Editor   │  │ Presenter│  │ Audience │          │
                      │   └────┬─────┘  └────┬─────┘  └────┬─────┘          │
                      │        │             │             │                │
                      │   ┌────┴─────────────┴─────────────┴────┐           │
                      │   │  Widget sandbox  (iframe srcdoc)    │           │
                      │   │  postMessage bridge `window.slaides`│           │
                      │   └─────────────────────────────────────┘           │
                      │                                                      │
                      └─────────────┬───────────────────────┬────────────────┘
                                    │ HTTPS                 │ WSS
                                    ▼                       ▼
                            ┌──────────────────────────────────────┐
                            │       FastAPI                         │
                            │  ┌─────────┐  ┌─────────┐  ┌──────┐  │
                            │  │ REST    │  │ WS hub  │  │ LLM  │  │
                            │  │ /api/v1 │  │ /ws/... │  │ proxy│  │
                            │  └────┬────┘  └────┬────┘  └──┬───┘  │
                            └───────┼─────────────┼─────────┼──────┘
                                    │             │         │
                                    │             ▼         │
                                    │      ┌──────────┐     │
                                    │      │  Redis   │     │
                                    │      │ pub/sub  │     │
                                    │      │ presence │     │
                                    │      └──────────┘     │
                                    ▼                       ▼
                            ┌────────────────┐     ┌────────────────┐
                            │   Supabase     │     │  OpenAI-comp.  │
                            │  PostgreSQL    │     │   endpoint     │
                            │  + Auth        │     │ (per workspace)│
                            │  + Storage     │     └────────────────┘
                            └────────────────┘
```

## Components

### Frontend — Vue 3 + Vite

- **Routes:** `/signin`, `/workspace`, `/editor/:deck`, `/present/:session`, `/j/:code` (audience landing), `/audience/:session`.
- **State:** Pinia stores. One store per major domain: `auth`, `workspace`, `editor`, `session`, `widgets`.
- **Markdown:** `remark` + custom plugin to lift `{{widget:id}}` into a Vue component.
- **Editor surface:** Monaco for raw-markdown edit-mode; a custom contenteditable layer for inline edits in rendered mode. Slides are split on `H1` boundaries at save.
- **Realtime:** A single `useSession()` composable owns the WebSocket. It surfaces reactive `slideIdx`, `participants`, `questions`, `interactions`.

### Backend — FastAPI

- Python 3.12, `uvicorn` workers behind a reverse proxy.
- Domain split into routers: `auth`, `decks`, `slides`, `widgets`, `sessions`, `participants`, `interactions`, `llm`.
- SQLAlchemy 2.x async with Pydantic v2 schemas. Alembic for migrations.
- Background tasks via Celery + Redis (transcript summarisation, exports).
- WebSocket hub: one async task per session that fans out events from Redis pub/sub.

### Realtime — WebSockets + Redis

- Each session has a Redis channel `sess:{id}`.
- The FastAPI process subscribes once per running session, broadcasts to all attached WS clients.
- Presence: `SET sess:{id}:participant:{ref} EX 30` heartbeat from each client; expiry counts as leave.
- This makes the WS layer horizontally scalable — every API node can serve any session, and Redis is the source of truth for live state.

### LLM proxy

- A thin internal router that hides workspace-scoped keys from the browser.
- POST `/api/v1/llm/complete` with `{ purpose, prompt, context, model_override? }` → streams server-sent events back.
- Three purposes in v0.1: `inline_write`, `interpret`, `widget_generate`.
- Per-workspace rate limit (60/min).
- Logs `{ purpose, prompt_hash, latency_ms, tokens_in, tokens_out }` for cost tracking. Prompt text is NOT logged by default — opt-in per workspace.

### Database — Supabase PostgreSQL

We use Supabase for managed Postgres + auth + storage. Schema lives in `migrations/` regardless — we don't depend on Supabase RPC.

## Data model

```sql
-- ===== identity =====
create table workspace (
  id           uuid primary key,
  name         text not null,
  llm_base_url text not null default 'https://api.openai.com/v1',
  llm_key_enc  bytea,                           -- Fernet-encrypted API key (LLM_ENCRYPTION_SECRET)
  llm_models   jsonb default '[]',              -- Array of model configs: [{id, max_context_window, max_output_tokens, temperature, top_p, frequency_penalty, presence_penalty, supports_image_input}]
  llm_capability_models jsonb default '{}',     -- Map: {inline_write: model_id, interpret: model_id, widget_generate: model_id}
  created_at   timestamptz default now()
);
-- Note: llm_caps boolean map is derived from llm_capability_models at read time for backwards compatibility

create table app_user (
  id           uuid primary key,
  workspace_id uuid references workspace(id),
  supabase_user_id uuid,                -- Links to Supabase Auth (unique, nullable)
  email        text unique not null,
  display_name text,
  role         text check (role in ('owner','instructor')) default 'instructor',
  approval_status text check (approval_status in ('pending','approved','rejected')) default 'pending',
  approved_at  timestamptz,
  created_at   timestamptz default now()
);
-- Note: Password auth handled by Supabase Auth; app_user stores only approval/role metadata

-- ===== authoring =====
create table deck (
  id           uuid primary key,
  workspace_id uuid references workspace(id) not null,
  owner_id     uuid references app_user(id) not null,
  title        text not null,
  subtitle     text,
  cover        text,
  manifest     jsonb not null default '{}',     -- theme, layout toggles, etc.
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

create table section (
  id           uuid primary key,
  deck_id      uuid references deck(id) on delete cascade,
  title        text not null,
  position     int not null
);

create table slide (
  id           uuid primary key,
  deck_id      uuid references deck(id) on delete cascade,
  section_id   uuid references section(id),
  position     int not null,
  kicker       text,
  markdown     text not null,                   -- the source of truth
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

-- ===== Widgets v2 — deck-local with revisions (migrations 0011, 0015) =====
create table widget (
  id           uuid primary key,
  deck_id      uuid references deck(id) on delete cascade not null,  -- Widgets v2: deck-local ownership
  derived_from_id uuid,                    -- Soft pointer to source widget (cross-deck copy lineage, no FK)
  name         text not null,
  kind         text not null,                   -- 'poll' | 'question' | 'quiz' | 'plotter' | 'wordcloud' | 'custom' | ...
  description  text,
  html         text not null default '',
  js           text,
  css          text,
  props_schema jsonb default '{}',
  example_props jsonb default '{}',              -- Sample values for preview/thumbnail rendering
  tags         jsonb default '[]',               -- JSON array (portable PG/SQLite)
  version      text default 'v0.1',
  behavior     jsonb not null default '{"kind": "quiet"}',  -- Widgets v2: {"kind":"quiet"} | {"kind":"loud","aggregator":"tally",...}
  ai_spec      jsonb default '{}',               -- Structured intent/spec from AI generation
  current_revision_id uuid,                      -- FK to widget_revision (soft during migration, enforced in PG)
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

-- Widget revision tracking (migration 0015)
create table widget_revision (
  id           uuid primary key,
  widget_id    uuid references widget(id) on delete cascade not null,
  version_number int not null,                   -- Monotonic per widget
  html         text not null default '',
  js           text,
  css          text,
  props_schema jsonb not null default '{}',
  example_props jsonb not null default '{}',
  behavior     jsonb not null default '{"kind": "quiet"}',
  ai_spec      jsonb not null default '{}',
  created_reason text,                           -- 'migration_backfill' | 'ai_apply' | 'manual_save' | 'rollback'
  created_at   timestamptz default now(),
  unique (widget_id, version_number)             -- Enforce version sequence
);
create index ix_widget_revision_widget on widget_revision (widget_id, version_number);

-- AI conversation threads per widget (migration 0015)
create table widget_ai_thread (
  id           uuid primary key,
  widget_id    uuid references widget(id) on delete cascade not null,
  title        text,
  compact_summary jsonb default '{}',
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

create table widget_ai_message (
  id           uuid primary key,
  thread_id    uuid references widget_ai_thread(id) on delete cascade not null,
  role         text not null check (role in ('user', 'assistant')),
  message_type text not null,                    -- 'question' | 'draft' | 'plan' | 'step' | 'reflection'
  content      jsonb not null default '{}',
  revision_id  uuid references widget_revision(id),  -- Links draft/apply to specific revision
  created_at   timestamptz default now()
);
create index ix_widget_ai_message_thread_created on widget_ai_message (thread_id, created_at);

create table slide_widget (
  slide_id     uuid references slide(id) on delete cascade,
  placement_id text not null,                   -- the `id` inside `{{widget:id}}` in markdown
  widget_id    uuid references widget(id) not null,
  revision_id  uuid references widget_revision(id),  -- Widgets v2: snapshot of widget at attach time
  props        jsonb default '{}',
  primary key (slide_id, placement_id)
);

-- ===== live sessions =====
create table session (
  id           uuid primary key,
  deck_id      uuid references deck(id),
  owner_id     uuid references app_user(id),
  workspace_id uuid references workspace(id),
  code         text unique not null,            -- SLD-XXXX-XX
  salt         text not null,                   -- for anon-hashing
  started_at   timestamptz default now(),
  ended_at     timestamptz,
  current_slide_id uuid,                        -- FK dropped (migration 0004) — can hold slide.id or session_slide.id
  is_preview   boolean default false,           -- Preview tab ephemeral sessions (migration 0013)
  config       jsonb default '{}'               -- transcripts on/off, anonymous allowed, etc.
);
-- Note: current_slide_id has no FK constraint — can reference either slide.id or session_slide.id

create table participant (
  id           uuid primary key,
  session_id   uuid references session(id) on delete cascade,
  user_id      uuid references app_user(id),    -- nullable for guests
  email        text,                            -- nullable for fully anonymous
  display_name text,
  anon         boolean default false,
  ref          text not null,                   -- user_id for registered, sha256(email+salt) for guests
  joined_at    timestamptz default now(),
  left_at      timestamptz,
  unique (session_id, ref)
);

create table interaction_log (
  id           bigserial primary key,
  session_id   uuid references session(id) on delete cascade,
  slide_id     uuid references slide(id),
  session_slide_id uuid,                        -- For native live interactions (migration 0006)
  widget_id    uuid references widget(id),
  participant_ref text not null,                -- never raw email
  kind         text not null,                   -- 'join' | 'vote' | 'text' | 'slider' | 'interpret' | 'question' | 'answer' | ...
  payload      jsonb not null,
  occurred_at  timestamptz default now()
);
create index ix_log_session on interaction_log (session_id, occurred_at);
create index ix_log_widget  on interaction_log (widget_id);
create index ix_log_session_slide on interaction_log (session_slide_id);

create table question (
  id           uuid primary key,
  session_id   uuid references session(id) on delete cascade,
  slide_id     uuid references slide(id),
  participant_ref text not null,
  anon         boolean default false,
  text         text not null,
  answered_at  timestamptz,
  raised_at    timestamptz default now()
);

-- Session-only interaction slides ("live" polls/questions opened during a session).
-- These do NOT mutate the deck — they live with the session forever.
create table session_slide (
  id           uuid primary key,
  session_id   uuid references session(id) on delete cascade,
  parent_slide_id uuid references slide(id),   -- the deck slide the instructor was on
  position     int not null,                   -- effective position in the session's slide order
  kind         text not null,                  -- 'poll' | 'question' | 'random' | 'widget'
  spec         jsonb not null,                 -- the poll question/options, etc.
  results      jsonb default '{}',             -- aggregated final state at session end (legacy path)
  inverted_theme boolean default false,        -- optional legacy/explicit theme inversion; new live interactions inherit current theme
  widget_id    uuid references widget(id),     -- For widget-type session slides
  opened_at    timestamptz default now(),
  closed_at    timestamptz
);
create index ix_session_slide on session_slide (session_id, position);

-- Placement state for Loud widgets (migration 0012, Widgets v2 Step 4)
create table placement_state (
  session_id   uuid references session(id) on delete cascade,
  placement_id text not null,                  -- Matches slide_widget.placement_id
  widget_id    uuid references widget(id) not null,
  aggregator   text not null,                  -- 'tally' | 'latest_per_participant' | 'append' | 'set_union' | 'keyed_tally'
  state        jsonb not null default '{}',    -- Aggregated state (shape depends on aggregator)
  state_version int not null default 0,        -- Monotonic, for optimistic concurrency
  contribution_count int default 0,
  closed_at    timestamptz,                    -- Set when presenter closes voting or session ends
  primary key (session_id, placement_id)
);
create index ix_placement_state_session on placement_state (session_id);

-- ===== LLM accounting =====
create table llm_call (
  id           bigserial primary key,
  workspace_id uuid references workspace(id),
  user_id      uuid references app_user(id),
  session_id   uuid references session(id),
  purpose      text not null,                   -- 'inline_write' | 'interpret' | 'widget_generate' | 'summarise'
  model        text,
  prompt_hash  text,
  prompt_text  text,                            -- null unless workspace opts in
  latency_ms   int,
  tokens_in    int,
  tokens_out   int,
  occurred_at  timestamptz default now()
);
```

### Why `participant_ref`?

The interaction log is queried two ways:
- "Show me everything Sara K. did in this session." → join `participant_ref` to `participant`.
- "Show me everything anonymous-attendee-#3 did across this session." → group by `participant_ref` without resolving.

Storing the ref instead of `participant_id` keeps anonymous rows perfectly portable when we re-derive the hash for a re-export, and it makes the log queryable even after a participant row is purged on request.

## REST API surface

All routes under `/api/v1`. JSON in/out. Standard pagination via `?cursor=&limit=`.

| Method | Path | Purpose |
|---|---|---|
| POST  | `/auth/signin`                  | Instructor login → JWT pair |
| POST  | `/auth/refresh`                 | Refresh access token |
| POST  | `/auth/guest`                   | Guest join: { code, email, display_name, anonymous } → session token |
| GET   | `/workspace`                    | Current workspace (settings, capabilities) |
| PATCH | `/workspace`                    | Update LLM config / toggles |
| GET   | `/decks`                        | List decks |
| POST  | `/decks`                        | Create empty deck |
| GET   | `/decks/:id`                    | Full deck (sections, slides, slide_widgets) |
| PATCH | `/decks/:id`                    | Rename, theme, layout |
| DELETE| `/decks/:id`                    | Delete |
| POST  | `/decks/:id/duplicate`          | Duplicate |
| POST  | `/decks/:id/export`             | → `.slaides` zip (signed URL) |
| POST  | `/decks/import`                 | Upload a `.slaides` zip |
| PUT   | `/decks/:id/slides/:sid`        | Replace slide markdown (chunked autosave) |
| POST  | `/decks/:id/slides`             | Insert slide at position |
| DELETE| `/decks/:id/slides/:sid`        | Delete slide |
| GET   | `/api/v1/widgets`                           | List all widgets (workspace-wide, for cross-deck picker) |
| GET   | `/api/v1/decks/:deck_id/widgets`            | List widgets in specific deck |
| POST  | `/api/v1/decks/:deck_id/widgets`            | Create widget in deck |
| POST  | `/api/v1/decks/:deck_id/widgets/copy`       | Copy widget from another deck (body: {source_widget_id}) |
| POST  | `/api/v1/decks/:deck_id/widgets/import`     | Import `.swidget` into deck |
| PATCH | `/widgets/:id`                              | Update widget metadata/source |
| DELETE| `/widgets/:id`                              | Delete widget (409 if in use; `?force=true` cascades) |
| POST  | `/widgets/:id/export`                       | Export as `.swidget` file |
| GET   | `/widgets/:id/revisions`                    | List all revisions |
| POST  | `/widgets/:id/revisions/:rev_id/rollback`   | Rollback to specific revision |
| GET   | `/widgets/:id/ai-thread`                    | Get or create AI conversation thread |
| GET   | `/widgets/:id/ai-thread/messages`           | List messages in thread |
| POST  | `/decks/:deck_id/slides/:slide_id/widgets`  | Attach widget to slide (enforces 1-per-slide, same-deck) |
| PATCH | `/decks/:deck_id/slides/:slide_id/widgets/:placement_id` | Update placement props (validates against props_schema) |
| DELETE| `/decks/:deck_id/slides/:slide_id/widgets/:placement_id` | Detach widget, strip placeholder from markdown |
| POST  | `/sessions`                     | Start a session from a deck → returns code + URL |
| GET   | `/sessions/:id`                 | Session snapshot |
| POST  | `/sessions/:id/end`             | End a session |
| GET   | `/sessions/:id/transcript`      | Full transcript (paginated) |
| GET   | `/sessions/:id/transcript.csv`  | Export CSV |
| POST  | `/llm/complete`                 | Stream LLM response (SSE) |

## WebSocket protocol

```
wss://api.slaides.app/ws/sessions/{id}?token=...
```

All messages JSON, `{type, ...}` shape. See SPEC §10 for the full list.

**Connection flow:**

1. Client connects with token → server validates, joins to Redis channel.
2. Server sends `session.state` snapshot.
3. Bidirectional flow until close.
4. On disconnect, server fires `participant.left` after 30s grace.

## Widget Behavior Contract (Widgets v2)

Widgets declare behavior in the `behavior` JSON field:

### Quiet Widgets (default)
```json
{ "kind": "quiet" }
```
- Run locally in the iframe
- No audience aggregation
- Use `window.slaides.setState/getState()` for persistence
- Examples: Concept cards, quizzes, calculators, carousels

### Loud Widgets
```json
{
  "kind": "loud",
  "aggregator": "tally" | "latest_per_participant" | "append" | "set_union" | "keyed_tally",
  "contribution_schema": { /* JSON Schema for contribution value */ }
}
```
- Aggregate contributions across all audience members
- Must call `window.slaides.contribute(value)` to send contribution
- Must subscribe via `window.slaides.on('state', callback)` for state updates
- State persisted to `placement_state` table per (session_id, placement_id)
- Examples: Live polls, word clouds, Q&A boards, reaction walls

### Five Aggregators

| Aggregator | State Shape | Use Case |
|------------|-------------|----------|
| `tally` | `{ tally: {choice→int}, voters: int }` | Polls, multiple-choice quizzes |
| `latest_per_participant` | `{ values: {ref→value} }` | Sliders, ratings, one value per user |
| `append` | `{ entries: [{ref,value,ts}], total: int }` | Q&A, brainstorming, idea collection |
| `set_union` | `{ counts: {value→int} }` | Word clouds, tag clouds |
| `keyed_tally` | `{ items: [{id,ref,value,ts,votes,voters}] }` | Reaction boards, prioritization |

### Placement State Service

The `placement_state_service.py` provides:

```python
async def contribute_to_placement(
    session, session_id, placement_id, widget_id,
    aggregator, value, participant_ref
) -> tuple[PlacementState, dict]:
    """
    Upsert placement_state row for (session_id, placement_id).
    Run aggregator primitive: new_state = aggregator(old_state, value, participant_ref).
    Increment state_version and contribution_count.
    Return (row, public_state_projection).
    """
```

- Aggregator is sticky per placement — cannot change mid-session
- `state_version` used for optimistic concurrency (drop stale events on reconnect)
- `closed_at` set when presenter closes voting or session ends
- After close, contributions dropped but state preserved for transcript replay

## Widget sandbox

```html
<iframe sandbox="allow-scripts" srcdoc="<!doctype html><html>...widget..."></iframe>
```

Before the widget's script runs, the host injects a bridge script (via the srcdoc template) that defines `window.slaides`. All host-bound calls become `parent.postMessage({type, ...}, ORIGIN)`. The host listens on its window and routes the message to the right session WebSocket.

Why iframe and not Web Components? Because v0.1 lets users hand-edit (or LLM-generate) arbitrary HTML/JS. Iframe sandboxing is the simplest container that *guarantees* the widget cannot reach the deck DOM or the parent's storage.

## Deployment shape

- **API** — One stateless FastAPI service. Horizontally scalable. Behind a reverse proxy (Caddy / nginx) for TLS.
- **Realtime** — Same FastAPI processes; Redis is the broker.
- **Worker** — A small Celery worker for async exports + transcript summarisation.
- **DB** — Supabase project (Postgres + auth + signed storage URLs for exports).
- **Cache / Pub-Sub** — Redis (managed, e.g. Upstash).
- **Static frontend** — Vue 3 build deployed to a CDN (e.g. Cloudflare Pages). Talks to the API by configured base URL.

## Observability

- Structured JSON logs (`structlog`).
- Trace IDs propagated from frontend → API → LLM proxy.
- Key SLO dashboards: session-event latency p95, LLM call cost per workspace, audience join success rate.

---

## Migration History

### Migration 0015 (2026-05-26) — Widget Revisions + AI Threads
- Added `widget_revision` table for versioned widget source storage
- Added `widget_ai_thread` and `widget_ai_message` tables for AI conversation persistence
- Added `widget.current_revision_id` and `slide_widget.revision_id` columns
- Widgets now snapshot revision at attach time; placements render historical revision
- AI Adjust creates new revision instead of overwriting; rollback supported

### Migration 0014 (2026-05-26) — Tutorial v2 Reseed
- Split tutorial §06 into §06a (Quiet) and §06b (Loud) to fix 1-widget-per-slide violation
- Placement IDs now use `{slug}-{8hex}` format (was bare slug)
- Tutorial deck is now 10 slides (was 9)

### Migration 0013 (2026-05-25) — Preview Sessions
- Added `session.is_preview` column
- Preview tab sessions marked ephemeral, excluded from "Resume session" logic

### Migration 0012 (2026-05-23) — Placement State
- Added `placement_state` table for Loud widget aggregation
- Composite PK `(session_id, placement_id)` with state_version for optimistic concurrency
- Five aggregators: tally, latest_per_participant, append, set_union, keyed_tally

### Migration 0011 (2026-05-23) — Widget Deck-Local Ownership
- Replaced `widget.workspace_id` with `widget.deck_id NOT NULL CASCADE`
- Added `widget.derived_from_id` (soft pointer for cross-deck copy lineage)
- Added `widget.behavior` JSONB column (Quiet/Loud declaration)
- Multi-deck-referenced widgets snapshot-copied into per-deck clones

### Migration 0010 (2026-05-22) — Split LLM Caps
- Split `workspace.llm_caps` JSON into `llm_models` + `llm_capability_models`
- Data-preserving; booleans derived at read time for compatibility

### Migration 0009 (2026-05-22) — Drop Password Hash
- Removed `app_user.password_hash` column after Supabase Auth migration

### Migration 0008 (2026-05-21) — Supabase Auth + Approval
- Added `app_user.supabase_user_id` (unique, nullable)
- Added `approval_status` (pending/approved/rejected) and `approved_at`

### Migration 0007 (2026-05-21) — Session Slide Theme Default
- Changed `session_slide.inverted_theme` server default to `false`
- New live interactions inherit current presentation theme

### Migration 0006 (2026-05-21) — Interaction Log Session Slide
- Added `interaction_log.session_slide_id` for native live interactions

### Migration 0004 (2026-05-19) — Session Current Slide FK
- Dropped FK on `session.current_slide_id` to allow slide.id or session_slide.id

### Migration 0003 (2026-05-19) — Sessions Schema
- Added session, participant, question, interaction_log, session_slide

### Migration 0002 (2026-05-19) — Widgets Schema
- Added widget, slide_widget (PK `(slide_id, placement_id)`)

### Migration 0001 (2026-05-19) — M0/M1 Foundation
- Added workspace, app_user, deck, section, slide
