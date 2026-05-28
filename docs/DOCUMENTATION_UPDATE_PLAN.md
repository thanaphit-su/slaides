# Documentation Update Implementation Plan

**Priority:** P0 (Blocker)  
**Created:** 2026-05-28  
**Goal:** Update ARCHITECTURE.md, SPEC.md, and REQUIREMENTS.md to reflect current implementation state

---

## Task 1: ARCHITECTURE.md Complete Rewrite

### 1.1 Widget Data Model Updates

**Current state (WRONG):**
```markdown
Widget:
  - id, workspace_id, name, kind, description
  - html, js, css, props_schema, tags, version
  - created_at, updated_at
```

**Should be:**
```markdown
Widget:
  - id, deck_id (NOT NULL, CASCADE), derived_from_id (soft pointer)
  - name, kind, description, html, js, css
  - props_schema, tags, version
  - behavior (JSON, default {"kind": "quiet"})
  - ai_spec (JSON), example_props (JSON)
  - current_revision_id (FK → widget_revision.id, nullable during migration)
  - created_at, updated_at

WidgetRevision:
  - id, widget_id (FK → widget.id CASCADE)
  - version_number (unique per widget)
  - html, js, css, props_schema, example_props
  - behavior (JSON), ai_spec (JSON)
  - created_reason, created_at
  - Indexes: (widget_id, version_number)

WidgetAiThread:
  - id, widget_id (FK → widget.id CASCADE)
  - title, compact_summary (JSON)
  - created_at, updated_at

WidgetAiMessage:
  - id, thread_id (FK → widget_ai_thread.id CASCADE)
  - role ("user" | "assistant"), message_type ("question" | "draft" | "plan" | "step" | "reflection")
  - content (JSON), revision_id (FK → widget_revision.id, nullable)
  - created_at
  - Index: (thread_id, created_at)

SlideWidget:
  - slide_id (PK), placement_id (PK)
  - widget_id (FK → widget.id)
  - revision_id (FK → widget_revision.id, nullable)  -- NEW
  - props (JSON)

PlacementState:
  - session_id (PK), placement_id (PK)
  - widget_id (FK → widget.id)
  - aggregator (tally | latest_per_participant | append | set_union | keyed_tally)
  - state (JSON), state_version (monotonic integer)
  - contribution_count, closed_at (nullable)
  - Index: session_id
```

**Source files to reference:**
- `apps/api/src/slaides/db/models.py` lines 140-239
- `apps/api/migrations/versions/0011_widget_deck_local.py`
- `apps/api/migrations/versions/0012_placement_state.py`
- `apps/api/migrations/versions/0015_widget_revisions_ai_threads.py`

---

### 1.2 API Routes Update

**Current state (WRONG):**
```markdown
POST   /widgets              -- Create workspace widget
GET    /widgets              -- List workspace widgets
POST   /widgets/import       -- Import .swidget file
```

**Should be:**
```markdown
# Deck-scoped widget CRUD (primary)
GET    /api/v1/decks/{deck_id}/widgets                    -- List deck's widgets
POST   /api/v1/decks/{deck_id}/widgets                    -- Create widget in deck
POST   /api/v1/decks/{deck_id}/widgets/import             -- Import .swidget into deck
POST   /api/v1/decks/{deck_id}/widgets/copy               -- Copy from another deck
       Body: { source_widget_id }

# Cross-deck picker (workspace-wide, read-only)
GET    /api/v1/widgets                                    -- List all widgets (for picker)

# Widget management
POST   /widgets/{id}/export                               -- Export as .swidget
PATCH  /widgets/{id}                                      -- Update widget metadata/source
DELETE /widgets/{id}                                      -- Delete (409 if in use, force=true cascades)
       Query: ?force=true

# Revision management
GET    /widgets/{id}/revisions                            -- List all revisions
POST   /widgets/{id}/revisions/{rev_id}/rollback          -- Rollback to revision

# AI threads
GET    /widgets/{id}/ai-thread                            -- Get or create AI thread
GET    /widgets/{id}/ai-thread/messages                   -- List messages in thread

# Slide attachment (deck-scoped, same-deck constraint)
POST   /api/v1/decks/{deck_id}/slides/{slide_id}/widgets  -- Attach widget to slide
       Body: { widget_id }
       Returns: 409 if slide already has widget OR if widget is from different deck
       Auto-appends {{widget:placement_id}} to slide markdown

PATCH  /api/v1/decks/{deck_id}/slides/{slide_id}/widgets/{placement_id}
       Body: { props }                                    -- Update placement props
       Validates against widget.props_schema, returns 422 on violation

DELETE /api/v1/decks/{deck_id}/slides/{slide_id}/widgets/{placement_id}
       Strips {{widget:placement_id}} from slide markdown
```

**Source files:**
- `apps/api/src/slaides/widgets/router.py`
- `apps/api/src/slaides/widgets/props_validator.py`

---

### 1.3 Loud/Quiet Behavior Contract

**Add new section:**

```markdown
## Widget Behavior Contract

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
- State persisted to `placement_state` table per session
- Examples: Live polls, word clouds, Q&A boards, reaction walls

### Five Aggregators

| Aggregator | State Shape | Use Case |
|------------|-------------|----------|
| tally | `{ tally: {choice→int}, voters: int }` | Polls, multiple-choice |
| latest_per_participant | `{ values: {ref→value} }` | Sliders, ratings, one value per user |
| append | `{ entries: [{ref,value,ts}], total: int }` | Q&A, brainstorming, idea collection |
| set_union | `{ counts: {value→int} }` | Word clouds, tag clouds |
| keyed_tally | `{ items: [{id,ref,value,ts,votes,voters}] }` | Reaction boards, prioritization |

**Source files:**
- `apps/api/src/slaides/sessions/aggregators.py`
- `apps/web/src/widgets/bridge.ts`
- `docs/WIDGETS_V2.md`
```

---

### 1.4 Placement State Service

**Add new section:**

```markdown
## Placement State Management

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

# Aggregator is sticky per placement - cannot change mid-session
# state_version used for optimistic concurrency (drop stale events)
# closed_at set when presenter closes voting or session ends
# After close, contributions dropped but state preserved for transcript
```

**Source files:**
- `apps/api/src/slaides/sessions/placement_state_service.py`
```

---

## Task 2: SPEC.md UI Flow Updates

### 2.1 Widget Collection Redesign

**Replace Section 3.10 with:**

```markdown
### 3.10 Widget Collection — Persistent Right Sidebar

**Layout:**
- Persistent collapsible right sidebar (not a modal)
- Collapsed state: Floating "WIDGETS" pill (31×115 px, rounded left edge, drop shadow)
- Expanded state: 400-450px wide panel with three tabs

**Header:**
- Mono breadcrumb: "WIDGETS · NN" (slide number from Editor)
- Collapse button (X icon, top-right)

**Tabs:**

1. **My Library** (default)
   - "This deck" section: Widgets belonging to current deck
   - "Other decks" section: Cross-deck picker (collapsible)
   - Each widget: Thumbnail card (sandboxed iframe preview)
   - Draggable cards (drag to insert into slide)
   - Card actions: Adjust, Remove (hover/focus-only icons)

2. **AI Adjust** (when widget selected)
   - Chat interface with user/AI bubbles
   - Selected widget as context (name, kind, tags shown)
   - Streaming AI responses with workflow progress
   - Preview cards for generated drafts
   - Apply button (creates new widget_revision, doesn't overwrite)
   - "New widget" reset button

3. **Code** (when adjusting or editing source)
   - HTML/JS/CSS panes (local drafts)
   - Save button (bottom-right, explicit persist)
   - No autosave

**Generate with AI Flow:**
- Chat composer with optional image attachment (+ button, shown if model supports images)
- Streaming feedback during generation:
  - Animated typing dots + "Waiting for the model to start…"
  - Live character counter (switches to KB past 1KB)
  - Faded mono tail box showing last ~280 chars of streamed source
- Preview card appears on completion with:
  - Compact "DRAFT · KIND" kicker
  - "</> code" link
  - "+ insert" button
- Warnings rendered as amber notice above Apply button (non-blocking)

**Quiet/Loud Picker:**
- Sun-icon popover anchored above composer toolbar
- Explains two modes with ? tooltip
- No longer a manual picker in create mode
- Behavior choice through AI clarification questions (option chips above chat input)

**Source files:**
- `apps/web/src/components/WidgetCollection.vue`
- `apps/web/src/widgets/recent-prompts.ts`
```

---

### 2.2 Widget Adjust Flow

**Replace Section 3.11 with:**

```markdown
### 3.11 Adjusting Widgets

**Entry points:**
1. Click "Adjust" on widget card in My Library tab
2. Click Adjust icon on widget chrome (bottom-right, hover/focus-only)
3. Open AI Adjust tab when widget is selected

**Adjust Mode:**
- Sidebar switches to adjust mode with selected widget as context
- Chat composer pre-filled with widget metadata
- AI streams revision workflow:
  - `question`: Clarification questions with option chips
  - `plan`: Multi-step adjustment plan
  - `step`: Progress through plan steps
  - `reflection`: Self-critique and course correction
  - `draft`: Complete widget revision (all fields)
- Apply button creates new `widget_revision` (doesn't overwrite current)
- Editor bumps `widgetRev` counter to trigger canvas repaint
- Previous revisions preserved, can rollback via API

**Manual Source Editing:**
- Code tab shows HTML/JS/CSS editors
- Changes are local drafts until Save clicked
- Save button (bottom-right) patches widget
- Triggers canvas repaint via widgetRev bump

**Behavior Changes:**
- AI Adjust can swap behavior in either direction (Quiet ↔ Loud)
- Adjust mode PATCH only sends changed fields (name, description, html, js, css, props_schema, tags)
- Never sends `behavior` or `kind` in adjust mode PATCH
- Backend guard refuses behavior write when open placement_state exists

**Source files:**
- `apps/web/src/components/WidgetCollection.vue` (adjust mode logic)
- `apps/api/src/slaides/widgets/router.py` (revision endpoints)
```

---

### 2.3 Audience Typography

**Replace Section 5.3 with:**

```markdown
### 5.3 Audience View

**Typography:**
- Same non-slim typography as presenter view
- h1: 48px (not 28px slim)
- Body: 18px sans-serif (not 14px slim)
- Matches editor canvas rendering

**Navigation:**
- Sticky presenter-style bottom stepper
- Shows only slides already passed by presenter
- ArrowLeft/ArrowRight navigate within passed history
- Cannot jump ahead of presenter

**Live Interactions:**
- Native poll voting (Enter to submit, immediate close with toast)
- Open question answers (Enter to send, Shift+Enter for newline)
- Floating "?" Raise Question button (lower-right, matches presenter FAB position)
- Selected-text AI interpretation toolbar (read-only, guest JWT scoped to session)

**Exit Behavior:**
- Session ended or invalid: Clear guest token
- Signed-in users: Redirect to workspace
- Anonymous users: Redirect to sign-in

**Source files:**
- `apps/web/src/pages/Audience.vue`
- `apps/web/src/stores/session.ts` (audiencePassedSlides logic)
```

---

## Task 3: REQUIREMENTS.md Updates

### 3.1 Widget Ownership

**Replace FR-045 with:**

```markdown
**FR-045: Widget Ownership**
- Widgets belong to exactly one deck (deck-local ownership)
- Cross-deck reuse requires explicit copy operation
- Copy creates independent widget with `derived_from_id` lineage pointer (soft, no cascade)
- Workspace-wide widget list exists only for cross-deck picker
- Delete widget: 409 conflict if placed on any slide (unless force=true)
- Force delete: Strip placeholder from slide markdown, null historical references

**Rationale:** Deck-local ownership simplifies permission model and prevents accidental cross-deck mutations. Explicit copy with lineage preserves attribution while maintaining independence.
```

---

### 3.2 Widget Schema

**Replace FR-040 with:**

```markdown
**FR-040: Widget Schema**

```json
{
  "id": "uuid",
  "deck_id": "uuid",
  "derived_from_id": "uuid | null",
  "name": "string (max 300)",
  "kind": "string (poll | question | quiz | plotter | custom)",
  "description": "string | null",
  "html": "string",
  "js": "string | null",
  "css": "string | null",
  "props_schema": "JSON Schema subset",
  "example_props": "object",
  "behavior": {
    "kind": "quiet | loud",
    "aggregator": "tally | latest_per_participant | append | set_union | keyed_tally (if loud)",
    "contribution_schema": "JSON Schema (if loud)"
  },
  "ai_spec": "object",
  "tags": "array",
  "version": "string",
  "current_revision_id": "uuid | null",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**Revision Schema:**
```json
{
  "id": "uuid",
  "widget_id": "uuid",
  "version_number": "integer",
  "html": "string",
  "js": "string | null",
  "css": "string | null",
  "props_schema": "JSON",
  "example_props": "JSON",
  "behavior": "JSON",
  "ai_spec": "JSON",
  "created_reason": "string | null",
  "created_at": "timestamp"
}
```
```

---

### 3.3 LLM Configuration

**Replace FR-080 with:**

```markdown
**FR-080: LLM Configuration**
- Workspace-level configuration (not per-deck or per-session)
- Supports multiple model IDs in library
- Per-model advanced parameters:
  - max_context_window, max_output_tokens
  - temperature, top_p
  - frequency_penalty, presence_penalty
  - supports_image_input (boolean flag)
- Capability-to-model routing:
  - inline_write: Model for inline writing assistance
  - interpret: Model for selected-text interpretation
  - widget_generate: Model for widget generation
  - None: Disables capability
- API key encrypted at rest (Fernet encryption via LLM_ENCRYPTION_SECRET)
- Rate limiting:
  - Workspace: 60 calls/minute (configurable)
  - Widget generation: 6 calls/minute/user (configurable)
- Calls logged to llm_call table with prompt hash (not raw text)

**Rationale:** Multi-model support allows using different models for different tasks (e.g., cheap model for interpret, expensive model for widget generation). Capability routing provides fine-grained control without UI complexity.
```

---

## Verification Steps

After completing updates:

1. **Cross-reference with code:**
   ```bash
   # Verify widget model columns
   grep -A 30 "class Widget" apps/api/src/slaides/db/models.py
   
   # Verify API routes
   grep -n "router\." apps/api/src/slaides/widgets/router.py | head -20
   
   # Verify migrations exist
   ls apps/api/migrations/versions/001*.py
   ```

2. **Check for contradictions:**
   - Ensure no workspace_id references in widget context
   - Ensure no modal descriptions for widget flows
   - Ensure Slim typography removed from audience specs

3. **Validate against HANDOFF.md:**
   - All features marked "shipped" in HANDOFF.md should be reflected
   - Migration numbers should match
   - Test counts should be current

4. **Peer review:**
   - Backend engineer reviews ARCHITECTURE.md data models
   - Frontend engineer reviews SPEC.md UI flows
   - Product owner reviews REQUIREMENTS.md functional specs

---

## Estimated Effort

| Task | Complexity | Time Estimate |
|------|------------|---------------|
| ARCHITECTURE.md rewrite | High | 4-6 hours |
| SPEC.md rewrite | High | 4-6 hours |
| REQUIREMENTS.md update | Medium | 2-3 hours |
| Verification & review | Medium | 2 hours |
| **Total** | | **12-17 hours** |

---

## Dependencies

- [ ] Complete before: Milestone 5 (Transcripts) documentation
- [ ] Blocks: New engineer onboarding (outdated docs cause confusion)
- [ ] Blocks: Public API documentation (must stabilize internal docs first)

---

## Success Criteria

- [ ] No references to workspace-scoped widgets
- [ ] No modal descriptions for widget flows
- [ ] All migration 0011/0012/0015 features documented
- [ ] Widget revision system fully described
- [ ] Quiet/Loud behavior contract clear
- [ ] Placement state and aggregators documented
- [ ] Zero contradictions between docs
- [ ] New engineers can follow docs without confusion
