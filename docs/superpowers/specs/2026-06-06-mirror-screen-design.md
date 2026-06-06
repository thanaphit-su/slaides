# Mirror Screen Design

Date: 2026-06-06

## Goal

Support screen sharing during a live session without exposing presenter-only material. The presenter can copy a mirror link from the live presenter view. The link opens a read-only mirror page that visually follows the presenter’s current slide, including live interaction slides, but never exposes presenter notes, audience questions, moderation controls, or slide navigation controls.

## Non-Goals

- Mirror viewers cannot control slide position.
- Mirror viewers cannot vote, answer, raise questions, moderate answers, launch interactions, or end sessions.
- Guest identities do not satisfy allowed-email mirror access.
- The mirror page is not a replacement for the audience page.
- The mirror link does not grant access to deck editing or session transcripts.

## Access Model

Mirror configuration is stored at the deck level and applied to each live session for that deck.

The deck supports three mirror access modes:

1. `owner_only`
   - Only the signed-in deck owner can open the mirror page.
   - Public link tokens do not bypass this mode.

2. `allowed_emails`
   - Only signed-in users whose account email appears in the deck’s mirror allow list can open the mirror page.
   - Audience guests who joined with an allowed email are not accepted.
   - Email comparison is case-insensitive and stores normalized lowercase emails.

3. `public_link`
   - Anyone with the session-specific mirror link can open the mirror page.
   - The link uses a random session mirror token so guessing a session id is not enough.

Mirror settings are deck-level because they are authoring policy. Mirror links are session-specific because the page mirrors one live session’s current state.

## Data Model

Add deck-level mirror settings:

- `mirror_access_mode`: enum string, default `owner_only`
- `mirror_allowed_emails`: JSON array of lowercase email strings, default `[]`

Add session-level mirror token:

- `mirror_token`: nullable unique string, generated when a real live session is created
- Preview sessions may have no mirror token and should not expose mirror links

This requires a backend migration.

## Backend API

### Update Deck Mirror Settings

`PATCH /api/v1/decks/{deck_id}/mirror-access`

Authenticated owner-only endpoint.

Request:

```json
{
  "mode": "owner_only",
  "allowed_emails": []
}
```

Validation:

- `mode` must be one of `owner_only`, `allowed_emails`, `public_link`.
- `allowed_emails` is used only for `allowed_emails`; an empty list is valid and means only the deck owner can access until emails are added.
- Emails are trimmed, lowercased, deduped, and validated.

### Get Mirror Metadata

`GET /api/v1/sessions/{session_id}/mirror-link`

Authenticated host/owner endpoint.

Returns:

```json
{
  "url": "https://app.example.com/mirror/{session_id}?token=...",
  "access_mode": "public_link"
}
```

For `owner_only` and `allowed_emails`, the URL may omit the token or include it only as a session locator. Access is still enforced from the signed-in user. For `public_link`, the token is required.

### Get Mirror Snapshot

`GET /api/v1/sessions/{session_id}/mirror`

Authentication rules:

- `owner_only`: requires signed-in deck owner.
- `allowed_emails`: requires signed-in user whose email is in allow list or is the deck owner.
- `public_link`: accepts valid `token` query param, or signed-in deck owner.

Response shape mirrors the render portions of `SessionSnapshot` but is sanitized:

- Includes:
  - session id, deck id, deck title, current slide id, started/ended state
  - sections needed to compute slide kicker labels
  - deck slides with markdown, kicker, theme fields, widget placements, widget props
  - session interaction slides with kind/spec/render state
  - active widget bodies required to render placements
  - audience count if already visible in presenter chrome
- Excludes:
  - `presenter_notes`
  - questions
  - participant identities
  - moderation data
  - raw interaction logs
  - host-only fields and controls

### WebSocket Mirror Role

Mirror clients connect with a `role=mirror` or equivalent token classification.

Allowed inbound messages:

- None, except harmless connection lifecycle messages.

Outbound messages:

- Current slide changes.
- Session ended.
- Widget state updates that affect what the slide visually displays.
- Live interaction state updates required to render the public interaction screen.

The server ignores or rejects any mirror attempt to advance slides, submit audience data, raise questions, launch interactions, or moderate answers.

## Frontend UX

### Editor Settings

Add mirror access controls to the editor settings/session area, not Workspace:

- Access mode segmented/radio control:
  - Only owner
  - Allowed users
  - Anyone with link
- Allowed users mode shows an email list editor:
  - add email
  - remove email
  - validation message for malformed emails

The settings persist on the deck.

### Presenter View

Add a “Copy mirror link” button in the presenter top bar near the session code/copy controls.

Behavior:

- Calls mirror-link endpoint.
- Copies link to clipboard.
- Shows a short copied state/toast.
- Hidden in preview iframe sessions.
- If mirror access mode is `owner_only` or `allowed_emails`, the link still works only after signed-in authorization.

### Mirror Page

New route:

`/mirror/:sessionId`

Behavior:

- Loads mirror snapshot.
- Opens mirror WebSocket.
- Renders the current slide using the same slide render components as presenter view.
- Shows live interaction slides, but read-only.
- Has no notes rail, question rail, moderation rail, bottom stepper, open-interaction FAB, answer inputs, voting controls, question FAB, or keyboard slide navigation.
- When session ends, shows a simple ended state.
- If unauthorized, shows a clear sign-in/access message.

## Rendering Rules

Normal deck slides use `SlideStage` in a read-only mirror role.

Live interaction slides use the existing live interaction components in a mirror/read-only mode. If a component currently assumes `presenter` or `audience`, introduce `role="mirror"` and gate controls accordingly:

- Poll: show prompt, choices, and aggregate state if the presenter view would show it; no voting controls.
- Question: show prompt and promoted/public answer state only; no answer input or moderation controls.
- Random audience: show the visible random-selection state; do not expose participant lists beyond what the slide already reveals.

## Security and Privacy

The primary safety property is server-side sanitization. The mirror page must not receive private data and hide it in the UI. It must never receive private data at all.

Tests should verify:

- Mirror snapshot omits presenter notes.
- Mirror snapshot omits questions.
- Mirror snapshot omits participant identities.
- Guest token cannot satisfy `allowed_emails`.
- Public link requires the session mirror token.
- Mirror WebSocket cannot advance slides.

## Implementation Units

1. Backend schema and models
   - Add deck mirror settings and session mirror token.

2. Backend mirror services
   - Access check helper.
   - Sanitized mirror snapshot builder.
   - Mirror-link endpoint.

3. WebSocket support
   - Add mirror role.
   - Restrict inbound commands.
   - Broadcast visual state changes to mirror clients.

4. Frontend API/types/store
   - Add mirror settings and snapshot API types.
   - Add mirror route.

5. Editor controls
   - Add deck mirror access settings in the editor settings/session surface.

6. Presenter controls
   - Add copy mirror link button.

7. Mirror page
   - Read-only slide renderer.
   - Auth/public-token error handling.
   - Session ended state.

## Testing Plan

Backend:

- Migration test/model serialization.
- Owner can update mirror settings.
- Non-owner cannot update mirror settings.
- Owner-only mirror snapshot works for owner and rejects public token-only access.
- Allowed-email mirror snapshot works for signed-in allowed user.
- Allowed-email mirror snapshot rejects guest token even if guest email matches.
- Public-link mirror snapshot requires valid token.
- Mirror snapshot excludes notes/questions/participants.
- Mirror WebSocket role receives slide change but cannot advance slides.

Frontend:

- Editor settings saves mirror mode and allowed emails.
- Presenter copy mirror link calls API and copies URL.
- Mirror route renders current deck slide.
- Mirror route renders interaction slide in read-only mode.
- Mirror route does not render notes/questions/stepper/FAB.
- Unauthorized state is shown for denied access.

## Open Decisions Resolved

- Mirror shows live interaction slides.
- Allowed-email access requires signed-in account identity.
- Mirror policy is deck-level; mirror links are session-specific.
