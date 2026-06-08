/**
 * Widget iframe Content-Security-Policy.
 *
 * Widgets render in a `sandbox="allow-scripts allow-forms"` iframe with a null
 * origin, so they already have zero access to host cookies / storage / Pinia.
 * On top of that, this CSP governs what the widget can load over the network.
 *
 * By default it is fully locked down: only inline scripts/styles, `data:` fonts,
 * and `https:` images are permitted; `connect-src` is `'none'`. An admin can
 * widen it by adding trusted origins (e.g. a CDN) to the workspace allowlist —
 * those origins are appended to `script-src`, `style-src`, `font-src`, and
 * `connect-src` so widgets can pull libraries/styles/fonts and fetch from them.
 *
 * The allowlist lives in a module-level reactive ref rather than being threaded
 * through props, mirroring how `readHostTokens()` reads global host state. It is
 * populated by whichever context owns the workspace config:
 *   - the editor / settings drawer (authenticated `GET /workspace`)
 *   - the audience / presenter / mirror session snapshot
 */
import { ref } from "vue";

const allowedCdnHosts = ref<string[]>([]);

/** Replace the active allowlist. Pass already-normalised origins (the backend
 *  normalises to `scheme://host[:port]`); empties out on invalid input. */
export function setAllowedCdnHosts(hosts: string[] | null | undefined): void {
  const next = Array.isArray(hosts)
    ? hosts.filter((h): h is string => typeof h === "string" && h.trim().length > 0)
    : [];
  // Avoid a needless reload of every mounted widget iframe when nothing changed.
  if (next.length === allowedCdnHosts.value.length && next.every((h, i) => h === allowedCdnHosts.value[i])) {
    return;
  }
  allowedCdnHosts.value = next;
}

export function getAllowedCdnHosts(): string[] {
  return allowedCdnHosts.value;
}

/**
 * Build the widget iframe CSP. Reading `allowedCdnHosts.value` makes any caller
 * inside a Vue computed reactive to allowlist changes.
 *
 * `img-src data: https:` is intentionally permissive (instructor-supplied image
 * URLs, e.g. the Carousel) and is unaffected by the allowlist.
 */
export function buildWidgetCsp(): string {
  const hosts = allowedCdnHosts.value;
  const extra = hosts.length ? " " + hosts.join(" ") : "";
  const connectSrc = hosts.length ? hosts.join(" ") : "'none'";
  return (
    "default-src 'none'; " +
    `style-src 'unsafe-inline'${extra}; ` +
    `script-src 'unsafe-inline'${extra}; ` +
    "img-src data: https:; " +
    `font-src data:${extra}; ` +
    `connect-src ${connectSrc}; ` +
    "base-uri 'none'; " +
    "form-action 'none'; " +
    "frame-ancestors 'self';"
  );
}
