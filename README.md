# SLAIDES

> A press for talks worth keeping.

SLAIDES is a web-based platform for **interactive presentations** — slide decks that can host live polls, open questions, AI-generated widgets, and on-the-fly interpretations of selected text. Every audience interaction is logged for later analysis: who participated, what they typed, what terms they asked the LLM to explain.

This repository contains the **SLAIDES v0.1 implementation**, archived draft/reference material, and the product/design documentation. The implemented app is a Vue 3 + Vite frontend in `apps/web` backed by a FastAPI service in `apps/api`; the old React prototype now lives under `.draft/prototype`.

---

## What's inside

| File / Folder | What it is |
|---|---|
| `apps/web` | Implemented Vue 3 + Vite frontend |
| `apps/api` | Implemented FastAPI backend, Alembic migrations, tests, and seed/eval scripts |
| `docker-compose.yml`, `docker/supabase/`, `supabase/` | Local Supabase + Redis development services |
| `docs/CONCEPT.md` | Product concept, user roles, primary jobs-to-be-done |
| `docs/SPEC.md` | Functional spec — every screen, every interaction |
| `docs/REQUIREMENTS.md` | Functional + non-functional requirements with acceptance criteria |
| `docs/ARCHITECTURE.md` | System architecture, data model, API surface, realtime protocol |
| `docs/HANDOFF.md` | What the next agent / engineering team needs to implement, in order |
| `docs/DESIGN.md` | Design tokens (colors, type, spacing, components, motion) |
| `.draft/prototype` | Archived React+Babel prototype (`slaides.html` + `src/*.jsx`) |
| `.draft/visual-directions` | Archived early visual-direction board. Direction **B** was chosen. |
| `.draft/docs` | Superseded plans, snapshots, and documentation-maintenance notes |

## How to run the implemented app

1. Copy `.env.example` to `.env` and adjust local secrets if needed.
2. Run `make up` to start Supabase and Redis.
3. Run `make migrate` and `make seed`.
4. Run `make api` and `make web` in separate terminals.
5. Open the web app at `http://localhost:5173`.

Useful local URLs:
- API: `http://localhost:8000`
- Supabase API/Auth: `http://localhost:54321`
- Supabase Studio: `http://localhost:54323`

## Production container rehearsal

`docker-compose.prod.yml` builds the FastAPI API and the Vue static web image, runs Redis with persistence, and expects managed Postgres/Supabase values through environment variables.

1. Set production environment variables: `DATABASE_URL`, `CORS_ORIGINS`, `JWT_SECRET`, `GUEST_JWT_SECRET`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, and `LLM_ENCRYPTION_SECRET`.
2. Run `make prod-build`.
3. Run `make prod-migrate`.
4. Run `make prod-up`.
5. Check `GET /readyz` through the deployed web/API route.

Before a first large live session, create a real live session and run:

```bash
make load-rehearsal API_URL=https://your-host.example/api/v1 CODE=SLD-XXXX-XX AUDIENCE=150 CONCURRENCY=25
```

For a loud-widget burst test, add `PLACEMENT_ID=<placement_id>`. The rehearsal exits non-zero if errors occur or p95 budgets are exceeded.

## How to read the prototype

1. Open `.draft/prototype/slaides.html` in a browser.
2. A floating **PROTOTYPE NAV** strip appears at the bottom-left. Use it to jump between the five primary surfaces:
   - **Sign in** — auth + guest-join flow
   - **Library** — instructor's deck collection (home/workspace)
   - **Editor** — slide editor with sidebar, content, widgets, AI prompts
   - **Presenter** — live presenting view with audience panel
   - **Audience** — mobile audience view
3. Most interactive elements are wired up with mocked delays. Treat the prototype as a visual/interaction reference; use `apps/web` + `apps/api` for current behavior.

## Stack chosen for production

| Layer | Choice |
|---|---|
| Backend | **FastAPI** (async, modern, OpenAPI built-in) |
| Database | **Supabase (PostgreSQL)** |
| Realtime | **WebSockets** (single channel per session) |
| Frontend | **Vue 3 + Vite** |
| Widget runtime | **Sandboxed iframe** + postMessage bridge; generated/starter widgets are self-contained HTML/CSS/JS |
| LLM | **OpenAI-compatible only**, configured per workspace (base URL + key + model library/capability routing) |
| Anonymous storage | Hash(email + per-session salt), retain hash + content |

The archived prototype is React for visual reference. The production implementation now lives in Vue 3 under `apps/web`.

## License & status

v0.1 — implemented local development build plus prototype reference. Not production hardened. See `LICENSE` (TBD).
