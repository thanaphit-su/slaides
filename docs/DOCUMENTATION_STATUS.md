# SLAIDES Documentation Status

**Updated:** 2026-05-29 (M5 transcript shipped + Loud-widget state persistence)

This file records the documentation state after the 2026-05-29 docs refresh and a code-level audit against `apps/web` and `apps/api`.

## Quick Summary

| File | Status | Notes |
|---|---|---|
| `README.md` | CURRENT | Now describes both implemented app/API and prototype reference. |
| `ARCHITECTURE.md` | CURRENT | Data model, widget revisions, AI threads, placement state, and analytics / transcript routes match code. Background worker for transcript summarisation / large exports remains a deployment / future-work concept. |
| `SPEC.md` | CURRENT | Auth, widget sidebar, AI Adjust, settings, widget collection text, and session transcript / replay flows match current implementation. Display-preference persistence remains future. |
| `REQUIREMENTS.md` | CURRENT WITH EXPLICIT BACKLOG ITEMS | Shipped items use check marks; FR-074 / FR-075 / FR-076 (transcript view + export) are shipped. Display persistence and i18n catalog remain backlog. |
| `HANDOFF.md` | CURRENT | Most detailed implementation history; latest verified counts are 176 backend / 236 frontend. |
| `SLIDE_CANVAS_UX_TEST_CASES.md` | NEEDS REVIEW | Still useful as a manual UX checklist, but should be rechecked against preview mode and widget-revision flows. |
| `WIDGETS_V2.md` | CURRENT | Reference design brief plus shipped decision log. |
| `architecture/widget-revisions-ai-workflow.md` | CURRENT | Authoritative contract for migration 0015 workflow. |
| `CONCEPT.md` | CURRENT | High-level product vision. |
| `DESIGN.md` | CURRENT | Design tokens and visual direction. |

## Current Known Caveats

- Display preferences are not persisted yet. The settings UI explicitly labels dark mode and editor density persistence as later-release work.
- The current frontend uses a custom markdown renderer/contenteditable editor, not `remark` or Monaco.
- The API has no Celery worker dependency today. Background transcript summarisation / large-export workers (beyond the current inline 10k-event cap) remain a deployment / future-work concept, not current code.
- The transcript page's slide pane renders Loud widgets on deck slides with their persisted final aggregated state (poll tally, set-union, etc.) via the snapshot's `placement_states[]`. Quiet widgets with no persistable state boot identically to live; session-slides (FAB-inserted polls / open questions / random-audience picks) render via the existing `Live*Slide` components in `role="presenter"` against `session_slide.results`.

## Recent Changes (2026-05-29)

### Loud-Widget State Persistence on Slide Remount

**Feature:** Loud widgets keep their aggregated state when the host navigates away from a slide and back (live), and render their final persisted state in the session transcript page.

**Mechanism:**
- `useSessionStore().placementStates` is already the in-memory cache of aggregated state, populated by `loadHost` from snapshot + live `widget.state` WS events.
- New `hydratePlacementStates(list: PlacementState[])` helper on the store accepts an explicit list, so non-live callers (the transcript page) can populate the cache without going through `loadHost` (which would open a WebSocket).
- `WidgetFrame` now has an `@load` handler on the iframe that looks up the current placement state from the store and posts a `state` message into the new iframe using the same envelope live broadcasts already use.
- Editor / preview / thumbnail contexts (no active Pinia) stay no-op via a `try/catch` around `useSessionStore()`.

**Files modified:**
- `apps/web/src/stores/session.ts` (extract + export `hydratePlacementStates`)
- `apps/web/src/widgets/WidgetFrame.vue` (~20 lines for `onIframeLoad` + `@load` binding)
- `apps/web/src/pages/SessionTranscript.vue` (3 lines to hydrate on `fetchSnapshot`)

**Testing:**
- TypeScript check: passed
- Frontend tests: 236 passed
- Backend tests: 176 passed

### Milestone 5 — Session History & Transcript (2026-05-28)

**Feature:** Per-session transcript replays the live presenter view with the persisted final state of every interaction. Workspace sessions tab lists past sessions with deck title, duration, participant count, and interaction count. Sessions can be permanently deleted; partial "Clear Slide & LLM" deletes the privacy-sensitive subset of events.

**Backend:**
- New `apps/api/src/slaides/analytics/` package (router / service / events / crypto / export).
- Migration `0016_session_events.py` — `session_event` table and `workspace.log_llm_prompts_for_transcript` boolean.
- Endpoints under `/api/v1/sessions/{id}`: `GET /transcript`, `GET /replay`, `GET /transcript.csv`, `GET /transcript.json`, `DELETE /transcript`, `DELETE /` (refuses live; NULL-s `llm_call.session_id` before delete).
- `SessionListItem` extended with `deck_title` (join) + `participant_count` + `interaction_count` (correlated subqueries).

**Frontend:**
- `apps/web/src/pages/SessionTranscript.vue` — full-bleed Presenter chrome (app bar · slide pane · stepper) + 380px sidebar (Timeline / Per-Slide / Participants). Section kicker mirrors `Presenter.vue`'s `currentKicker` verbatim. Live components (`LivePollSlide` / `LiveQuestionSlide` / `LiveRandomAudienceSlide`) render session-slides in `role="presenter"` against persisted `session_slide.results`.
- `apps/web/src/pages/Workspace.vue` — sessions list shows deck title + stats chips; zero-duration sessions hidden by default behind a toggle; `?tab=decks|sessions` URL parameter; 28×28 trash button per session card.
- `apps/web/src/components/SettingsDrawer.vue` — "Log LLM prompts for transcript" toggle in the LLM tab.

**Testing:**
- Frontend: 236 passed (auto-scroll snapshot count, then +46 for streaming preview, then unchanged for transcript work).
- Backend: 176 passed (+10 in `test_analytics.py`).

### Auto-Scroll for Widget Chat Panel (2026-05-28)

**Feature:** Smart auto-scrolling during AI widget generation that respects user's reading position.

**Behavior:**
- Auto-scrolls during streaming only when user is near bottom (150px threshold)
- User can scroll up to read history without being hijacked
- Generation completion respects user's scroll position (no forced scroll)
- Template-based scroll binding ensures listener works correctly with tab switching
- Unmount guard prevents post-unmount scroll work
- **Post-render scroll:** Waits for preview card to render before scrolling (avoids scroll-before-content)
- **Apply confirmation:** Scrolls to show "Applied to the widget" message after user clicks Insert/Apply

**Implementation:**
- `isUserNearBottom` ref with synchronous scroll tracking
- `queueAutoScrollToBottom()` helper with rAF coalescing and re-check
- `@scroll.passive` binding on `.widget-chat-thread` element
- `isUnmounted` flag guards streaming rAF and finally block
- Streaming preview captures `shouldFollow` state before DOM update, scrolls after `nextTick()`
- `persistDraft()` calls `scrollThreadToBottom()` after apply messages

**Files modified:**
- `apps/web/src/components/WidgetCollection.vue` (~60 lines added/modified)

**Testing:**
- TypeScript check: passed
- Frontend tests: 236 passed

## Verification

Commands run during the audit:

```sh
cd apps/api && uv run pytest -q
cd apps/web && npm test -- --run
```

Results:

- Backend: 176 passed.
- Frontend: 236 passed.
