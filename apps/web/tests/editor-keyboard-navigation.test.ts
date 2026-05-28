import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import type { Deck, Slide } from "@/api/types";
import Editor from "@/pages/Editor.vue";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/api/decks", () => ({
  decksApi: {
    get: vi.fn(),
    patch: vi.fn(),
    exportDeck: vi.fn(),
    insertSlide: vi.fn(),
    updateSlide: vi.fn(),
    deleteSlide: vi.fn(),
    reorderSlides: vi.fn(),
  },
  sectionsApi: {
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  },
}));

vi.mock("@/api/sessions", () => ({
  sessionsApi: {
    active: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock("@/api/widgets", () => ({
  widgetsApi: {
    get: vi.fn(),
    attachToSlide: vi.fn(),
    detachFromSlide: vi.fn(),
  },
}));

function slide(overrides: Partial<Slide>): Slide {
  return {
    id: "slide-a",
    deck_id: "deck-1",
    section_id: "section-1",
    position: 0,
    kicker: null,
    markdown: "# Slide",
    updated_at: "2026-05-22T00:00:00Z",
    widgets: [],
    ...overrides,
  };
}

function deck(): Deck {
  return {
    id: "deck-1",
    title: "Deck",
    subtitle: null,
    cover: null,
    manifest: {},
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    sections: [{ id: "section-1", title: "Section", position: 0 }],
    slides: [
      slide({ id: "slide-a", position: 0, markdown: "# A" }),
      slide({ id: "slide-b", position: 1, markdown: "# B" }),
    ],
  };
}

function mountEditor() {
  return mount(Editor, {
    props: { deckId: "deck-1" },
    global: {
      stubs: {
        Wordmark: true,
        Icon: true,
        SidebarOpen: true,
        SidebarCollapsed: true,
        SlideCanvas: {
          props: ["slideId"],
          template: '<div data-testid="editor-slide">{{ slideId }}</div>',
        },
        SlideStepper: true,
        AddSlideRibbon: true,
        AddWidgetRibbon: true,
        WidgetCollection: true,
        SettingsDrawer: true,
        InterpretPopover: true,
        ConfirmDialog: true,
      },
    },
  });
}

describe("editor keyboard navigation", () => {
  let wrapper: VueWrapper | null = null;

  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(decksApi.get).mockResolvedValue(deck());
    vi.mocked(sessionsApi.active).mockResolvedValue(null);
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  it("selects previous and next slides with arrow keys", async () => {
    wrapper = mountEditor();
    await flushPromises();

    expect(wrapper.get('[data-testid="editor-slide"]').text()).toBe("slide-a");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    await flushPromises();

    expect(wrapper.get('[data-testid="editor-slide"]').text()).toBe("slide-b");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }));
    await flushPromises();

    expect(wrapper.get('[data-testid="editor-slide"]').text()).toBe("slide-a");
  });

  it("does not change slides while an editable control has focus", async () => {
    wrapper = mountEditor();
    await flushPromises();

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await flushPromises();

    expect(wrapper.get('[data-testid="editor-slide"]').text()).toBe("slide-a");
    input.remove();
  });
});
