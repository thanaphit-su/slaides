# SLAIDES Documentation Status

**Generated:** 2026-05-28  
**Purpose:** Track document currency and update priorities following migration 0015 (widget revisions + AI threads) and Widgets v2 rollout.

---

## Quick Summary

| Priority | File | Status | Action | Effort |
|----------|------|--------|--------|--------|
| 🔴 P0 | `ARCHITECTURE.md` | STALE | MAJOR REWRITE | High |
| 🔴 P0 | `SPEC.md` | CONTRADICTORY | MAJOR REWRITE | High |
| 🔴 P0 | `REQUIREMENTS.md` | STALE | UPDATE | Medium |
| 🟡 P1 | `HANDOFF.md` | STALE | UPDATE | Medium |
| 🟡 P1 | `SLIDE_CANVAS_UX_TEST_CASES.md` | STALE | UPDATE | Low |
| 🟢 P2 | `superpowers/plans/*.md` | SUPERSEDED | ARCHIVE | Low |
| 🟢 P2 | `superpowers/specs/*.md` | SUPERSEDED | MERGE | Low |
| ✅ OK | `WIDGETS_V2.md` | CURRENT | KEEP | None |
| ✅ OK | `CONCEPT.md` | CURRENT | KEEP | None |
| ✅ OK | `DESIGN.md` | CURRENT | KEEP | None |
| ✅ OK | `architecture/widget-revisions-ai-workflow.md` | CURRENT | KEEP | None |

---

## Critical Issues by Document

### 🔴 ARCHITECTURE.md (P0 - Blocker)

**Problems:**
1. **Widget model completely outdated** - Shows `workspace_id` but widgets are deck-local since migration 0011
2. **Missing entire revision system** - No `widget_revision`, `widget_ai_thread`, `widget_ai_message` tables
3. **Missing placement_state** - Critical table for Loud widget aggregation not documented
4. **API routes wrong** - Shows workspace-scoped widget endpoints, but they're deck-scoped
5. **Missing columns** - `derived_from_id`, `behavior`, `ai_spec`, `example_props`, `current_revision_id`, `revision_id`

**What needs updating:**
- Section 3.3: Widget data model (complete rewrite)
- Section 3.3: SlideWidget model (add revision_id)
- Section 3.3: Add WidgetRevision, WidgetAiThread, WidgetAiMessage models
- Section 3.3: Add PlacementState model
- Section 4.2: Widget API routes (deck-scoped, not workspace)
- Section 4.2: Add revision management endpoints
- Section 4.2: Add AI thread endpoints

**Source of truth:** 
- `apps/api/src/slaides/db/models.py` (lines 140-239)
- `apps/api/src/slaides/widgets/router.py`
- Migration 0011, 0012, 0015

---

### 🔴 SPEC.md (P0 - Blocker)

**Problems:**
1. **UI flows describe modals that don't exist** - Widget Adjust, Generate with AI are now sidebar-based
2. **Missing Widgets v2 behavior contract** - No Quiet/Loud distinction, no `contribute()` protocol
3. **Typography specs wrong** - Audience uses same non-slim as presenter, not "slim: true"
4. **Widget collection UX outdated** - Describes old drawer, not persistent sidebar with chat

**What needs updating:**
- Section 3.4: Widget tab → persistent right sidebar
- Section 3.8: AI chat modal → sidebar chat thread
- Section 3.10: Widget collection redesign (sun-icon popover, library popover, compact cards)
- Section 3.11: Adjust modal → sidebar adjust mode
- Section 5.3: Audience typography (remove "slim: true")
- Section 7: Widget collection (remove workspace tab reference)
- Section 9: Widget contract (add behavior, contribute protocol, props_schema)

**Source of truth:**
- `apps/web/src/components/WidgetCollection.vue`
- `apps/web/src/widgets/bridge.ts`
- HANDOFF.md lines 45-47

---

### 🔴 REQUIREMENTS.md (P0 - Blocker)

**Problems:**
1. **FR-045 contradicts implemented design** - Says "reusable across decks" but widgets are deck-local with explicit copy
2. **Widget schema outdated** - Missing behavior, ai_spec, example_props, revision system
3. **FR-027** - Describes drawer, not persistent sidebar
4. **FR-080** - Says "one endpoint" but system supports multi-model library with capability routing

**What needs updating:**
- FR-027: Update to persistent sidebar description
- FR-031: Clarify same-deck constraint with copy workflow
- FR-040: Add behavior, ai_spec, example_props, current_revision_id to schema
- FR-045: Rewrite to describe deck-local ownership + cross-deck copy
- FR-054: Update to describe FAB menu + unified contribute protocol
- FR-080: Update to describe multi-model library + capability routing

**Source of truth:**
- HANDOFF.md lines 47, 100
- `apps/api/src/slaides/widgets/router.py`
- `apps/api/src/slaides/llm/service.py`

---

### 🟡 HANDOFF.md (P1 - Important)

**Problems:**
1. **Test counts outdated** - Claims 164 backend / 162 frontend; actual: 166 / 188
2. **References deleted .swidget files** - Lines 162-163, 296, 330, 337, 381 reference non-existent files
3. **Field Notes widget claim wrong** - Line 158 says seed.py links widgets, but Field Notes is content-only
4. **Tutorial slide count wrong** - Line 53 says "9-slide" but line 59 correctly says "10 slides"
5. **Missing migration 0015** - Documents migrations 0001-0014 but omits 0015 entirely
6. **References removed setting** - Line 35 mentions `SUPABASE_AUTH_VERIFY_VIA_SERVER` as dropped, but line 85 still references it

**What needs updating:**
- Line 13: Update test counts
- Lines 135-147: Add migration 0015 documentation
- Lines 158, 162-163: Remove .swidget references
- Line 164: Update seed widget description
- Line 296: Update repository layout
- Line 330, 337, 381: Remove .swidget references
- Line 53: Fix tutorial slide count to "10-slide"

**Source of truth:**
- `apps/api/migrations/versions/0015_widget_revisions_ai_threads.py`
- `apps/api/scripts/seed.py`
- `packages/widget-runtime/seeds/` (empty)
- Actual test output

---

### 🟡 SLIDE_CANVAS_UX_TEST_CASES.md (P1 - Important)

**Problems:**
1. **Dated 2026-05-20** - Many changes since then (sidebar redesign, widget AI revisions)
2. **Line 97-99** - Add-widget ribbon behavior may conflict with sidebar redesign
3. **Line 178** - References "right edge Adjust widget tab" which is now sidebar adjust mode

**What needs updating:**
- Update date to current
- Review all widget adjustment flows against current sidebar implementation
- Verify add-widget behavior matches WidgetCollection.vue implementation

**Source of truth:**
- `apps/web/src/components/WidgetCollection.vue`
- `apps/web/src/pages/Editor.vue`

---

### 🟢 Superpowers Plans (P2 - Archive)

**Files:**
- `superpowers/plans/2026-05-26-widget-ai-revisions-agentic-workflow.md`
- `superpowers/plans/2026-05-21-supabase-auth-signup-approval.md`

**Status:** Implementation plans with all tasks marked complete. Features shipped per HANDOFF.md.

**Action:** Move to `docs/archive/plans/` or delete. These served their purpose.

---

### 🟢 Superpowers Specs (P2 - Merge)

**Files:**
- `superpowers/specs/2026-05-21-supabase-auth-signup-approval-design.md`

**Status:** Design spec for shipped features. Design decisions now reflected in implementation.

**Action:** Merge relevant design decisions into ARCHITECTURE.md section on auth, then archive.

---

## Documents to Keep (No Action)

### ✅ WIDGETS_V2.md
- Reference design brief for Widgets v2
- Correctly describes deck-local ownership, placement_state, five aggregators, Quiet/Loud split
- All shipped features marked with dates that match HANDOFF.md

### ✅ CONCEPT.md
- High-level product vision
- Implementation-agnostic
- No contradictions found

### ✅ DESIGN.md
- Design token system
- Visual direction ("Editorial Press")
- No implementation-specific claims

### ✅ architecture/widget-revisions-ai-workflow.md
- Authoritative contract for migration 0015
- Correctly describes data ownership, behavior rules, AI workflow envelope
- Aligns with shipped implementation

---

## Update Strategy

### Phase 1: Fix Blockers (Do First)

1. **ARCHITECTURE.md** - Complete data model rewrite
   - Add all migration 0011/0012/0015 tables and columns
   - Update API routes to deck-scoped endpoints
   - Add revision management endpoints
   - Add placement_state and aggregators

2. **SPEC.md** - UI flows and widget contract
   - Replace all modal descriptions with sidebar flows
   - Add Widgets v2 behavior contract (Quiet/Loud, contribute protocol)
   - Fix audience typography specs
   - Update widget collection UX

3. **REQUIREMENTS.md** - Functional requirements
   - Fix widget ownership (deck-local with copy)
   - Add revision system to widget schema
   - Update AI/LLM requirements (multi-model, capability routing)

### Phase 2: Clean Up (Do Second)

4. **HANDOFF.md** - Fix contradictions and outdated refs
   - Update test counts
   - Add migration 0015
   - Remove .swidget references
   - Fix tutorial slide count
   - Fix Field Notes description

5. **SLIDE_CANVAS_UX_TEST_CASES.md** - Review against current UX
   - Update widget adjustment flows
   - Verify add-widget behavior

### Phase 3: Archive (Do Last)

6. **superpowers/plans/** - Move to archive or delete
7. **superpowers/specs/** - Merge design decisions, then archive

---

## Verification Checklist

After updates, verify:

- [ ] All migration numbers match actual files in `apps/api/migrations/versions/`
- [ ] Test counts match actual `uv run pytest` and `npm test` output
- [ ] No references to `packages/widget-runtime/seeds/*.swidget` (directory is empty)
- [ ] Widget API routes use `/decks/{deck_id}/widgets` not `/widgets`
- [ ] Widget model includes `deck_id`, `derived_from_id`, `behavior`, `current_revision_id`
- [ ] SlideWidget model includes `revision_id`
- [ ] WidgetRevision, WidgetAiThread, WidgetAiMessage models documented
- [ ] PlacementState model and aggregators documented
- [ ] UI flows describe sidebars, not modals
- [ ] Audience typography matches presenter (non-slim)
- [ ] Widget contract includes behavior.kind, contribute(), props_schema

---

## Ownership

- **ARCHITECTURE.md** → Backend team (data models, API routes)
- **SPEC.md** → Frontend team (UI flows, widget contract)
- **REQUIREMENTS.md** → Product/Engineering lead (functional requirements)
- **HANDOFF.md** → Engineering lead (release notes, current state)
- **SLIDE_CANVAS_UX_TEST_CASES.md** → QA/Frontend team (UX test cases)

---

## Next Steps

1. **Assign owners** to each P0/P1 document
2. **Create GitHub issues** for each update task
3. **Set deadline** for Phase 1 completion (blocker docs)
4. **Schedule review** to verify all contradictions resolved
5. **Establish process** for keeping docs current after future migrations
