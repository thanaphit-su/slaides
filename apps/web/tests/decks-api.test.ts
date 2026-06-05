import { afterEach, describe, expect, it, vi } from "vitest";
import { decksApi } from "../src/api/decks";
import type { Slide } from "../src/api/types";

function slide(overrides: Partial<Slide> = {}): Slide {
  return {
    id: "slide-1",
    deck_id: "deck-1",
    section_id: "section-1",
    position: 0,
    kicker: null,
    markdown: "",
    updated_at: "2026-05-20T00:00:00Z",
    widgets: [],
    ...overrides,
  };
}

describe("decksApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("passes section_id when inserting a slide", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify(slide()), { status: 201 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await decksApi.insertSlide("deck-1", 0, "", "section-1");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      position: 0,
      markdown: "",
      section_id: "section-1",
    });
  });

  it("patches slide presenter notes without sending markdown", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify(slide({ presenter_notes: "Speaker cue" })), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await decksApi.updateSlideNotes("deck-1", "slide-1", "Speaker cue");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/decks/deck-1/slides/slide-1/notes");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({
      presenter_notes: "Speaker cue",
    });
  });
});
