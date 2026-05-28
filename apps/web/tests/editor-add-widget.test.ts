import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import { widgetsApi } from "@/api/widgets";
import type { Deck, Slide, Widget, WidgetSummary } from "@/api/types";
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
    list: vi.fn(async () => []),
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
    markdown: "# A",
    updated_at: "2026-05-22T00:00:00Z",
    widgets: [],
    ...overrides,
  };
}

function emptyDeck(): Deck {
  return {
    id: "deck-1",
    title: "Deck",
    subtitle: null,
    cover: null,
    manifest: {},
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    sections: [{ id: "section-1", title: "Section", position: 0 }],
    slides: [slide({ id: "slide-a", position: 0, markdown: "# A" })],
  };
}

function deckWithWidget(widget: Widget): Deck {
  return {
    ...emptyDeck(),
    slides: [
      slide({
        id: "slide-a",
        position: 0,
        markdown: "# A\n\n{{widget:poll-abcd1234}}",
        widgets: [
          {
            placement_id: "poll-abcd1234",
            widget_id: widget.id,
            revision_id: null,
            kind: widget.kind,
            name: widget.name,
            props: {},
          },
        ],
      }),
    ],
  };
}

// Spy stub of SlideCanvas: records the most recent value of `widgetRev` so we
// can assert the editor bumped it after the widget body landed in the store
// cache.
const slideCanvasPaint = vi.fn<(args: { rev: number; widgetCount: number }) => void>();
function makeSlideCanvasStub() {
  slideCanvasPaint.mockReset();
  return {
    props: ["slideId", "markdown", "widgets", "widgetRev", "getWidget"],
    template: '<div data-testid="editor-slide">{{ slideId }}</div>',
    mounted(this: { slideId: string; widgetRev: number; widgets: unknown[] }) {
      slideCanvasPaint({ rev: this.widgetRev, widgetCount: this.widgets.length });
    },
    updated(this: { widgetRev: number; widgets: unknown[] }) {
      slideCanvasPaint({ rev: this.widgetRev, widgetCount: this.widgets.length });
    },
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
        SlideCanvas: makeSlideCanvasStub(),
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

describe("Editor — adding a widget repaints the slide without a manual refresh", () => {
  let wrapper: VueWrapper | null = null;

  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(sessionsApi.active).mockResolvedValue(null);
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  it("bumps widgetRev so SlideCanvas repaints with the cached widget body after attach", async () => {
    const widget: Widget = {
      id: "widget-new",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Generated poll",
      kind: "poll",
      description: null,
      html: "<section>poll</section>",
      js: null,
      css: null,
      props_schema: {},
      tags: [],
      version: "v0.1",
      behavior: { kind: "quiet" },
    };

    vi.mocked(decksApi.get)
      .mockResolvedValueOnce(emptyDeck()) // initial editor load
      .mockResolvedValueOnce(deckWithWidget(widget)); // after attach
    vi.mocked(widgetsApi.attachToSlide).mockResolvedValue({
      placement_id: "poll-abcd1234",
      widget_id: widget.id,
      revision_id: null,
      kind: widget.kind,
      name: widget.name,
      props: {},
    });
    vi.mocked(widgetsApi.get).mockResolvedValue(widget);

    wrapper = mountEditor();
    await flushPromises();

    // After the initial load, capture the starting rev that SlideCanvas saw.
    const initialPaint = slideCanvasPaint.mock.calls.at(-1)?.[0];
    expect(initialPaint).toBeTruthy();
    const initialRev = initialPaint!.rev;
    expect(initialPaint!.widgetCount).toBe(0);

    // Trigger the same path the WidgetCollection "Add to slide" button takes.
    const summary: WidgetSummary = {
      id: widget.id,
      deck_id: widget.deck_id,
      derived_from_id: widget.derived_from_id,
      name: widget.name,
      kind: widget.kind,
      description: widget.description,
      tags: widget.tags,
      version: widget.version,
      behavior: widget.behavior,
    };
    await (wrapper.vm as unknown as { onPickWidget: (w: WidgetSummary) => Promise<void> }).onPickWidget(summary);
    await flushPromises();

    const finalPaint = slideCanvasPaint.mock.calls.at(-1)?.[0];
    expect(finalPaint).toBeTruthy();
    // The slide now carries one widget placement.
    expect(finalPaint!.widgetCount).toBe(1);
    // And widgetRev advanced — without this bump SlideCanvas would have
    // painted the placeholder before the widget body was cached and never
    // repainted, which is the "blank until refresh" bug.
    expect(finalPaint!.rev).toBeGreaterThan(initialRev);
  });
});
