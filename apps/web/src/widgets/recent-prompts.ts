const KEY = "slaides:recent-widget-prompts:v1";
const MAX = 5;

export function loadRecentPrompts(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr)
      ? arr
          .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
          .slice(0, MAX)
      : [];
  } catch {
    return [];
  }
}

export function pushRecentPrompt(text: string): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  const current = loadRecentPrompts().filter((p) => p !== trimmed);
  current.unshift(trimmed);
  try {
    localStorage.setItem(KEY, JSON.stringify(current.slice(0, MAX)));
  } catch {
    // best effort; storage may be full or unavailable
  }
}

export const RECENT_PROMPTS_KEY = KEY;
export const RECENT_PROMPTS_MAX = MAX;
