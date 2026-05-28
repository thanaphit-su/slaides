/**
 * Preview-iframe handshake.
 *
 * When the editor's preview tab embeds /audience/:sessionId or
 * /present/:sessionId in an iframe, that child page can't reach the parent's
 * sessionStorage (sessionStorage is scoped per browsing context). We don't
 * want to thread a guest token through the URL — that ends up in browser
 * history, server logs, and the Referer header on outbound requests from the
 * widget iframes.
 *
 * Instead the child posts `preview.ready` to its parent immediately on mount.
 * If the parent is a preview harness it replies with `preview.auth`, carrying
 * the guest token (or, for the presenter, just the inspector-mode flag).
 * The child keeps that guest in memory and threads it through its normal mount
 * flow. Do not store preview guests under the production sessionStorage key:
 * same-origin preview iframes share that key and would collapse all fake
 * audience tiles into whichever token was written last.
 */

import type { GuestJoinResponse } from "@/api/types";

const HANDSHAKE_TIMEOUT_MS = 1500;

export interface PreviewAuthMessage {
  slaides: true;
  type: "preview.auth";
  sessionId: string;
  role: "audience" | "presenter";
  inspect: boolean;
  // Audience tiles get a fake guest token; the presenter tile leaves this null
  // and uses the parent's localStorage-backed user auth (same-origin iframes
  // share localStorage so the user token is already visible).
  guest?: GuestJoinResponse | null;
}

export interface PreviewNavigateMessage {
  slaides: true;
  type: "preview.goto";
  slideIndex: number;
}

export interface PreviewInspectMessage {
  slaides: true;
  type: "preview.inspect";
  on: boolean;
}

export interface PreviewPickMessage {
  slaides: true;
  type: "preview.pick";
  payload: {
    selector: string;
    tag: string;
    classes: string[];
    text: string;
  };
}

export type PreviewMessage =
  | PreviewAuthMessage
  | PreviewNavigateMessage
  | PreviewInspectMessage
  | PreviewPickMessage;

/**
 * Result returned to the child page after the handshake. Caller uses
 * `isPreview` to decide whether to engage preview-mode behaviour
 * (suppress the keyboard handler hijack, listen for nav messages, etc).
 */
export interface PreviewHandshakeResult {
  isPreview: boolean;
  inspect: boolean;
  guest: GuestJoinResponse | null;
}

/**
 * Called from Audience.vue / Presenter.vue at the top of `onMounted` BEFORE
 * the normal join/auth flow. Resolves once the handshake completes or times
 * out. On timeout, returns `{ isPreview: false, inspect: false, guest: null }`
 * and the caller proceeds with the production flow.
 */
export async function maybeReceivePreviewAuth(
  sessionId: string,
): Promise<PreviewHandshakeResult> {
  if (typeof window === "undefined" || window.parent === window) {
    return { isPreview: false, inspect: false, guest: null };
  }
  return new Promise((resolve) => {
    let settled = false;
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || data.slaides !== true || data.type !== "preview.auth") return;
      if (data.sessionId !== sessionId) return;
      window.removeEventListener("message", onMessage);
      const guest = data.guest ? (data.guest as GuestJoinResponse) : null;
      // Set a window-scoped flag so WidgetFrame instances mounted later know
      // they're inside the preview tab and should bake the inspector script
      // into their srcdoc. Production audience widgets never see this flag.
      (window as unknown as { __slaides_preview?: boolean }).__slaides_preview = true;
      settled = true;
      resolve({ isPreview: true, inspect: !!data.inspect, guest });
    };
    window.addEventListener("message", onMessage);
    // Signal readiness to the parent — the parent waits for this before
    // sending preview.auth, so a missing reply means we're not inside a
    // preview harness and should fall through to the normal flow.
    try {
      window.parent.postMessage(
        { slaides: true, type: "preview.ready", sessionId },
        "*",
      );
    } catch {
      // Cross-origin parents will throw on postMessage; preview is same-origin
      // by definition so this only fires in pathological cases.
    }
    window.setTimeout(() => {
      if (settled) return;
      window.removeEventListener("message", onMessage);
      resolve({ isPreview: false, inspect: false, guest: null });
    }, HANDSHAKE_TIMEOUT_MS);
  });
}
