import { computed, shallowRef } from "vue";

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

function onSystemThemeChange(event: MediaQueryListEvent): void {
  systemDark.value = event.matches;
  if (mode.value === "system") applyTheme();
}

function ensureMediaListener(): void {
  if (typeof window === "undefined" || listenerAttached) return;
  mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)") || null;
  systemDark.value = !!mediaQuery?.matches;
  mediaQuery?.addEventListener("change", onSystemThemeChange);
  listenerAttached = true;
}

export function useThemeMode() {
  mode.value = readStoredMode();
  ensureMediaListener();
  applyTheme();

  function setMode(next: ThemeMode): void {
    mode.value = next;
    localStorage.setItem(THEME_MODE_STORAGE_KEY, next);
    applyTheme();
  }

  return {
    mode,
    resolvedMode: computed(resolvedModeValue),
    setMode,
  };
}
