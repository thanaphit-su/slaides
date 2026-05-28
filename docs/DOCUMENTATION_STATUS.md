# SLAIDES Documentation Status

**Updated:** 2026-05-28

This file records the documentation state after the 2026-05-28 docs refresh and a code-level audit against `apps/web` and `apps/api`.

## Quick Summary

| File | Status | Notes |
|---|---|---|
| `README.md` | CURRENT | Now describes both implemented app/API and prototype reference. |
| `ARCHITECTURE.md` | CURRENT WITH M5 CAVEATS | Data model, widget revisions, AI threads, and placement state match code. Transcript routes and worker/export notes are documented as future, not current. |
| `SPEC.md` | CURRENT WITH M5 CAVEATS | Auth, widget sidebar, AI Adjust, settings, and widget collection text match current implementation. Transcript/display persistence remain future. |
| `REQUIREMENTS.md` | CURRENT WITH EXPLICIT BACKLOG ITEMS | Shipped items use check marks; transcript view/export, display persistence, and i18n catalog are marked backlog. |
| `HANDOFF.md` | CURRENT | Most detailed implementation history; latest verified counts are 166 backend / 190 frontend. |
| `SLIDE_CANVAS_UX_TEST_CASES.md` | NEEDS REVIEW | Still useful as a manual UX checklist, but should be rechecked against preview mode and widget-revision flows. |
| `WIDGETS_V2.md` | CURRENT | Reference design brief plus shipped decision log. |
| `architecture/widget-revisions-ai-workflow.md` | CURRENT | Authoritative contract for migration 0015 workflow. |
| `CONCEPT.md` | CURRENT | High-level product vision. |
| `DESIGN.md` | CURRENT | Design tokens and visual direction. |

## Current Known Caveats

- Transcript UI and transcript export are not implemented yet. The current code persists interaction data, native live interaction results, and placement state needed for future transcript work.
- Display preferences are not persisted yet. The settings UI explicitly labels dark mode and editor density persistence as later-release work.
- The current frontend uses a custom markdown renderer/contenteditable editor, not `remark` or Monaco.
- The API has no Celery worker dependency today. Background transcript summarisation/export workers are a deployment/future-work concept, not current code.

## Verification

Commands run during the audit:

```sh
cd apps/api && uv run pytest -q
cd apps/web && npm test -- --run
```

Results:

- Backend: 166 passed.
- Frontend: 190 passed.
