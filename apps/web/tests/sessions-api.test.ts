import { afterEach, describe, expect, it, vi } from "vitest";
import { sessionsApi } from "../src/api/sessions";

describe("sessionsApi mirror endpoints", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches a presenter mirror link", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ url: "/mirror/sess-1?token=t", token: "t", access_mode: "link" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const link = await sessionsApi.mirrorLink("sess-1");

    expect(link.url).toBe("/mirror/sess-1?token=t");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/sessions/sess-1/mirror-link");
  });

  it("encodes the mirror snapshot token when present", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          id: "sess-1",
          deck_id: "deck-1",
          deck_title: "Mirror",
          started_at: "2026-06-06T00:00:00Z",
          ended_at: null,
          current_slide_id: null,
          sections: [],
          slides: [],
          session_slides: [],
          placement_states: [],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await sessionsApi.mirrorSnapshot("sess-1", "tok en+/");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/sessions/sess-1/mirror?token=tok%20en%2B%2F",
    );
  });
});
