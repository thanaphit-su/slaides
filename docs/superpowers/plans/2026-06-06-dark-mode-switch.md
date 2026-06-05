# Dark Mode Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted dark mode switch that reliably themes the app shell, editor, presenter/audience views, transcripts, and widget iframes.

**Architecture:** Use the existing CSS token system in `apps/web/src/theme/tokens.css` as the source of truth. Add one small theme composable/store that applies `dark` or `light` to `document.documentElement`, persists the preference in `localStorage`, and reacts to system preference only when the user chooses `system`. Update widget token capture so iframes re-read host tokens when the app theme changes.

**Tech Stack:** Vue 3 Composition API, Pinia/Vue composable style, CSS custom properties, Vitest, Vue Test Utils, Playwright/browser screenshot checks if implementation touches visual surfaces.

---

## Scrutinize Pass

**Intent:** The feature is not “add a dark palette”; the palette already exists. The actual job is to add a runtime theme owner and close the surfaces where hardcoded colors or one-time token snapshots bypass that owner.

**Simpler alternative:** Do not introduce a database-backed display setting yet. `docs/DOCUMENTATION_STATUS.md` says display persistence is future work, and the app already has local display state patterns. A local `localStorage` preference plus `prefers-color-scheme` support solves the current user need without backend migration or workspace contract churn.

**Finding 1: A plan that only toggles `.dark` on one view will not work globally.**
- Why it matters: route transitions and modals would fall back to light because `tokens.css` defines `.dark`, but nothing owns the class at app startup.
- Evidence: `apps/web/src/main.ts` only mounts `App`; `apps/web/src/App.vue` only renders `RouterView`; `apps/web/src/theme/tokens.css` defines `.dark` but no code applies it.
- Suggested change: create `apps/web/src/theme/useThemeMode.ts` and initialize it once in `App.vue`, applying classes to `document.documentElement`.

**Finding 2: Widgets will remain stale if the theme changes after mount.**
- Why it matters: `WidgetFrame` snapshots host tokens once, then bakes them into iframe `srcdoc`; changing `.dark` later does not cross the iframe boundary.
- Evidence: `apps/web/src/widgets/theme-tokens.ts` reads `getComputedStyle(document.documentElement)`; `apps/web/src/widgets/WidgetFrame.vue` stores `const hostTokens = readHostTokens()` at module setup and builds `srcdoc` from that value.
- Suggested change: make theme mode reactive and pass a `themeVersion`/`themeKey` into `WidgetFrame`, or make `WidgetFrame` subscribe to a `slaides:theme-changed` window event and rebuild `srcdoc`.

**Finding 3: Hardcoded literals must be audited, not globally banned.**
- Why it matters: overlays like `rgba(11, 13, 16, 0.42)` are intentionally fixed scrims, while SVG thumbnails in `DeckCover.vue` are mini artwork and should not necessarily theme-switch.
- Evidence: `rg` finds real risk areas: `Toggle.vue` uses `background: '#fff'`; `DeckCard.vue` uses `background: '#fff'`; `SlideCanvas.vue` uses `color: #8bb0ff`; `WidgetFrame.vue` uses `#d9534f` for inspector outline. But `DeckCover.vue` SVG literals are preview illustrations and may be intentionally fixed.
- Suggested change: replace app-control literals with tokens, document intentional exceptions in a test allowlist.

**Finding 4: Presenter/live interaction slides have inverted-theme code that can conflict with app dark mode.**
- Why it matters: `Presenter.vue` manually chooses `background: currentSessionSlide?.inverted_theme ? var(--ink) : var(--paper)`, and live components contain several white/rgba literals for inverted cards. App dark mode must not double-invert or make live interactions illegible.
- Evidence: `apps/web/src/pages/Presenter.vue` uses explicit paper/ink switching; `LivePollSlide.vue`, `LiveQuestionSlide.vue`, and `LiveRandomAudienceSlide.vue` contain white rgba styles.
- Suggested change: keep `session_slide.inverted_theme` semantics separate from app theme; add tests/screenshots for deck slide, poll slide, question slide, and random slide in both modes.

Verdict: **fix-then-ship**. The smallest correct plan is a centralized root theme owner plus targeted color audit and widget iframe invalidation; anything less will leave high-risk surfaces stuck in light mode.

---

## Component Map

- `apps/web/src/theme/useThemeMode.ts`: Single source of truth for theme preference, resolved mode, persistence, media query listener, root class application, and theme-change event.
- `apps/web/src/App.vue`: Initializes the theme composable once for all routes.
- `apps/web/src/components/SettingsDrawer.vue`: Replaces the placeholder Display copy with a theme segmented control or toggle.
- `apps/web/src/widgets/WidgetFrame.vue`: Rebuilds iframe `srcdoc` when theme tokens change.
- `apps/web/src/components/WidgetThumbnail.vue`: Re-reads host tokens for thumbnails when theme changes.
- Existing page/components with literals: targeted token cleanup where the literal is UI chrome rather than intentional content/artwork.

---

## Task 1: Theme Mode Composable

**Files:**
- Create: `apps/web/src/theme/useThemeMode.ts`
- Modify: `apps/web/src/App.vue`
- Test: `apps/web/tests/theme-mode.test.ts`

- [ ] **Step 1: Write failing tests**

Create `apps/web/tests/theme-mode.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { useThemeMode, THEME_MODE_STORAGE_KEY } from "../src/theme/useThemeMode";

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark", "light");
});

describe("useThemeMode", () => {
  it("applies dark class and persists explicit dark mode", () => {
    const theme = useThemeMode();
    theme.setMode("dark");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);
    expect(localStorage.getItem(THEME_MODE_STORAGE_KEY)).toBe("dark");
  });

  it("applies light class and removes dark when mode changes", () => {
    const theme = useThemeMode();
    theme.setMode("dark");
    theme.setMode("light");

    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("emits a theme change event for iframe/token consumers", () => {
    const listener = vi.fn();
    window.addEventListener("slaides:theme-changed", listener);
    const theme = useThemeMode();

    theme.setMode("dark");

    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      type: "slaides:theme-changed",
    }));
    window.removeEventListener("slaides:theme-changed", listener);
  });
});
```

Run:

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/theme-mode.test.ts
```

Expected: fail because `useThemeMode.ts` does not exist.

- [ ] **Step 2: Implement composable**

Create `apps/web/src/theme/useThemeMode.ts`:

```ts
import { computed, onBeforeUnmount, shallowRef } from "vue";

export type ThemeMode = "light" | "dark" | "system";
export const THEME_MODE_STORAGE_KEY = "slaides:theme-mode";

const mode = shallowRef<ThemeMode>(readStoredMode());
const systemDark = shallowRef(false);
let mediaQuery: MediaQueryList | null = null;
let listenerAttached = false;

function readStoredMode(): ThemeMode {
  if (typeof localStorage === "undefined") return "system";
  const raw = localStorage.getItem(THEME_MODE_STORAGE_KEY);
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

function resolvedModeValue(): "light" | "dark" {
  return mode.value === "system" ? (systemDark.value ? "dark" : "light") : mode.value;
}

function applyTheme(): void {
  if (typeof document === "undefined") return;
  const resolved = resolvedModeValue();
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document.documentElement.classList.toggle("light", resolved === "light");
  window.dispatchEvent(new CustomEvent("slaides:theme-changed", { detail: { mode: mode.value, resolved } }));
}

function ensureMediaListener(): void {
  if (typeof window === "undefined" || listenerAttached) return;
  mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)") || null;
  systemDark.value = !!mediaQuery?.matches;
  mediaQuery?.addEventListener("change", onSystemThemeChange);
  listenerAttached = true;
}

function onSystemThemeChange(event: MediaQueryListEvent): void {
  systemDark.value = event.matches;
  if (mode.value === "system") applyTheme();
}

export function useThemeMode() {
  ensureMediaListener();
  applyTheme();

  function setMode(next: ThemeMode): void {
    mode.value = next;
    localStorage.setItem(THEME_MODE_STORAGE_KEY, next);
    applyTheme();
  }

  onBeforeUnmount(() => {
    mediaQuery?.removeEventListener("change", onSystemThemeChange);
    listenerAttached = false;
  });

  return {
    mode,
    resolvedMode: computed(resolvedModeValue),
    setMode,
  };
}
```

- [ ] **Step 3: Initialize in `App.vue`**

Modify `apps/web/src/App.vue`:

```vue
<script setup lang="ts">
import { RouterView } from "vue-router";
import { useThemeMode } from "@/theme/useThemeMode";

useThemeMode();
</script>

<template>
  <RouterView />
</template>
```

- [ ] **Step 4: Run tests**

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/theme-mode.test.ts
```

Expected: pass.

---

## Task 2: Settings Display Control

**Files:**
- Modify: `apps/web/src/components/SettingsDrawer.vue`
- Test: `apps/web/tests/settings-drawer.test.ts`

- [ ] **Step 1: Add failing settings test**

Append to `apps/web/tests/settings-drawer.test.ts`:

```ts
it("changes theme mode from the Display tab", async () => {
  const wrapper = mount(SettingsDrawer, {
    props: {
      open: true,
      userEmail: "instructor@example.com",
      userName: "Instructor",
      workspace: baseWorkspace(),
    },
  });

  await wrapper.findAll(".settings-tabs button").find((b) => b.text() === "Display")!.trigger("click");
  await wrapper.get('[data-testid="theme-mode-dark"]').trigger("click");

  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(localStorage.getItem("slaides:theme-mode")).toBe("dark");
});
```

Run:

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/settings-drawer.test.ts
```

Expected: fail because Display tab has placeholder copy and no buttons.

- [ ] **Step 2: Implement Display tab controls**

In `SettingsDrawer.vue` script, import and initialize:

```ts
import { useThemeMode, type ThemeMode } from "@/theme/useThemeMode";

const theme = useThemeMode();
const themeOptions: { value: ThemeMode; label: string; description: string }[] = [
  { value: "system", label: "System", description: "Follow this device." },
  { value: "light", label: "Light", description: "Use the editorial light palette." },
  { value: "dark", label: "Dark", description: "Use the low-light palette." },
];
```

Replace the Display placeholder section with:

```vue
<section v-if="tab === 'display'" class="settings-stack">
  <div class="settings-block">
    <h3>Display</h3>
    <p>Choose how SLAIDES appears on this device.</p>
    <div class="theme-mode-grid" role="radiogroup" aria-label="Theme mode">
      <button
        v-for="option in themeOptions"
        :key="option.value"
        type="button"
        class="theme-mode-option"
        :class="{ active: theme.mode.value === option.value }"
        :data-testid="`theme-mode-${option.value}`"
        :aria-checked="theme.mode.value === option.value"
        role="radio"
        @click="theme.setMode(option.value)"
      >
        <strong>{{ option.label }}</strong>
        <span>{{ option.description }}</span>
      </button>
    </div>
  </div>
</section>
```

Add scoped styles:

```css
.theme-mode-grid {
  display: grid;
  gap: 8px;
}

.theme-mode-option {
  border: 1px solid var(--rule);
  background: var(--paper-2);
  color: var(--ink);
  border-radius: var(--r-md);
  padding: 10px 12px;
  text-align: left;
  display: grid;
  gap: 3px;
}

.theme-mode-option span {
  color: var(--ink-soft);
  font-size: 12px;
}

.theme-mode-option.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
```

- [ ] **Step 3: Run settings test**

Expected: pass.

---

## Task 3: Widget Iframe Theme Refresh

**Files:**
- Modify: `apps/web/src/widgets/WidgetFrame.vue`
- Modify: `apps/web/src/components/WidgetThumbnail.vue`
- Test: `apps/web/tests/widget-frame.test.ts`

- [ ] **Step 1: Add failing widget refresh test**

Add to `widget-frame.test.ts`:

```ts
it("rebuilds srcdoc when the host theme changes", async () => {
  const wrapper = mount(WidgetFrame, {
    props: {
      widget: quietWidget({ html: "<section>Theme aware</section>" }),
      placementId: "p-theme",
      role: "preview",
    },
  });
  const before = wrapper.find("iframe").attributes("srcdoc") || "";

  document.documentElement.classList.add("dark");
  window.dispatchEvent(new CustomEvent("slaides:theme-changed"));
  await nextTick();

  const after = wrapper.find("iframe").attributes("srcdoc") || "";
  expect(after).not.toBe(before);
  expect(after).toContain("--background: #0d0e10");
});
```

Run:

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/widget-frame.test.ts
```

Expected: fail because `hostTokens` is captured once.

- [ ] **Step 2: Make host tokens reactive**

In `WidgetFrame.vue`, replace:

```ts
const hostTokens = readHostTokens();
```

with:

```ts
const hostTokens = ref(readHostTokens());

function refreshThemeTokens(): void {
  hostTokens.value = readHostTokens();
}

onMounted(() => {
  window.addEventListener("slaides:theme-changed", refreshThemeTokens);
});

onBeforeUnmount(() => {
  window.removeEventListener("slaides:theme-changed", refreshThemeTokens);
});
```

Update the `buildSrcdoc` call site to pass `hostTokens.value`.

- [ ] **Step 3: Apply same pattern to thumbnails**

In `WidgetThumbnail.vue`, any `readHostTokens()` snapshot used for iframe srcdoc must become a reactive ref and listen for `slaides:theme-changed`.

- [ ] **Step 4: Run widget tests**

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/widget-frame.test.ts tests/widget-thumbnail.test.ts
```

Expected: pass.

---

## Task 4: Hardcoded Color Cleanup

**Files:**
- Modify: `apps/web/src/theme/tokens.css`
- Modify: `apps/web/src/components/Toggle.vue`
- Modify: `apps/web/src/components/DeckCard.vue`
- Modify: `apps/web/src/components/SlideCanvas.vue`
- Modify: `apps/web/src/widgets/WidgetFrame.vue`
- Modify targeted modal/overlay components only when literals are UI chrome and not intentional scrims/artwork.
- Test: `apps/web/tests/theme-color-audit.test.ts`

- [ ] **Step 1: Add allowlisted audit test**

Create `apps/web/tests/theme-color-audit.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { globSync } from "glob";

const allowlist = new Set([
  "src/theme/tokens.css",
  "src/components/DeckCover.vue",
  "src/components/LivePollSlide.vue",
  "src/components/LiveQuestionSlide.vue",
  "src/components/LiveRandomAudienceSlide.vue",
]);

describe("theme color audit", () => {
  it("keeps non-allowlisted UI chrome on CSS theme tokens", () => {
    const root = join(process.cwd(), "src");
    const files = globSync("**/*.{vue,ts,css}", { cwd: root });
    const offenders = files.flatMap((file) => {
      if (allowlist.has(file)) return [];
      const text = readFileSync(join(root, file), "utf8");
      const matches = text.match(/#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(|color:\s*['"]?(white|black)|background:\s*['"]?(white|black)/g);
      return matches ? [`${file}: ${matches.join(", ")}`] : [];
    });

    expect(offenders).toEqual([]);
  });
});
```

Run:

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run tests/theme-color-audit.test.ts
```

Expected: fail on known literals.

- [ ] **Step 2: Replace obvious UI literals with tokens**

Examples:

```ts
// Toggle.vue
background: 'var(--paper)'
boxShadow: 'var(--shadow-1)'

// DeckCard.vue
background: 'var(--paper)'

// WidgetFrame.vue inspector outline
el.style.outline = on ? "2px solid var(--err)" : "";

// SlideCanvas.vue AI toolbar accent text
color: var(--accent)
```

- [ ] **Step 3: Keep intentional exceptions documented**

Leave `DeckCover.vue` SVG artwork and live-slide inverted-mode rgba styles in the allowlist unless implementation finds actual contrast failures. Add a comment in the test explaining each allowlist entry.

- [ ] **Step 4: Run audit**

Expected: pass.

---

## Task 5: Visual Regression Coverage

**Files:**
- Create or modify: `apps/web/tests/theme-mode.test.ts`
- Optional E2E/manual: Playwright/browser checks if the local app can run with seeded data.

- [ ] **Step 1: Add unit coverage for root class persistence**

Covered by Task 1.

- [ ] **Step 2: Add component coverage for high-risk views**

Add focused Vue tests for:
- `SettingsDrawer`: Display controls apply `.dark`.
- `WidgetFrame`: iframe srcdoc updates after `slaides:theme-changed`.
- `PresenterRail` or `Presenter.vue` shallow mount: right rail uses tokens and does not hardcode light background.

- [ ] **Step 3: Manual/browser checklist**

Run with API and web dev servers:

```sh
make api
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm run dev
```

Check:
- Signin page in light/dark.
- Workspace cards and settings drawer in light/dark.
- Editor left sidebar, slide canvas, right WidgetCollection Chat/Props/Code/Note in light/dark.
- Presenter deck slide, poll slide, open-question slide, random-audience slide in light/dark.
- Audience view in light/dark.
- Transcript view in light/dark.
- A generated widget iframe and widget thumbnail after switching theme while mounted.

---

## Verification Commands

Run:

```sh
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm test -- --run
PATH="/opt/homebrew/bin:$PATH" cd apps/web && npm run build
git diff --check
```

Backend tests are not required unless the implementation adds backend persistence. If the plan changes to workspace/server-side preference persistence, add API tests and migration verification.

---

## Self-Review

- Spec coverage: covers switch UI, persistence, root class application, widget iframe refresh, color literals, high-risk visual surfaces.
- Placeholder scan: no intentional “TBD” or unbounded “fix styles” tasks; every task names files and verification.
- Type consistency: `ThemeMode = "light" | "dark" | "system"` is used consistently by composable and settings controls.
- Scope control: no backend migration; display setting is device-local unless product later requires workspace/account sync.
