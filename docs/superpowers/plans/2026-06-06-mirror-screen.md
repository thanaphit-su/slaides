# Mirror Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only mirror link for live sessions so a presenter can share a clean slide-only view while keeping presenter notes, audience questions, moderation rails, and slide controls private. Access is configured per deck in the editor with three levels: owner only, allowed signed-in users by email, or anyone with the session mirror link.

**Architecture:** Persist deck-level mirror access settings and a per-session mirror token. Add backend mirror snapshot and websocket authorization that returns a sanitized session projection with no `presenter_notes`, no audience questions, and no participant/private streams. Add a `/mirror/:sessionId` frontend route that renders the current live slide without navigation or contribution controls. Presenter gets a copy mirror-link button; editor settings get mirror permission controls.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, Redis-backed websocket hub, Vue 3 Composition API, Pinia, TypeScript, Vitest/Playwright-style component tests where existing patterns allow.

---

## Task 1: Add Persistence For Mirror Access

- [ ] Update [apps/api/src/slaides/db/models.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/db/models.py):
  - Add to `Deck`:
    - `mirror_access_mode = Column(String(24), nullable=False, server_default="owner")`
    - `mirror_allowed_emails = Column(JSON, nullable=False, server_default="[]")`
  - Add to `Session`:
    - `mirror_token = Column(String(64), nullable=True, index=True)`
  - Keep values simple strings: `"owner"`, `"allowed"`, `"link"`.

- [ ] Add migration [apps/api/migrations/versions/0021_mirror_screen_access.py](/Users/thebook/Documents/slaides/apps/api/migrations/versions/0021_mirror_screen_access.py):
  ```python
  """mirror screen access

  Revision ID: 0021_mirror_screen_access
  Revises: 0020_slide_presenter_notes
  """

  from alembic import op
  import sqlalchemy as sa

  revision = "0021_mirror_screen_access"
  down_revision = "0020_slide_presenter_notes"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.add_column("deck", sa.Column("mirror_access_mode", sa.String(length=24), nullable=False, server_default="owner"))
      op.add_column("deck", sa.Column("mirror_allowed_emails", sa.JSON(), nullable=False, server_default="[]"))
      op.add_column("session", sa.Column("mirror_token", sa.String(length=64), nullable=True))
      op.create_index("ix_session_mirror_token", "session", ["mirror_token"], unique=False)


  def downgrade() -> None:
      op.drop_index("ix_session_mirror_token", table_name="session")
      op.drop_column("session", "mirror_token")
      op.drop_column("deck", "mirror_allowed_emails")
      op.drop_column("deck", "mirror_access_mode")
  ```
  If SQLite tests reject JSON `server_default`, switch to `sa.text("'[]'")` and verify with the test database.

- [ ] Update [apps/api/src/slaides/sessions/service.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/sessions/service.py):
  ```python
  def generate_mirror_token() -> str:
      return secrets.token_urlsafe(32)
  ```
  Set `mirror_token=generate_mirror_token()` in `create_session(...)`.

- [ ] Also inspect preview session creation in [apps/api/src/slaides/sessions/router.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/sessions/router.py). Preview sessions should either receive a token harmlessly or explicitly set `mirror_token=None`; prefer harmless token generation through the shared `create_session` path unless a preview-specific row constructor bypasses it.

## Task 2: Add Deck Mirror Settings API

- [ ] Update [apps/api/src/slaides/decks/schemas.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/decks/schemas.py):
  ```python
  from typing import Literal
  from pydantic import field_validator

  MirrorAccessMode = Literal["owner", "allowed", "link"]


  class MirrorAccessSettings(BaseModel):
      mode: MirrorAccessMode = "owner"
      allowed_emails: list[str] = []

      @field_validator("allowed_emails")
      @classmethod
      def _clean_emails(cls, value: list[str]) -> list[str]:
          cleaned: list[str] = []
          seen: set[str] = set()
          for raw in value:
              email = raw.strip().lower()
              if not email:
                  continue
              if "@" not in email:
                  raise ValueError(f"invalid email: {raw}")
              if email not in seen:
                  cleaned.append(email)
                  seen.add(email)
          return cleaned[:100]
  ```
  Add `mirror_access: MirrorAccessSettings` to `DeckOut`.

- [ ] Update `_deck_out(...)` in [apps/api/src/slaides/decks/router.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/decks/router.py) to include:
  ```python
  mirror_access=MirrorAccessSettings(
      mode=deck.mirror_access_mode or "owner",
      allowed_emails=list(deck.mirror_allowed_emails or []),
  )
  ```

- [ ] Add endpoint in `decks/router.py`:
  ```python
  @router.patch("/{deck_id}/mirror-access", response_model=MirrorAccessSettings)
  async def update_mirror_access(...):
      deck = await _load_deck(session, user, deck_id)
      settings = MirrorAccessSettings.model_validate(body.model_dump())
      deck.mirror_access_mode = settings.mode
      deck.mirror_allowed_emails = settings.allowed_emails if settings.mode == "allowed" else []
      await session.flush()
      return settings
  ```
  Use the actual imported schema name from the previous step.

- [ ] Add API tests in [apps/api/tests/test_decks.py](/Users/thebook/Documents/slaides/apps/api/tests/test_decks.py) or [apps/api/tests/test_sessions.py](/Users/thebook/Documents/slaides/apps/api/tests/test_sessions.py), matching existing test organization:
  - Owner can save `"owner"`, `"allowed"` with normalized emails, and `"link"`.
  - Non-owner or wrong workspace cannot update.
  - Invalid email returns validation error.
  - `GET /decks/{deck_id}` includes `mirror_access`.

## Task 3: Add Sanitized Mirror Snapshot And Link API

- [ ] Add mirror output schemas to [apps/api/src/slaides/sessions/schemas.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/sessions/schemas.py):
  ```python
  class MirrorSlideOut(BaseModel):
      id: uuid.UUID
      deck_id: uuid.UUID
      section_id: uuid.UUID | None
      position: int
      kicker: str | None
      markdown: str
      updated_at: datetime
      widgets: list[SlideWidgetEmbed] = []


  class MirrorSessionSnapshot(BaseModel):
      id: uuid.UUID
      deck_id: uuid.UUID
      deck_title: str
      started_at: datetime
      ended_at: datetime | None
      current_slide_id: uuid.UUID | None
      sections: list[SectionOut]
      slides: list[MirrorSlideOut]
      session_slides: list[SessionSlideOut]
      placement_states: list[PlacementStateOut] = []


  class MirrorLinkOut(BaseModel):
      url: str
      token: str | None = None
      access_mode: Literal["owner", "allowed", "link"]
  ```
  Import `SlideWidgetEmbed` from `decks.schemas`.

- [ ] Add helper functions in [apps/api/src/slaides/sessions/router.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/sessions/router.py):
  - `_mirror_token_valid(row, token) -> bool`
  - `_optional_signed_in_user(creds, session) -> AppUser | None`, using `HTTPBearer(auto_error=False)` and `get_supabase_auth().get_user(...)`.
  - `_can_view_mirror(row, deck, user, token) -> bool`.

  Required access behavior:
  - `"owner"`: signed-in approved owner only. Link token alone is not enough.
  - `"allowed"`: signed-in approved owner or signed-in approved user whose `email.lower()` is in `deck.mirror_allowed_emails`. Guest tokens are not accepted even if their email matches.
  - `"link"`: correct `mirror_token` is enough; signed-in owner also works.

- [ ] Add sanitized snapshot builder:
  ```python
  async def _mirror_snapshot(session: AsyncSession, row: SessionRow) -> MirrorSessionSnapshot:
      full = await _snapshot(session, row, viewer="audience")
      slides = [
          MirrorSlideOut(
              id=s.id,
              deck_id=s.deck_id,
              section_id=s.section_id,
              position=s.position,
              kicker=s.kicker,
              markdown=s.markdown,
              updated_at=s.updated_at,
              widgets=s.widgets,
          )
          for s in full.slides
      ]
      return MirrorSessionSnapshot(
          id=full.id,
          deck_id=full.deck_id,
          deck_title=full.deck_title,
          started_at=full.started_at,
          ended_at=full.ended_at,
          current_slide_id=full.current_slide_id,
          sections=full.sections,
          slides=slides,
          session_slides=full.session_slides,
          placement_states=full.placement_states,
      )
  ```
  This intentionally omits `questions`, `audience_count`, `owner_id`, `code`, `interpret_quick_options`, and `presenter_notes`.

- [ ] Add owner-only link endpoint:
  ```python
  @router.get("/{session_id}/mirror-link", response_model=MirrorLinkOut)
  async def get_mirror_link(...):
      row = await _load_owned(session, user, session_id)
      deck = ...
      token = row.mirror_token or session_service.generate_mirror_token()
      row.mirror_token = token
      await session.flush()
      mode = deck.mirror_access_mode or "owner"
      path = f"/mirror/{row.id}"
      query = f"?token={token}" if mode == "link" else ""
      return MirrorLinkOut(url=f"{path}{query}", token=token if mode == "link" else None, access_mode=mode)
  ```
  Keep it a relative URL; the frontend can prefix `window.location.origin`.

- [ ] Add mirror snapshot endpoint:
  ```python
  @router.get("/{session_id}/mirror", response_model=MirrorSessionSnapshot)
  async def get_mirror_snapshot(session_id, token: str | None = None, creds=Depends(_bearer), ...):
      row = ...
      deck = ...
      user = await _optional_signed_in_user(creds, session)
      if not _can_view_mirror(row, deck, user, token):
          raise HTTPException(status_code=403, detail="mirror access denied")
      return await _mirror_snapshot(session, row)
  ```
  Return 410 for ended sessions, matching audience behavior.

- [ ] Add backend tests:
  - Mirror snapshot for a slide with `presenter_notes` does not include `presenter_notes` in any slide object.
  - Mirror snapshot does not include `questions`, `audience_count`, session `code`, or `owner_id`.
  - Owner mode: owner auth succeeds, no auth with token fails.
  - Allowed mode: signed-in approved allowed email succeeds; guest token with same email fails.
  - Link mode: correct token succeeds without auth; wrong/missing token fails.

## Task 4: Add Mirror Websocket Role

- [ ] Update [apps/api/src/slaides/sessions/ws.py](/Users/thebook/Documents/slaides/apps/api/src/slaides/sessions/ws.py):
  - Change `_Connection.role` comment to `'host' | 'participant' | 'mirror'`.
  - Add query params:
    ```python
    token: str = Query(""),
    role: str | None = Query(None),
    mirror_token: str | None = Query(None),
    ```
  - If `role == "mirror"`, load session and deck, call the same mirror access helper created for REST, and assign `role = "mirror"`, `participant_id = None`, `participant_ref = None`.
  - Mirror websocket must not call `hub.heartbeat`, must not publish `participant.joined`, and must not count as audience presence.
  - For non-mirror paths, preserve the existing guest and host behavior.

- [ ] Ensure `_handle_client_event(...)` remains read-only for mirror:
  - It already gates contributions on `conn.role == "participant"` and presenter actions on `conn.role == "host"`.
  - Add an explicit early return after heartbeat:
    ```python
    if conn.role == "mirror":
        return
    ```
    This prevents future event handlers from accidentally accepting mirror input.

- [ ] Ensure private streams stay private:
  - Existing open-answer stream uses `publish_to_role(..., "host", ...)`, so mirror will not receive it.
  - Existing collect widget states use `role_target="host"`, so mirror will not receive private collect entries.
  - General `slide.changed`, `session_slide.inserted`, public poll tallies, and public widget states should reach mirror.

- [ ] Add websocket tests in [apps/api/tests/test_ws.py](/Users/thebook/Documents/slaides/apps/api/tests/test_ws.py) or a small unit test for `_handle_client_event` if websocket client setup is not already present:
  - Mirror role receives `session.state` and `slide.changed`.
  - Mirror role cannot send `question.raise`, `interaction.vote`, or `widget.contribute`.
  - Mirror role does not increment presence count.

## Task 5: Update Frontend Types And API Clients

- [ ] Update [apps/web/src/api/types.ts](/Users/thebook/Documents/slaides/apps/web/src/api/types.ts):
  ```ts
  export type MirrorAccessMode = "owner" | "allowed" | "link";

  export interface MirrorAccessSettings {
    mode: MirrorAccessMode;
    allowed_emails: string[];
  }

  export type MirrorSlide = Omit<Slide, "presenter_notes">;

  export interface MirrorSessionSnapshot {
    id: string;
    deck_id: string;
    deck_title: string;
    started_at: string;
    ended_at: string | null;
    current_slide_id: string | null;
    sections: Section[];
    slides: MirrorSlide[];
    session_slides: SessionSlide[];
    placement_states: PlacementState[];
  }

  export interface MirrorLink {
    url: string;
    token: string | null;
    access_mode: MirrorAccessMode;
  }
  ```
  Add `mirror_access: MirrorAccessSettings` to `Deck`.

- [ ] Update [apps/web/src/api/decks.ts](/Users/thebook/Documents/slaides/apps/web/src/api/decks.ts):
  ```ts
  updateMirrorAccess: (id: string, settings: MirrorAccessSettings) =>
    api<MirrorAccessSettings>(`/decks/${id}/mirror-access`, { method: "PATCH", body: settings }),
  ```

- [ ] Update [apps/web/src/api/sessions.ts](/Users/thebook/Documents/slaides/apps/web/src/api/sessions.ts):
  ```ts
  mirrorLink: (id: string) => api<MirrorLink>(`/sessions/${id}/mirror-link`),
  mirrorSnapshot: (id: string, token?: string | null) =>
    api<MirrorSessionSnapshot>(`/sessions/${id}/mirror${token ? `?token=${encodeURIComponent(token)}` : ""}`),
  ```
  Let `api(...)` attach signed-in auth automatically for owner/allowed modes.

## Task 6: Extend Session Store For Mirror Mode

- [ ] Update [apps/web/src/stores/session.ts](/Users/thebook/Documents/slaides/apps/web/src/stores/session.ts):
  - Expand role type to `"host" | "audience" | "mirror" | null`.
  - Add `loadMirror(sessionId: string, token?: string | null)` using `sessionsApi.mirrorSnapshot`.
  - Store `MirrorSessionSnapshot` in the same `snapshot` ref using a union type. Because mirror snapshots intentionally omit private fields, guard question-specific handlers:
    ```ts
    function hasQuestions(snap: unknown): snap is SessionSnapshot {
      return !!snap && typeof snap === "object" && "questions" in snap;
    }
    ```
    Then in `question.new` / `question.answered`, no-op unless `hasQuestions(snapshot.value)`.
  - Update `wsUrl` to accept an optional role:
    ```ts
    function wsUrl(sessionId: string, token: string, mode?: "host" | "audience" | "mirror"): string {
      const roleQuery = mode === "mirror" ? "&role=mirror" : "";
      return `${wsRoot}/ws/sessions/${sessionId}?token=${encodeURIComponent(token)}${roleQuery}`;
    }
    ```
  - Update `connect(...)` to accept `"mirror"`:
    - Use the mirror query token if present.
    - Otherwise use `useAuthStore().access` for owner/allowed signed-in mirror.
    - Do not heartbeat for mirror.
    - On reconnect, refresh auth for `"host"` and `"mirror"` when using signed-in auth.

- [ ] Keep `presentationOrder`, `currentSlide`, and `placementStates` working for both `SessionSnapshot` and `MirrorSessionSnapshot`; these only need slides/session slides and should not depend on `questions`.

## Task 7: Add Editor Mirror Permission Controls

- [ ] Add a new editor settings surface in [apps/web/src/components/SettingsDrawer.vue](/Users/thebook/Documents/slaides/apps/web/src/components/SettingsDrawer.vue) or, if the existing settings drawer is strictly workspace-level, add a deck-specific section in [apps/web/src/pages/Editor.vue](/Users/thebook/Documents/slaides/apps/web/src/pages/Editor.vue) settings. Prefer `SettingsDrawer` only if it already receives the active deck or can be extended cleanly.

- [ ] UI requirements:
  - Label: `Mirror access`.
  - Segmented/radio options:
    - `Only owner`
    - `Allowed users`
    - `Anyone with link`
  - When `Allowed users` is active, show a textarea or tokenized input for signed-in user emails.
  - Supporting copy should be concise and not expose internal implementation details.
  - Save on explicit button click or alongside settings save; show current status with existing `showToast(...)` in `Editor.vue`.

- [ ] Data flow:
  - Initialize from `editor.deck.mirror_access`.
  - On save call `decksApi.updateMirrorAccess(props.deckId, settings)`.
  - Patch `editor.deck.mirror_access` locally after success so reopening settings is consistent.

- [ ] Theme audit:
  - Use existing tokens: `var(--paper)`, `var(--paper-2)`, `var(--ink)`, `var(--ink-soft)`, `var(--rule)`, `var(--accent)`.
  - Do not hardcode black/white backgrounds for the new controls.

## Task 8: Add Presenter Copy Mirror Link Button

- [ ] Update [apps/web/src/pages/Presenter.vue](/Users/thebook/Documents/slaides/apps/web/src/pages/Presenter.vue):
  - Add refs:
    ```ts
    const mirrorCopied = ref(false);
    const mirrorBusy = ref(false);
    ```
  - Add function:
    ```ts
    async function copyMirrorLink() {
      if (!session.snapshot) return;
      mirrorBusy.value = true;
      try {
        const link = await sessionsApi.mirrorLink(session.snapshot.id);
        const absolute = new URL(link.url, window.location.origin).toString();
        await navigator.clipboard.writeText(absolute);
        mirrorCopied.value = true;
        window.setTimeout(() => (mirrorCopied.value = false), 1500);
      } finally {
        mirrorBusy.value = false;
      }
    }
    ```
  - Add a toolbar button near the join-code copy button:
    ```vue
    <button class="btn btn-sm" :disabled="mirrorBusy" @click="copyMirrorLink" title="Copy mirror link">
      <Icon name="copy" :size="14" />
      {{ mirrorCopied ? "Mirror copied" : "Mirror" }}
    </button>
    ```
  - Hide in preview iframe with the same `!inPreviewIframe` condition used for account menu.

- [ ] If the current icon registry does not have a screen/cast icon, use `copy`; do not hand-draw a new SVG unless the local `Icon.vue` pattern requires it.

## Task 9: Add Mirror Page

- [ ] Add [apps/web/src/pages/Mirror.vue](/Users/thebook/Documents/slaides/apps/web/src/pages/Mirror.vue):
  - Route accepts `sessionId` prop.
  - Reads `token` from `router.currentRoute.value.query.token`.
  - Calls `session.loadMirror(props.sessionId, token)` then `session.connect("mirror", props.sessionId, null, token)` or equivalent based on the store signature from Task 6.
  - Preloads widgets like `Audience.vue`; for public-link mirror, widget fetch may need the mirror token. If `widgetsApi.getAs` is guest-token-only, add a backend/frontend widget read path for mirror or rely on the widget bodies already embedded in snapshot revisions. Verify this while implementing.
  - Renders:
    - Minimal top bar with `Wordmark`, deck title, and connection status.
    - Main slide stage.
    - No `PresenterRail`, no `AnswerModerationRail`, no `RaiseQuestionSheet`, no `OpenInteractionFab`, no bottom stepper, no prev/next key handling.

- [ ] Current slide logic:
  ```ts
  const currentDeckSlide = computed(() => session.snapshot?.slides.find((s) => s.id === session.currentSlideId) || null);
  const currentSessionSlide = computed(() => session.snapshot?.session_slides.find((s) => s.id === session.currentSlideId) || null);
  ```

- [ ] Render live interactions with read-only role:
  ```vue
  <SlideStage v-if="currentDeckSlide" :slide="currentDeckSlide" role="preview" :interpret-enabled="false" />
  <LivePollSlide v-else-if="..." :slide="currentSessionSlide" role="mirror" />
  <LiveQuestionSlide v-else-if="..." :slide="currentSessionSlide" role="mirror" />
  <LiveRandomAudienceSlide v-else-if="..." :slide="currentSessionSlide" role="mirror" />
  ```

- [ ] Add route in [apps/web/src/router.ts](/Users/thebook/Documents/slaides/apps/web/src/router.ts):
  ```ts
  {
    path: "/mirror/:sessionId",
    name: "mirror",
    component: () => import("@/pages/Mirror.vue"),
    props: true,
  }
  ```
  Do not set `requiresAuth`; the backend decides whether auth/token is enough.

- [ ] Unauthorized behavior:
  - If `sessionsApi.mirrorSnapshot` returns 401/403 and the user is not signed in, redirect to signin with `next` equal to the full mirror URL.
  - If signed in but not allowed, show an in-page access denied state.
  - If session ended, show an ended state or redirect to workspace/signin using existing patterns.

## Task 10: Make Live Interaction Components Read-Only For Mirror

- [ ] Update [apps/web/src/components/LivePollSlide.vue](/Users/thebook/Documents/slaides/apps/web/src/components/LivePollSlide.vue), [apps/web/src/components/LiveQuestionSlide.vue](/Users/thebook/Documents/slaides/apps/web/src/components/LiveQuestionSlide.vue), and [apps/web/src/components/LiveRandomAudienceSlide.vue](/Users/thebook/Documents/slaides/apps/web/src/components/LiveRandomAudienceSlide.vue):
  - Expand prop type from `"presenter" | "audience"` to `"presenter" | "audience" | "mirror"`.
  - Treat `role === "mirror"` like presenter for display, but never show submit/answer controls.
  - Poll mirror should show aggregate results if public results are present.
  - Open-question mirror should show prompt and promoted/public results only; it must not show moderation controls or answer input.
  - Random-audience mirror should show the same selected result the presenter sees if the result is already public in `session_slide.results`, but not any controls.

- [ ] Update [apps/web/src/components/SlideStage.vue](/Users/thebook/Documents/slaides/apps/web/src/components/SlideStage.vue) and [apps/web/src/widgets/WidgetFrame.vue](/Users/thebook/Documents/slaides/apps/web/src/widgets/WidgetFrame.vue) only if needed:
  - Prefer passing `role="preview"` for deck-slide widgets in mirror so iframes do not enable audience contribution controls.
  - If widgets need a distinct mirror role, add `"mirror"` to both prop unions and make it read-only.

## Task 11: Add Focused Frontend Tests

- [ ] Add or update tests under [apps/web/src](/Users/thebook/Documents/slaides/apps/web/src):
  - API type/client tests if this repo has existing API client test patterns.
  - `Mirror.vue` renders current deck slide without notes, question rail, raise-question button, or stepper.
  - Presenter copy mirror link calls `sessionsApi.mirrorLink` and writes absolute URL to clipboard.
  - Editor settings saves each mirror access mode and normalizes allowed emails display after save.
  - Live interaction components with `role="mirror"` do not emit contribution/submit events.

- [ ] Add visual/theme check for the new editor setting controls:
  - Dark mode and light mode should both use tokens.
  - No hardcoded light panels inside the mirror access controls.

## Task 12: Verification

- [ ] Backend:
  ```bash
  cd apps/api
  pytest tests/test_decks.py tests/test_sessions.py tests/test_ws.py -q
  ```

- [ ] Frontend unit/component tests:
  ```bash
  cd apps/web
  npm test -- --run
  ```

- [ ] Frontend typecheck/build:
  ```bash
  cd apps/web
  npm run build
  ```

- [ ] Migration smoke test:
  ```bash
  cd apps/api
  alembic upgrade head
  ```

- [ ] Manual browser smoke test:
  - Start API and web dev servers using the repo’s existing commands.
  - Create/open a deck, set mirror access to `Anyone with link`, start a session, copy mirror link.
  - Open mirror URL in a signed-out/private context.
  - Advance presenter slides and verify mirror follows.
  - Verify mirror has no notes, questions, audience-count rail, answer moderation, raise-question affordance, or prev/next controls.
  - Switch deck access to `Only owner`; verify public mirror link is denied and owner signed-in mirror works.
  - Switch to `Allowed users`; verify allowed signed-in email works and a guest token/email does not.

## Risk Notes

- Privacy must be enforced by backend response schemas and websocket role filtering. Frontend-only hiding is not sufficient.
- Reusing `SessionSnapshot` for mirror is risky because it contains `presenter_notes` and questions. Use `MirrorSessionSnapshot`.
- Widget fetching may need a mirror-safe public path. Do not reuse guest auth semantics for allowed-email mirror, because guests with matching email are explicitly disallowed.
- Existing live widgets with `collect` aggregators already target host-only websocket streams. Keep that behavior unchanged so mirror cannot see private audience submissions.
