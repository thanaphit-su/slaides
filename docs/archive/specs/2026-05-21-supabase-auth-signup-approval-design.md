# Supabase Auth Sign-Up Approval Design

## Context

SLAIDES currently uses a local FastAPI auth router that verifies `app_user.password_hash`, issues custom instructor access/refresh JWTs, and separately issues custom guest JWTs for audience session joins. The v0.1 specification originally allowed instructor sign-in only and kept "Request access" as a waitlist. This design updates that product rule: instructors may sign up, but a new instructor needs approval before accessing the workspace.

Supabase Auth becomes the source of truth for instructor credentials and sessions. SLAIDES remains the source of truth for application authorization: workspace membership, user role, deck ownership, and approval state. Audience guest joins remain on the existing session-scoped guest token path because they already satisfy the privacy requirements around `participant_ref = sha256(email + session_salt)` and ended-session rejection.

## Goals

- Add instructor sign-up with email and password.
- Require approval before a newly signed-up instructor can access `/workspace`, decks, widgets, sessions, or LLM endpoints.
- Use Supabase Auth for instructor credential verification, access tokens, refresh tokens, and sign-up.
- Keep existing audience guest-join behavior unchanged.
- Add local Supabase services including Studio and the required Auth/API/database services.
- Preserve existing developer flow: `make up`, `make migrate`, `make seed`, `make api`, and `make web`.

## Non-Goals

- No production admin UI for approvals in this pass.
- No migration to Supabase PostgREST as the SLAIDES application API.
- No rewrite of app authorization into RLS policies.
- No social login, magic links, MFA, or password reset UI in this pass.
- No change to audience guest tokens.

## Architecture

The browser continues to talk to the SLAIDES FastAPI API for application data. For instructor identity, the backend delegates to Supabase Auth:

1. `POST /api/v1/auth/signup` calls Supabase Auth sign-up and creates a local `app_user` row with `approval_status = "pending"`.
2. `POST /api/v1/auth/signin` calls Supabase Auth password sign-in and then resolves the local `app_user` row by Supabase user id or email.
3. `POST /api/v1/auth/refresh` calls Supabase Auth refresh and returns the same frontend-compatible token shape.
4. Protected backend dependencies validate instructor bearer tokens as Supabase Auth tokens, then load the matching local `app_user`.
5. If the local user is not approved, protected application routes return `403 account pending approval`.

SLAIDES keeps issuing custom guest JWTs from `/auth/guest`. The auth dependencies continue to accept either a Supabase instructor token or a custom guest token where guest access is already allowed.

## Data Model

`app_user` gains:

- `supabase_user_id UUID NULL UNIQUE`: links the local user to `auth.users.id`.
- `approval_status VARCHAR(40) NOT NULL DEFAULT 'approved'`: one of `pending`, `approved`, or `rejected`.
- `approved_at TIMESTAMPTZ NULL`: set when approved.

Existing seeded/demo users remain approved. New sign-ups are pending. Pending users can exist without a workspace initially, or they can be assigned to a default pending workspace. To minimize schema churn against existing `workspace_id NOT NULL`, signup creates or reuses a "Pending Instructors" workspace for pending users. Approval can later move them into the intended workspace if needed. In local development, SLAIDES migrations run against Supabase local Postgres so Studio can inspect and edit `app_user.approval_status`.

## API Behavior

### `POST /auth/signup`

Request:

```json
{
  "email": "new@example.com",
  "password": "strong-password",
  "display_name": "New Instructor"
}
```

Behavior:

- Lowercase and trim email.
- Call Supabase Auth sign-up.
- Create or update local `app_user` with `approval_status = "pending"` and `supabase_user_id`.
- Return a frontend-compatible auth response with tokens when Supabase returns a session, plus the user object including `approval_status`.
- If email confirmation is enabled and Supabase does not return a session, return a pending user response without app access and with a message that email confirmation may be required.

### `POST /auth/signin`

Behavior:

- Call Supabase Auth password sign-in.
- Resolve local `app_user` by `supabase_user_id` first, then email.
- If a legacy approved local seeded user exists by email but has no `supabase_user_id`, link it.
- Return Supabase access and refresh tokens.
- Include `approval_status` in the user object.
- The sign-in itself may succeed for pending users, but the frontend routes them to a pending-approval state instead of `/workspace`.

### `POST /auth/refresh`

Behavior:

- Call Supabase Auth refresh-token endpoint.
- Resolve the local user from the refreshed access token.
- Return the same `AuthResponse` shape with rotated tokens.

### `GET /auth/me`

Behavior:

- Validates the Supabase instructor token.
- Returns `UserOut` including `approval_status`.
- Pending and rejected users are visible to themselves through `/me`, but application routes still block them.

### Protected Application Routes

Routes that use `current_user` require `approval_status = "approved"`. Pending users receive:

```json
{
  "detail": "account pending approval"
}
```

with HTTP 403. Rejected users receive:

```json
{
  "detail": "account rejected"
}
```

with HTTP 403.

## Frontend UX

The existing sign-in page keeps the instructor/audience mode switch. Instructor mode gains a secondary Sign in / Sign up switch.

Sign-up fields:

- Email.
- Display name.
- Password.
- Confirm password.

After signup:

- If the user is pending, show an approval-pending state with concise copy.
- Do not route to `/workspace`.
- If a pending user signs in later, show the same pending state.

Existing audience join UI is unchanged.

## Local Supabase Services

Local development should expose:

- Supabase API/Auth gateway: `http://localhost:54321`
- Supabase Postgres and SLAIDES application DB: `localhost:54322`
- Supabase Studio: `http://localhost:54323`
- Existing SLAIDES API: `http://localhost:8000`
- Existing SLAIDES web: `http://localhost:5173`

The implementation should prefer the Supabase CLI local stack when available because it includes the expected Auth, Studio, API gateway, and local SMTP/testing services with less hand-maintained Compose surface. The repo should document required env vars in `.env.example`:

```bash
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_ISSUER=http://localhost:54321/auth/v1
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres
```

The backend must never expose `SUPABASE_SERVICE_ROLE_KEY` to the browser. The frontend should keep using the SLAIDES API and should not need the service role key.

## Approval Workflow

For this pass, approval is operational rather than productized:

- An approver can use Supabase Studio or SQL to set `app_user.approval_status = 'approved'`.
- A small backend script may be added to approve by email for local development.
- A full Settings/Admin UI is deferred.

## Testing

Backend tests:

- Signup creates a pending local app user.
- Pending signed-in users cannot access `/workspace`.
- Approved Supabase-authenticated users can access `/workspace`.
- Refresh delegates to the Supabase-compatible auth client and rotates stored frontend tokens.
- Legacy seeded user sign-in links `supabase_user_id` when email matches.
- Guest join still returns the custom guest token and guest-only live interpret remains scoped.

Frontend tests:

- Auth store can sign up and stores pending approval state.
- Sign-in with a pending user does not route to workspace.
- API refresh path still updates access and refresh tokens.
- Audience guest join remains unaffected.

Manual verification:

- Start local Supabase services and open Studio.
- Seed the approved demo instructor.
- Sign in as `you@studio.press / slaides`.
- Sign up a new instructor and verify pending approval UI.
- Approve the new instructor through DB/Studio/script and verify workspace access.

## Open Risks

- Supabase Auth local service configuration must match backend token verification assumptions. Prefer Auth server `/user` verification or JWKS-based verification over trusting unverified JWT claims.
- Email confirmation behavior differs between hosted and local Supabase. The UI must handle both immediate-session and confirm-email flows.
- Self-hosting the full Supabase Docker stack is heavier than the current two-service compose. The CLI local stack is simpler for development; production deployment should be a separate infrastructure decision.
