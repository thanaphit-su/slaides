# Widgets v2 — design brief

Outcome of a brainstorm thread reshaping how widgets work in SLAIDES.
This is the durable reference; the staged rollout at the bottom is what
implementation work should follow.

## Context

Two limitations in widgets-as-shipped (M2 + M4):

1. **Widgets are not property-driven.** The generated HTML/JS bakes
   content (the poll question, the choices, etc.) into the source. The
   only way to customise is to hand-edit code, which is unfriendly for
   non-coders. Worse, attaching the same widget to two different slides
   makes both placements look identical even when the slides are about
   different topics.
2. **Widgets are always isolated.** Every audience member's iframe
   interacts independently. There's no way for an AI-generated widget
   to behave like an election poll or a Kahoot-style quiz where one
   audience's vote shows up on everyone else's screen. The only cases
   that *do* support cross-audience effects are the three hard-coded
   native interactions (`LivePollSlide`, `LiveQuestionSlide`,
   `LiveRandomAudienceSlide`) created during a live session — not
   AI-generated widgets attached to deck slides at authoring time.

Widgets v2 fixes both, and gives the LLM a clear contract for
generating both kinds.

## Topic 1 — Property-driven, reusable widgets

### Widget ownership

Widgets are **deck-local**. Every widget belongs to exactly one deck.
Cross-deck reuse goes through an explicit "copy widget from another
deck" flow which creates an independent widget row in the target deck,
carrying a soft `derived_from_id` pointer for lineage. The pointer is
informational only — it never enforces cascade, never propagates
edits, and the source can be deleted without affecting the copy.

The workspace-level Widgets tab has been removed. The editor's
right-sidebar library shows the current deck's widgets, with an explicit
copy flow for pulling in widgets from other decks.

### Adjust panel scope

When the user opens Adjust on a placement, they're editing **placement
props** by default — a form rendered from `widget.props_schema`. Two
escape hatches:

- **Edit code** tab — modifies the shared widget shell. The user is
  warned that all placements of this widget will be affected.
- **New variant** — clones the widget locally (in the same deck),
  swaps the placement to point at the clone, then opens the code
  editor on the clone. Source stays untouched.

This split is the difference between "tweak the question text for
this slide's instance" (the common case) and "rewrite the widget"
(the rare case). The current behaviour conflates the two and makes
the common case scary.

### `props_schema` contract

`widget.props_schema` is a strict JSON-Schema subset. Supported
keywords:

- `type` (`string` | `number` | `boolean` | `array` | `object`)
- `enum`
- `default`
- `description`
- `items` (with `type` and nested schema)
- `properties` (object shape)
- `minLength` / `maxLength`
- `minimum` / `maximum`

One SLAIDES-specific extension: `enum.from: "<other_prop>"` for
cross-field references. Example: a Kahoot-style quiz declares
`correct_answer: { type: "string", enum.from: "choices.id" }` — the
form picks the enum's options live from the current `choices` array.

The `widget_generate` system prompt is retrained to put **all
user-visible content in props with sensible defaults**. The shell
HTML/JS reads from `window.slaides.props` exclusively. The validator
that runs after streaming gains a check that no user-visible text in
the HTML is left hardcoded when the widget has a non-empty
`props_schema`.

### Migrations

When the LLM regenerates a widget shell and introduces new
`props_schema` keys, existing placements lazily backfill from
`props_schema[key].default` on read. Removed keys are tolerated (read
ignores them, write strips them). No data migration; the placement's
own `props` row only stores values that diverge from the schema's
defaults.

### Props form (hand-rolled)

A small Vue component renders the form from `props_schema`:

- Primitive renderers per type (`string` / `number` / `boolean`,
  plus `enum`-as-select).
- Array editor with add / remove / reorder for `items`.
- Object editor (nested form) for object-typed props.
- `enum.from` resolver that watches the referenced prop reactively.

Save flow PATCHes the placement, not the widget:

```
PATCH /decks/{deck_id}/slides/{slide_id}/widgets/{placement_id}
{ "props": { ... } }
```

This endpoint is implemented in the current API.

**Follow-up note.** Hand-rolling buys total control over the Editorial
Press visual vocabulary at the cost of extensibility. Revisit adopting
an off-the-shelf schema-form library (`formkit`, `vue-form-generator`,
or `jsf-vue`) once we've shipped this and felt out real UX needs.

## Topic 2 — Loud vs Quiet widgets

Two kinds, declared on the widget itself:

### Quiet

`behavior: { kind: "quiet" }`. Fully local to each viewer. No server
contact. The existing iframe CSP (`connect-src 'none'`) already
enforces this from the iframe side. The bridge offers
`setState`/`getState` for per-viewer scratch state (sessionStorage-
backed) but exposes no `contribute()` call.

Use cases: interactive plots, formula explorers, self-paced
flashcards, anything where each audience member's interaction is
private to them.

### Loud

`behavior: { kind: "loud", aggregator: <one-of-five>, contribution_schema: <json-schema> }`.
Audience contributions flow to the server, which aggregates into a
single shared state per `(session_id, placement_id)` and broadcasts
to every connected viewer.

### Aggregator vocabulary (5 total)

| Aggregator | State shape | Best for |
|---|---|---|
| `tally` | `{ choice_id → count }` | Election polls, Kahoot-style quizzes, image votes, confidence checks |
| `latest_per_participant` | `{ ref → value }` | Sentiment sliders, map pins, multi-criteria ratings — anywhere "one current answer per person" is the model |
| `append` | `[{ ref, value, ts }]` (capped) | Q&A threads, draw-canvas, open ideas |
| `set_union` | `{ value → count }` | Word clouds, "list 3 words that describe X" |
| `keyed_tally` | `[{ id, ref, value, ts, votes }]` | Brainstorm boards, idea jams, anything two-layer (item + votes per item) |

`histogram` was considered and dropped: widgets that wanted it
(sliders, ratings) need raw values on the server anyway, and
client-side bucketing of `latest_per_participant` is strictly more
flexible than committing to bucket boundaries upfront.

Scoring (e.g., Kahoot-style quizzes) is **not** a new aggregator. The
widget stores the answer key in props; the aggregator stays `tally`;
per-participant scoring is a post-session view that joins
`interaction_log` with `props.correct_answer` at transcript time.

### Local + Loud coexistence

`setState`/`getState` is always available to every widget regardless
of kind. A Loud widget can — and often will — also keep per-viewer
local scratch (current input, UI toggles, optimistic preview). The
`behavior` declaration only governs the contribution channel.

### Out-of-session behaviour

A Loud widget loaded outside a live session (in the editor preview,
or an exported `.slaides` opened standalone) acts Quiet and shows a
small banner: "Live behaviour only works during a session."
Contributions are no-ops; state never appears.

### Lifecycle rules

- **Presenter is observer-only.** Never contributes to a Loud widget.
  Their participant_ref doesn't exist server-side, so this falls out
  for free.
- **Editing widget props mid-session resets the tally** with a
  confirm modal. Mirrors the existing native-poll behaviour where
  choice edits are locked after the first vote (see
  `sessions/service.py:404`).
- **Source-widget edits never propagate to copies.** Once you copy a
  widget into your deck, you own it.
- **Placement state is frozen forever after session end** for
  transcript replay. No GC.

### Schema additions

**`widget` table changes (deck-scoped):**

- Replace `workspace_id` with `deck_id NOT NULL`.
- Add `derived_from_id UUID NULL` — no FK enforcement, soft pointer.
- Add `behavior JSONB NOT NULL DEFAULT '{"kind":"quiet"}'`.
- Server enforces on attach that `slide_widget.widget_id` and
  `slide_widget.slide_id` belong to the same deck.

**New `placement_state` table:**

```python
class PlacementState(Base):
    __tablename__ = "placement_state"

    session_id: Mapped[UUID]           # FK session.id, CASCADE
    placement_id: Mapped[str]          # slide_widget.placement_id
    # PK: (session_id, placement_id)

    widget_id: Mapped[UUID | None]     # convenience back-ref;
                                       #   nullable for deleted widgets
    aggregator: Mapped[str]            # one of the 5
    state: Mapped[dict]                # the projection audience tabs render
    contribution_count: Mapped[int]
    state_version: Mapped[int]         # increments per aggregation pass;
                                       #   used for optimistic concurrency +
                                       #   frontend dedupe
    opened_at: Mapped[datetime]        # first contribution timestamp
    updated_at: Mapped[datetime]
    closed_at: Mapped[datetime | None] # presenter "close voting"
```

Raw contributions still log to `interaction_log`, now keyed by
`placement_id` instead of `widget_id`, so we can replay per-placement
in transcripts.

### Bridge protocol

Audience widget code calls:

```js
window.slaides.contribute(value)
```

Quiet widgets that call this get a no-op (or a console warning in
dev). Loud widgets that call it with a payload not matching the
declared `contribution_schema` get a rejection event back via the
bridge.

WebSocket events on the existing session channel:

- audience → host: `widget.contribute { placement_id, value }`
- host → all: `widget.state { placement_id, state, state_version, closed }`
- host → all: `widget.closed { placement_id }`
- host → all: `widget.reset { placement_id }`

Late-joiner snapshot: `GET /sessions/:id/audience` adds
`placement_states[]` so newly connected audiences see current state
without a separate fetch round.

### Security guards

1. **Audience-scope:** server rejects `widget.contribute` whose
   `placement_id` doesn't belong to a slide or session_slide in the
   participant's session.
2. **Schema validation:** contribution payload must validate against
   the widget's declared `contribution_schema` before aggregation.
3. **Per-(participant, placement) rate limit:** Redis `INCR` on a
   minute bucket, mirroring the existing LLM limiter.
4. **Per-placement state size caps:** conservative defaults per
   aggregator:
   - `tally` — unlimited choice count (poll has at most a few dozen)
   - `latest_per_participant` — bounded by `SESSION_AUDIENCE_CAP`
   - `append` — 200 entries default; oldest dropped or contributions rejected with 429
   - `set_union` — 500 distinct values
   - `keyed_tally` — 100 items
   - Single contribution payload — 2 KB

### Generation UX

In `WidgetCollection` chat composer (above the textarea):

- Segmented control: **Quiet — private to each viewer** /
  **Loud — shared across the room**.
- When Loud is selected, a second compact picker appears: aggregator
  type, with a "Let AI choose" default.
- Both selections are piped into the `widget_generate` prompt
  context as a new `BEHAVIOR_CONTRACT` section parallel to
  `WIDGET_THEME_CONTRACT`. It explains the two modes, gives a
  semantic skeleton per aggregator (similar to the existing per-kind
  skeletons), and forbids cross-mode misuse (`contribute()` calls in
  a Quiet widget; subscribing to `state.broadcast` from a Quiet
  widget; etc.).
- A post-stream validator (added next to `_scan_theme_violations`)
  checks that a Loud widget actually calls `slaides.contribute(...)`
  somewhere in its JS, that its `props_schema` declares the
  contribution shape, and that the declared aggregator's state shape
  is referenced in the render code. Failures surface as warnings the
  same way hex colors do today — non-blocking, user has the call.

## Staged rollout

Four shippable slices, each with real user value:

### Step 1 — Props panel (Quiet-only)

- Tighten the JSON-Schema subset.
- Hand-roll the form renderer.
- Add `PATCH .../widgets/{placement_id}` endpoint and server-side
  schema validation.
- Retrain the `widget_generate` system prompt to put content in props.
- Add the post-stream hardcoded-content validator.

No new runtime behaviour, just stops widgets from being write-once
content-locked. **Biggest UX win, smallest risk** — this alone is
probably the largest quality-of-life improvement in the whole brief.

### Step 2 — Deck-local widget migration

- Alembic migration: snapshot-copy `workspace`-scoped widgets into
  the decks that reference them via `slide_widget`. Unreferenced
  widgets land in a per-workspace auto-created "Library" deck so
  nobody loses work.
- Schema: replace `widget.workspace_id` with `widget.deck_id NOT
  NULL`; add `derived_from_id UUID NULL` and
  `behavior JSONB NOT NULL DEFAULT '{"kind":"quiet"}'`.
- Server enforces same-deck constraint on attach.
- Add `POST /decks/{target}/widgets/import?source_widget_id=...`
  endpoint and the "copy from another deck" UI.
- Editor's right-sidebar library is rescoped to the current deck.
- Remove the workspace-level Widgets tab placeholder.

### Step 3 — Unified protocol on native polls first  *(shipped 2026-05-24)*

- New `apps/api/src/slaides/sessions/aggregators.py` ships all five
  aggregator primitives as pure functions.
- `_recompute_poll_tally` and `record_open_answer` fold through
  `tally_contribute` / `append_contribute` so the aggregator code is
  exercised on every native interaction.
- WS layer accepts `widget.contribute` audience-to-host events and
  broadcasts canonical `widget.state { placement_id, state,
  state_version, closed }` alongside the legacy `interaction.tally` /
  `interaction_results.updated` events. `_state_version` is persisted
  on `session_slide.results` so out-of-order broadcasts on reconnect
  can't roll back.
- Frontend session store sends `widget.contribute` from
  `submitPollVote` / `submitPollOther` / `submitOpenAnswer`, and a
  new `widget.state` handler respects `state_version` for stale-drop
  and merges embedded `spec_state` back into the slide spec.
- Native `LivePollSlide` / `LiveQuestionSlide` UIs are untouched — the
  new wire is invisible to the audience.

### Step 4 — Open Loud widgets to AI-generated widgets  *(shipped 2026-05-25)*

- New `placement_state` table (migration 0012, PK `(session_id, placement_id)`)
  persists each Loud widget's audience-visible state with monotonic
  `state_version`, `contribution_count`, and the `closed_at` freeze field
  for transcript replay.
- `placement_state_service` wraps the aggregator primitives behind a single
  `contribute_to_placement(...)` entry; the placement's aggregator is sticky
  after the first write so a widget can't switch shape mid-session.
- WS `_handle_iframe_contribute` branch: fires when `widget.contribute`
  carries a non-UUID placement_id. Audience-scope guard (placement's deck
  must match the participant's session's deck), behavior check
  (`kind == "loud"` with a known aggregator), per-(participant, placement)
  Redis rate limit (60/min), then aggregator dispatch + persistence +
  `widget.state` broadcast.
- Audience snapshot returns `placement_states[]` so late joiners see the
  current projection without an extra round.
- Bridge surface: `window.slaides.contribute(value)` + `slaides.on('state',
  cb)`; `behavior` baked into iframe boot so widget JS can branch on
  `slaides.behavior.kind`. WidgetFrame allows `widget.contribute` through
  the relay; session store caches the projection in `placementStates` and
  dispatches inbound state into mounted iframes via the existing
  `slaides:widget-broadcast` CustomEvent.
- LLM `BEHAVIOR CONTRACT` prompt section documents the Quiet/Loud split,
  the five aggregators with shapes + use cases, the bridge skeleton, and
  the `contribution_schema` declaration.
- `_scan_behavior_violations` surfaces Quiet widgets that call `contribute()`,
  Loud widgets that never call it or never subscribe to `state`, unknown
  aggregator names, and missing `contribution_schema`.
- Current `WidgetCollection` create mode does not expose a manual Quiet/Loud
  picker. Behavior is selected through AI clarification questions when the
  prompt is ambiguous, and the chosen contract is carried into the
  `widget_generate` context.

Each step is independently shippable. Steps 1 and 2 can land in
either order; Steps 3 and 4 depend on Step 2 (deck-local widgets) and
on each other.

## Decision log (referenced for future regressions)

| Decision | Choice |
|---|---|
| Adjust default scope | Placement props |
| Widget ownership | Deck-local |
| Cross-deck reuse | Copy with `derived_from_id` lineage |
| Source edits → copies | Never propagate |
| `props_schema` shape | JSON Schema subset with `enum.from` extension |
| Schema migrations on new keys | Lazy default backfill |
| Workspace widget migration | Snapshot copy (Migration A) |
| `histogram` aggregator | Dropped; client-side bucketing of `latest_per_participant` |
| `keyed_tally` aggregator | Included in v1 |
| Scoring (Kahoot-style) | Props + post-session view, not a new aggregator |
| Bridge contribution API | Single canonical `contribute(value)` |
| Local state availability | Always available, both kinds |
| Out-of-session Loud widgets | Act Quiet with banner |
| Presenter in Loud widgets | Observer-only |
| Edit mid-session | Resets tally with confirm modal |
| End-of-session state | Frozen forever for transcript record |
| State storage | Dedicated `placement_state` table |
| Form renderer | Hand-rolled now; revisit library later |
