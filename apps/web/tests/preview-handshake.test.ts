import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { maybeReceivePreviewAuth } from "../src/preview/handshake";

describe("maybeReceivePreviewAuth", () => {
  const originalParent = window.parent;

  beforeEach(() => {
    sessionStorage.clear();
    (window as unknown as { __slaides_preview?: boolean }).__slaides_preview = undefined;
  });

  afterEach(() => {
    Object.defineProperty(window, "parent", { configurable: true, value: originalParent });
  });

  it("returns isPreview=false immediately when not inside an iframe", async () => {
    // window.parent === window already (jsdom default for a top-level window).
    const result = await maybeReceivePreviewAuth("s-1");
    expect(result).toEqual({ isPreview: false, inspect: false, guest: null });
    expect((window as unknown as { __slaides_preview?: boolean }).__slaides_preview).toBeUndefined();
  });

  it("on preview.auth: returns the guest without writing the shared session token", async () => {
    // Pretend we are inside an iframe.
    Object.defineProperty(window, "parent", {
      configurable: true,
      value: { postMessage: vi.fn() },
    });

    const guest = {
      session_id: "s-1",
      participant_id: "p-1",
      participant_ref: "ref-1",
      token: "tok-1",
      display_name: "Alice",
      anon: false,
    };

    const pending = maybeReceivePreviewAuth("s-1");

    // Simulate the parent's reply.
    window.dispatchEvent(
      new MessageEvent("message", {
        data: {
          slaides: true,
          type: "preview.auth",
          sessionId: "s-1",
          role: "audience",
          inspect: true,
          guest,
        },
      }),
    );

    const result = await pending;
    expect(result).toEqual({ isPreview: true, inspect: true, guest });
    expect((window as unknown as { __slaides_preview?: boolean }).__slaides_preview).toBe(true);
    expect(sessionStorage.getItem("slaides:guest:s-1")).toBeNull();
  });

  it("ignores preview.auth for a different sessionId", async () => {
    Object.defineProperty(window, "parent", {
      configurable: true,
      value: { postMessage: vi.fn() },
    });
    vi.useFakeTimers();
    const pending = maybeReceivePreviewAuth("s-1");
    window.dispatchEvent(
      new MessageEvent("message", {
        data: { slaides: true, type: "preview.auth", sessionId: "OTHER", role: "audience", inspect: false },
      }),
    );
    // No matching reply → 1500ms timeout fires.
    vi.advanceTimersByTime(1500);
    const result = await pending;
    expect(result).toEqual({ isPreview: false, inspect: false, guest: null });
    vi.useRealTimers();
  });
});
