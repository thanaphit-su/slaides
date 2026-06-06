const SESSION_CODE_PATTERN = /^SLD-[A-Z0-9]{4}-[A-Z0-9]{2}$/;

export function normalizeJoinCode(raw: string): string {
  const value = raw.trim();
  if (!value) return "";

  const upper = value.toUpperCase();
  if (SESSION_CODE_PATTERN.test(upper)) return upper;

  try {
    const url = new URL(value);
    const lastSegment = decodeURIComponent(url.pathname.split("/").filter(Boolean).at(-1) || "");
    const candidate = lastSegment.trim().toUpperCase();
    if (SESSION_CODE_PATTERN.test(candidate)) return candidate;
  } catch {
    // Not a URL; fall through to a tolerant search.
  }

  const found = upper.match(/SLD-[A-Z0-9]{4}-[A-Z0-9]{2}/);
  return found?.[0] ?? upper;
}
