import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useEditorStore } from "../src/stores/editor";
import { decksApi } from "@/api/decks";
import type { Deck, Slide } from "../src/api/types";

vi.mock("@/api/decks", () => ({
  decksApi: {
    get: vi.fn(),
    insertSlide: vi.fn(),
    updateSlideNotes: vi.fn(),
  },
  sectionsApi: {
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  },
}));

vi.mock("@/api/widgets", () => ({
  widgetsApi: {
    attachToSlide: vi.fn(),
    detachFromSlide: vi.fn(),
  },
}));

function slide(overrides: Partial<Slide>): Slide {
  return {
    id: "slide-1",
    deck_id: "deck-1",
    section_id: null,
    position: 0,
    kicker: null,
    markdown: "",
    updated_at: "2026-05-20T00:00:00Z",
    presenter_notes: null,
    widgets: [],
    ...overrides,
  };
}

function deck(overrides: Partial<Deck> = {}): Deck {
  return {
    id: "deck-1",
    title: "Deck",
    subtitle: null,
    cover: null,
    manifest: {},
    created_at: "2026-05-20T00:00:00Z",
    updated_at: "2026-05-20T00:00:00Z",
    sections: [
      { id: "section-a", title: "A", position: 0 },
      { id: "section-b", title: "B", position: 1 },
      { id: "section-c", title: "C", position: 2 },
    ],
    slides: [
      slide({ id: "slide-a", section_id: "section-a", position: 0, markdown: "# A" }),
      slide({ id: "slide-c", section_id: "section-c", position: 1, markdown: "# C" }),
    ],
    mirror_access: { mode: "owner", allowed_emails: [] },
    ...overrides,
  };
}

describe("editor store section slide insertion", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(decksApi.get).mockReset();
    vi.mocked(decksApi.insertSlide).mockReset();
    vi.mocked(decksApi.updateSlideNotes).mockReset();
  });

  it("inserts a slide into an empty section before the next section's slides", async () => {
    const store = useEditorStore();
    const original = deck();
    const inserted = slide({ id: "slide-b", section_id: "section-b", position: 1 });
    const reloaded = deck({
      slides: [
        original.slides[0],
        inserted,
        slide({ id: "slide-c", section_id: "section-c", position: 2, markdown: "# C" }),
      ],
    });

    store.deck = original;
    vi.mocked(decksApi.insertSlide).mockResolvedValue(inserted);
    vi.mocked(decksApi.get).mockResolvedValue(reloaded);

    await store.insertSlideInSection("section-b");

    expect(decksApi.insertSlide).toHaveBeenCalledWith("deck-1", 1, "", "section-b");
    expect(store.activeSlideId).toBe("slide-b");
    expect(store.deck?.slides.map((s) => s.id)).toEqual(["slide-a", "slide-b", "slide-c"]);
  });

  it("patches slide presenter notes and updates the active slide", async () => {
    const store = useEditorStore();
    store.deck = deck({
      slides: [slide({ id: "slide-a", presenter_notes: null })],
    });
    vi.mocked(decksApi.updateSlideNotes).mockResolvedValue(
      slide({ id: "slide-a", presenter_notes: "Slow down on the demo." }),
    );

    await store.patchSlideNotes("slide-a", "Slow down on the demo.");

    expect(decksApi.updateSlideNotes).toHaveBeenCalledWith(
      "deck-1",
      "slide-a",
      "Slow down on the demo.",
    );
    expect(store.deck?.slides[0].presenter_notes).toBe("Slow down on the demo.");
  });
});
