# SLAIDES — Functional Specification

This document describes the implemented v0.1 product surfaces. The archived prototype in `.draft/prototype` remains a visual reference, but current behavior lives in `apps/web` and `apps/api`.

---

## 1. Sign-in / guest-join

### 1.1 Two-mode toggle
Top of the right panel: segmented control with two tabs — **Sign in** (instructor) and **Join a session** (audience). The instructor tab has its own Sign in / Sign up subswitch.

### 1.2 Instructor sign-in
- Fields: `email` (required), `password` (required).
- Submit → Supabase Auth sign-in via the backend; on success, redirect to `/workspace`.
- **Sign up** mode adds display name and password confirmation. Sign-up creates a pending local `app_user` profile; pending instructors can sign in but approved-only routes stay locked until an admin approves them.

### 1.3 Guest join — step A: code entry
- Single field: `session_code` in format `SLD-XXXX-XX` (auto-uppercase, monospace).
- Accepts both raw code and full join URL (parse on submit).
- On valid code → step B. On invalid → inline error under the field.

### 1.4 Guest join — step B: identity
- Fields: `email` (required), `display_name` (required UNLESS `anonymous = true`).
- Toggle: `anonymous`. When on, display name input is disabled and labelled "Hidden — joining anonymously".
- Submit → backend creates a `participant` row, returns a session-scoped token, navigates to `/audience/:session_id`.

### 1.5 Left panel (editorial side)
- SLAIDES wordmark top.
- Hero copy. Three lines, last word italicized for accent.
- Version + type credit at the bottom (`v 0.1 · prototype`).
- Pure presentation. No links.

---

## 2. Workspace (instructor home)

The page an instructor lands on after sign-in.

### 2.1 Top nav (sticky)
- Wordmark · tabs (`Decks` | `Sessions`). Widgets are deck-local and managed from the editor sidebar.
- Right side: search input (⌘K to focus), settings gear, avatar (click = sign-out menu).

### 2.2 Hero strip
- `Library · {user.name}` kicker.
- `The decks you've been writing.` H1.
- Short lede.

### 2.3 Action row
- Primary buttons: `+ New deck`, `Import…` (accepts `.slaides` zip). Widget collection is available inside the editor for each deck.
- Right side: deck count, grid / list view toggle.

### 2.4 Deck grid (default view)
- Responsive: `repeat(auto-fill, minmax(280px, 1fr))`.
- Each card: editorial cover thumbnail (16:10) + title + subtitle + meta row (slides, audience total, sessions count).
- Hover: border darkens, lifts to elevation 2.
- Click: → `/editor/:deck_id`.
- One trailing card: dashed "+ New deck" placeholder.

### 2.5 Deck list view
- Same data in a denser table form.

### 2.6 Empty state (no decks)
- Replace grid with a centered call-to-action: "Write your first deck." button + "or drop a .slaides file".

---

## 3. Editor (instructor)

The largest surface. Three regions: top bar, left sidebar (collapsible), center canvas, plus a right edge tab for widgets and a bottom stepper.

### 3.1 Top bar (56px, sticky)
- Back arrow → `/workspace`.
- Wordmark · deck title · `draft` chip.
- Right cluster: `Preview` · `Export` · `Settings` · **`Start session`** (the primary CTA, ink-blue dot indicates "this goes live").

### 3.2 Left sidebar
Collapsible (260px expanded, 44px collapsed). VS Code-like.

**Tabs (two):**
- **Sections** — Tree of sections (collapsible) → slides. Each slide row shows its H1 truncated to two lines + a widget icon if widgets present. Active slide gets a 2px left border. Bottom: `+ New slide`.
- **Theme** — A list of theme presets (Editorial Press is default in v0.1, others as preview-only stubs) + layout toggles (Wide margins, Drop caps, Section marks).

**Footer:** version chip + dark-mode toggle.

### 3.3 Center canvas
- White paper, max-width 920px, padded 56/64.
- Kicker (small uppercase) above the H1.
- The canvas is `contentEditable`. The instructor types directly into it; selections raise a floating WYSIWYG toolbar (3.6.1).
- Markdown renders as editorial type: 80px serif H1 (italics for emphasized words), 18px serif body, generous line-height (1.7).
- Widget placeholders (`{{widget:id}}`) render the live widget — non-editable — with a hover-revealed chrome strip showing `WIDGET · {kind} · #{id}` and an `Adjust` button (3.11).
- **Top edge**: an "+ Add slide above" pill becomes visible only while the cursor is within the top ~90px of the scroll area. Click inserts.
- **Bottom**: a dashed "Add a widget" zone appears below the content **only when the slide has no widget yet** (1-widget-per-slide rule). It dims when the cursor is far; brightens to an accent fill when the cursor enters its ~110px zone, revealing two CTAs: `From collection` and `Generate with AI`.
- Below that: slide-id meta + "no widget · 1 max per slide" or "widget · {kind}".

### 3.3.1 One widget per slide (hard rule)
A slide may have at most one widget. The UI enforces this in three places:
1. The bottom hover-zone Add Widget CTA is hidden when a widget is already present.
2. The right edge tab toggles label and behavior: `Widgets` (opens the collection) when empty → `Adjust widget` (opens the Adjust panel) when present.
3. The right-click context menu swaps `Generate widget…` and `Insert from collection…` for `Adjust widget…` when the slide already has one, and shows a `1 widget per slide · max reached` hint.

### 3.4 Right sidebar — Widgets (persistent, collapsible)
- **Collapsed state:** Floating "WIDGETS" pill (31×115 px, rounded left edge, `border-radius: 8px 0 0 8px`, drop shadow biased left)
- **Expanded state:** 400-450px wide panel with mode-specific chat, props, code, and library controls
- **Header:** Mono breadcrumb "WIDGETS · NN" (slide number) + collapse button (X icon)
- **Behavior:** Clicking active icon collapses; clicking inactive expands
- VSCode-style icon rail on left (sections / widgets / theme), flex-fill content panel on right
- **Create mode:** Generate-with-AI chat is the main panel; the deck-local library opens from the toolbar as a popover, with a "Copy from another deck" section for explicit cross-deck copies.
- **Adjust mode:** Generate/AI Adjust chat remains the main panel for the selected placement; widgets with props also expose a Props tab, and every selected widget exposes a Code tab with HTML/JS/CSS editors and explicit Save.
- **Drag-to-insert:** Deck-local widget cards and copied cross-deck candidates can be inserted into the active slide through the caller-supplied pick/drop path.

### 3.5 Bottom stepper (48px, sticky)
- `Prev` ◀ — pip rail (24px per slide, active is solid ink) — slide counter `N / total` — `Next` ▶.
- Pip click = jump to slide.

### 3.6.1 Floating WYSIWYG toolbar
When the user makes a non-collapsed text selection inside the canvas, a small dark pill appears centered above the selection rect (`position: fixed`, 8px above `range.getBoundingClientRect().top`, clamped to viewport).

**Buttons (left → right):**
- **B** — bold
- **I** — italic
- **U** — underline
- ─
- **H1** — promote block to h1
- **H2** — promote block to h2
- **¶** — promote block to paragraph
- **" "** — promote block to blockquote
- ─
- Inline code (mono pill)
- Link (prompts for URL)
- ─
- ✦ **Interpret with AI** (accent color) — opens the Interpret popover with the selection (3.7)

The toolbar uses `mousedown.preventDefault()` to avoid blurring the selection.

### 3.6 Context menu (right-click)
A single context menu surfaces on right-click anywhere in the canvas.

**Items (top to bottom):**
1. (If text selected) Selection preview line — first 32 chars in quotes.
2. `Copy` ⌘C
3. (If text selected) **`Interpret with AI`** — opens Interpret popover (3.7)
4. `Cut` ⌘X
5. `Paste` ⌘V
6. ─
7. **`Generate widget…`** — opens Inline Chat modal (3.8)
8. `Insert from collection…` — opens widget drawer
9. ─
10. `Edit as Markdown` — switches the active slide to raw-markdown view

### 3.7 Interpret popover
- Anchored near the cursor.
- Shows: kicker, the selected text in a mono box, a prompt field pre-filled "in plain English".
- While the LLM is thinking: shimmer placeholder lines.
- When done: serif response, plus `Copy` and `Insert below` actions.

### 3.8 Generate with AI — Sidebar chat (not modal)
- **Location:** Widget sidebar. In create mode this is the default panel; in adjust mode it becomes the AI Adjust chat for the selected widget.
- Chat composer with:
  - Textarea for prompt (⏎ to send, Shift+⏎ for newline)
  - Optional image attachment (+ button, shown if model supports images)
  - Workflow mode menu: "Build now" or "Clarify first"
  - Quiet/Loud behavior is chosen by AI workflow clarification questions rendered as option chips when needed; create mode does not expose a manual behavior picker.
- **Streaming during generation:**
  - Animated typing dots + "Waiting for the model to start…"
  - Live character counter (switches to KB past 1KB)
  - Faded mono tail showing last ~280 chars
  - **Auto-scroll:** Chat panel auto-scrolls during streaming when user is near bottom (~150px threshold). User can scroll up to read history without being hijacked. Generation completion respects user's scroll position.
- **Preview card on completion:**
  - Compact "DRAFT · KIND" kicker
  - "</> code" link
  - "+ insert" button (or "Regenerate" to retry)
- Warnings rendered as amber notice (non-blocking)

### 3.9 Settings drawer (3.10 below)

### 3.10 Widget collection — Redesigned sidebar

**My Library tab:**
- "This deck" section: Widgets belonging to current deck
- "Other decks" section: Cross-deck picker (collapsible)
- Each widget: Thumbnail card (sandboxed iframe preview with host theme tokens)
- Draggable cards (`draggable="true"`, dataTransfer carries `{widget_id, deck_id}`)
- Card actions: Adjust, Remove (hover/focus-only icon-only buttons, bottom-right)
- "OTHER DECK" pill badge on cross-deck widgets

**Generate with AI tab:**
- Chat composer with optional image attachment (+ button, shown if model supports images)
- **Streaming feedback during generation:**
  - Animated typing dots + "Waiting for the model to start…"
  - Live character counter (switches to KB past 1KB)
  - Faded mono tail box showing last ~280 chars of streamed source
- **Preview card on completion:**
  - Compact "DRAFT · KIND" kicker
  - "</> code" link
  - "+ insert" button
- Warnings rendered as amber notice above Apply button (non-blocking)

**Quiet/Loud picker:**
- Sun-icon popover anchored above composer toolbar
- Explains two modes with ? tooltip
- Behavior choice through AI clarification questions (option chips above chat input)
- No manual picker in create mode

**Recent prompts:**
- Empty state shows up to 5 recent prompts (from localStorage, deduped, capped)
- Click a row to prefill composer

### 3.11 Widget Adjust — Sidebar mode

**Entry points:**
1. Click "Adjust" on widget card in My Library tab
2. Click Adjust icon on widget chrome (bottom-right, hover/focus-only)
3. Open AI Adjust tab when widget is selected

**Adjust Mode:**
- Sidebar switches to adjust mode with selected widget as context
- Chat composer with widget metadata (name, kind, tags) shown
- **AI streams revision workflow:**
  - `question`: Clarification questions with option chips
  - `plan`: Multi-step adjustment plan
  - `step`: Progress through plan steps
  - `reflection`: Self-critique and course correction
  - `draft`: Complete widget revision (all fields)
- **Apply button creates new `widget_revision`** (doesn't overwrite current)
- Editor bumps `widgetRev` counter to trigger canvas repaint
- Previous revisions preserved; can rollback via API

**Behavior Changes:**
- AI Adjust can swap widget behavior in either direction (Quiet ↔ Loud)
- Adjust mode PATCH sends only draft fields that changed, including `kind` or `behavior` when the AI intentionally changes them
- Backend guard returns `409 edit_requires_reset` when an edit affects open `placement_state`; confirming resets the current audience aggregate and applies the edit

**Manual Source Editing:**
- Code tab shows HTML/JS/CSS editors
- Changes are local drafts until Save clicked
- Save button (bottom-right) patches widget, triggers canvas repaint

**Props Tab:**
- Form rendered from widget's `props_schema` (JSON Schema subset)
- Placement-specific customization (same widget, different props per slide)
- Supports primitives, arrays (with reorder), nested objects, `enum.from` dynamic selects
- PATCH updates placement props; validates against schema (422 on violation)

---

## 4. Presenter (live)

The instructor's view during a running session.

### 4.1 Top bar (52px)
- Exit (×) · wordmark · deck title · **LIVE** badge · "Started 12 min ago".
- Right cluster:
  - **Audience pill** — user icon + count.
  - **Pending questions** — `?` icon + count, with red dot when unread.
  - **Share code** — copy share code with one click; tooltip confirms "Link copied · slaides.app/j/..."
  - Dark-mode toggle.
  - Settings gear.

### 4.2 Slide stage
- Same renderer as editor, but 1100px max-width and bigger padding.
- Right-click on selected text → Interpret popover (same as editor; the audience can also do this on their phone).

### 4.3 Bottom bar (56px)
- Left: Dark-mode toggle (duplicated for reach).
- Right: prev / pips / counter / next. Interaction slides are pipped in `--accent` (vs `--ink` for deck slides) so the rhythm of the session is visible at a glance.

### 4.3.1 Open interaction FAB (bottom-right of slide stage)
- Circular 56px accent FAB. Expands to a labeled pill on hover. Rotates the icon to a `+` when the menu is open.
- Menu items: `Open poll as new slide`, `Open question as new slide`, `From widget library…`.
- **Interaction slides are session-only.** Choosing an interaction:
  1. **Creates a brand-new slide immediately after the current one** (the original deck is not edited).
  2. The new slide uses the **current presentation theme**. Live polls and open questions should feel like part of the same session surface rather than forcing an inverted/dark treatment.
  3. The presenter is auto-navigated to the new slide.
  4. The slide is appended to `session.history` with `{slide_id, kind, parent_slide_id, opened_at}`. After the session, transcripts show the original deck *plus* every interaction slide that was opened.
  5. Audience sees the new slide through the same realtime slide-advance event used for deck slides — no separate "modal" channel.

### 4.4 Right rail: live questions (toggle from top bar)
- Sticky 360px column.
- For each question:
  - Avatar (initial) OR `anon` badge.
  - Display name OR "Anonymous".
  - Question body (serif).
  - Time-ago, e.g. "2 min".
  - Actions: `Mark answered`, `Jump to slide`.
- Empty state: "No questions yet. The room is reading."

### 4.5 Keyboard
- `←` `→` — prev / next slide.
- `Esc` — close any open menu / popover.

### 4.6 Dark mode
- Toggle inverts paper/ink tokens. Headlines stay legible (serif, soft warm white on near-black).

---

## 5. Audience (mobile-leaning)

The view a guest or registered audience member sees on their phone.

### 5.1 Frame
- 380×760 phone-shaped frame on a dark backdrop in the prototype; in production this is the full viewport, scaled to phone proportions.
- Status bar (mock in prototype): time, signal, battery.

### 5.2 Top app bar
- Exit (×) · centered: deck title + LIVE indicator + "10 in room".

### 5.3 Slide content
- **Same non-slim typography as presenter view** (h1: 48px, body: 18px sans-serif)
- **No section sidebar.** Audience only ever sees one slide at a time, the one the presenter is on.
- Widgets render full-width.
- Live interactions inserted by the presenter appear inline with a slide-up animation.

### 5.4 Bottom action bar (62px)
- ◀ Prev (peek the previous slide, doesn't affect the presenter)
- **`Raise a question`** — full-width primary CTA.
- Next ▶

### 5.5 Raise question modal
- Slides up from the bottom (sheet).
- Fields: textarea + Anonymous toggle (defaults to user's anon state).
- Submit → confirmation screen (`Question sent.` with a check icon) → `Done` returns to slide.

### 5.6 Right-click / long-press
- On selected slide text, opens a small Interpret action (mobile-adapted version of 3.7).

---

## 6. Settings drawer

Right drawer, 420px. Four tabs:

### 6.1 Session
- **Publish & start a session** — primary CTA that begins a new session.
- **Recordings & transcripts** — explanatory block only in current v0.1 UI. Transcript toggles are M5; interaction logs are already captured for live sessions.
- **Deck access** — read-only sharable link, `Copy link` and `Export .slaides` buttons.

### 6.2 LLM — Multi-model configuration

**Workspace-level settings:**
- Base URL (default `https://api.openai.com/v1`)
- API key (masked, encrypted at rest via Fernet)
- **Model library:** Array of configured models with advanced parameters:
  - `max_context_window`, `max_output_tokens`
  - `temperature`, `top_p`
  - `frequency_penalty`, `presence_penalty`
  - `supports_image_input` (boolean flag)
- **Capability-to-model routing:**
  - `inline_write`: Model for inline writing assistance
  - `interpret`: Model for selected-text interpretation
  - `widget_generate`: Model for widget generation
  - `None`: Disables capability
- `Test connection` button (streams test prompt, shows latency + token usage)
- Rate limit display (60 workspace calls/min, 6 widget-generation calls/min/user)

**Notes:**
- No provider-name field (OpenAI-compatible only)
- No internet-search setting
- API key never echoed back to browser
- Calls logged with prompt hash (not raw text) for cost tracking

### 6.3 Display
- Current UI shows this as later-release work. Dark mode and editor density persistence are not implemented yet.

### 6.4 Account
- Avatar + name + email.
- `Sign out` (destructive style — red border/text).

---

## 7. Widget collection (sidebar, not workspace tab)

**Location:** Persistent right sidebar in editor (collapsible)

**Note:** Workspace-level "Widgets" tab was removed in Widgets v2. Widgets are deck-local; cross-deck reuse goes through explicit copy.

### 7.1 Panels and popovers
- Create mode: Generate-with-AI chat with optional image attachment and workflow mode menu.
- Library popover: deck-local widgets plus "Copy from another deck"; same-deck duplicate and delete actions are icon buttons per row.
- Adjust mode: AI Adjust chat for the selected widget.
- Props tab: shown when the selected widget has `props_schema` fields.
- Code tab: HTML/JS/CSS editors with explicit Save.

### 7.2 Library rows and previews
- Deck-local library rows show name, description/kind, duplicate, and delete actions.
- Cross-deck reuse goes through the copy picker; copying creates an independent widget in the current deck before insertion.
- Widget thumbnails/previews use sandboxed iframes with host theme tokens where rendered.

### 7.3 Widget Behavior Contract (Widgets v2)

**Quiet widgets (default):**
```json
{ "kind": "quiet" }
```
- Run locally in iframe
- No audience aggregation
- Use `window.slaides.setState/getState()` for persistence

**Loud widgets:**
```json
{
  "kind": "loud",
  "aggregator": "tally" | "latest_per_participant" | "append" | "set_union" | "keyed_tally",
  "contribution_schema": { /* JSON Schema */ }
}
```
- Aggregate contributions across audience
- Must call `window.slaides.contribute(value)` to send
- Must subscribe via `window.slaides.on('state', cb)` for updates
- State persisted to `placement_state` per (session_id, placement_id)

**Five Aggregators:**
| Aggregator | State Shape | Example |
|------------|-------------|---------|
| `tally` | `{ tally: {choice→int}, voters: int }` | Polls, quizzes |
| `latest_per_participant` | `{ values: {ref→value} }` | Sliders, ratings |
| `append` | `{ entries: [{ref,value,ts}], total: int }` | Q&A, ideas |
| `set_union` | `{ counts: {value→int} }` | Word clouds |
| `keyed_tally` | `{ items: [{id,ref,value,ts,votes,voters}] }` | Reaction boards |
- Hover darkens border.
- Click → insert into the active slide (caller-supplied callback).

### 7.4 Generate flow
- Textarea, optional image attachment, workflow mode menu, and recent prompt shortcuts.
- `Build now` drafts when the model has enough information; `Clarify first` asks one useful question before drafting.
- Drafting state shows typing dots, live character count, and a stream-tail preview.
- Ready state shows a preview card with insert/save actions and non-blocking validator warnings.

---

## 8. Markdown spec (the source of truth)

A deck file is a single `deck.json` manifest + N markdown files in `slides/`. The markdown subset supported in v0.1:

| Syntax | Meaning |
|---|---|
| `# Heading` | Slide title (H1) — exactly **one per slide** |
| `## Subhead` | In-slide subhead |
| `*italic*` | Emphasized run (display headlines often use this for the standout word) |
| `**bold**` | Strong emphasis |
| `` `code` `` | Inline monospace |
| `> quote` | Blockquote |
| `---` | Horizontal rule |
| `[label](url)` | Inline link |
| `{{widget:ID}}` | Widget placeholder. Renders the widget placement with that id |

Unordered lists, ordered lists, markdown tables, and safe links are implemented. Images, footnotes, and fenced code blocks remain out of scope for v0.1.

---

## 9. Widget contract (the iframe protocol)

Every widget is an isolated HTML document loaded into an iframe with `sandbox="allow-scripts allow-forms"` and `srcdoc=<the widget HTML>`. The widget cannot reach the deck DOM or parent storage because it has a sandbox-null origin. The host injects a tiny bridge before the widget script runs:

```js
window.slaides = {
  emit(event, payload),       // → host, e.g. emit('vote', {choice: 'B'})
  on(event, cb),              // ← host, e.g. on('presenter:advance', cb)
  setState(key, value),       // persist widget state (per participant for audience-mode)
  getState(key),              // read it back
  contribute(value),          // Loud widgets → host/server aggregation
  props,                      // placement-specific props, baked into srcdoc before widget JS
  behavior,                   // {kind:'quiet'} or {kind:'loud', aggregator, contribution_schema}
  role,                       // 'instructor' | 'audience' | 'preview'
  participant: { id, anon },  // never raw email
  api: {
    llm(prompt) → Promise<string>,    // calls the workspace's configured LLM proxy
  }
}
```

Allowed widget output: self-contained HTML/CSS/JS inside the sandbox. Current AI-generated/starter widgets are vanilla DOM; remote scripts and stylesheets are rejected by the widget-generation contract and blocked by the srcdoc CSP. Images may load from `data:` or `https:` URLs.

---

## 10. Realtime events (WebSocket)

One channel per session: `/ws/sessions/:id?token=...`. JSON messages use a discriminating `type`.

**Server → clients:**
- `session.state` (initial snapshot)
- `slide.changed { slide_id, is_session_slide }`
- `session_slide.inserted { id, kind, spec, results, ... }`
- `session.ended {}`
- `interaction.tally { session_slide_id, results, spec_state? }`
- `interaction_spec.updated { session_slide_id, spec }`
- `interaction_results.updated { session_slide_id, results }`
- `question_answer.new { session_slide_id, answer }`
- `widget.state { placement_id, widget_id?, state, state_version, contribution_count }`
- `widget.reset { placement_id, widget_id?, state, state_version, contribution_count }`
- `question.new { id, text, ... }`
- `question.answered { question_id }`
- `participant.joined` / `participant.left`

**Client → server:**
- `participant.joined`
- `participant.left`
- `interaction.vote { session_slide_id, choice }`
- `interaction.text { session_slide_id, text }`
- `interaction.slider { session_slide_id, value }`
- `widget.contribute { placement_id, value }`
- `interaction.interpret { selection, prompt }`
- `question.raise { text, anonymous }`
- `question.answered { question_id }`
- `widget.update { ... }` (legacy relay path)

Audience contribution events are appended to `interaction_log`. Server broadcasts also update `session_slide.results` or `placement_state` so late joiners receive the current state in `session.state`.

---

## 11. Out of scope for v0.1

- Team collaboration / multi-instructor edits
- Slide transitions / animations beyond fade-in
- Live cursors / co-presence in the editor
- Mobile-native apps
- Paid plans, billing
- A widget marketplace (the per-workspace library is enough)
- Image / video uploads (markdown is text-only in v0.1)
- Localization (English-only in v0.1; "interpret to language" via LLM works as an escape hatch)
