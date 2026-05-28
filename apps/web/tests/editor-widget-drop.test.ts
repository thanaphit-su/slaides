import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import { widgetsApi } from "@/api/widgets";
import type { Deck, Slide, Widget } from "@/api/types";
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
  sessionsApi: { active: vi.fn(), create: vi.fn() },
}));

vi.mock("@/api/widgets", () => ({
  widgetsApi: {
    list: vi.fn(async () => []),
    listForDeck: vi.fn(async () => []),
    get: vi.fn(),
    attachToSlide: vi.fn(),
    detachFromSlide: vi.fn(),
    copyIntoDeck: vi.fn(),
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

function mountEditor() {
  return mount(Editor, {
    props: { deckId: "deck-1" },
    global: {
      stubs: {
        Wordmark: true,
        Icon: true,
        SidebarOpen: true,
        SidebarCollapsed: true,
        SlideCanvas: true,
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

function fakeWidget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: "widget-x",
    deck_id: "deck-1",
    derived_from_id: null,
    name: "Poll",
    kind: "poll",
    description: null,
    html: "<section>poll</section>",
    js: null,
    css: null,
    props_schema: {},
    tags: [],
    version: "v0.1",
    behavior: { kind: "quiet" },
    ...overrides,
  } as Widget;
}

function dispatchDrop(wrapper: VueWrapper, payload: string | null) {
  const section = wrapper.find("section").element as HTMLElement;
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", {
    value: {
      types: payload ? ["application/x-slaides-widget"] : [],
      getData: (mime: string) =>
        mime === "application/x-slaides-widget" && payload ? payload : "",
    },
  });
  section.dispatchEvent(event);
}

beforeEach(() => {
  localStorage.clear();
  setActivePinia(createPinia());
  vi.clearAllMocks();
  vi.mocked(sessionsApi.active).mockResolvedValue(null);
});

let wrapper: VueWrapper | null = null;
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("Editor — drop widget onto slide canvas", () => {
  it("calls attachToSlide directly for a same-deck widget", async () => {
    const widget = fakeWidget({ deck_id: "deck-1" });
    vi.mocked(decksApi.get).mockResolvedValue(emptyDeck());
    vi.mocked(widgetsApi.list).mockResolvedValue([
      {
        id: widget.id,
        deck_id: widget.deck_id,
        derived_from_id: null,
        name: widget.name,
        kind: widget.kind,
        description: null,
        tags: [],
        version: widget.version,
        behavior: widget.behavior,
      },
    ]);
    vi.mocked(widgetsApi.get).mockResolvedValue(widget);
    vi.mocked(widgetsApi.attachToSlide).mockResolvedValue({
      placement_id: "poll-aaaa1111",
      widget_id: widget.id,
      revision_id: null,
      kind: widget.kind,
      name: widget.name,
      props: {},
    });

    wrapper = mountEditor();
    await flushPromises();

    // Prime the cross-deck list so the drop handler can resolve the
    // widget_id → summary lookup.
    const { useWidgetsStore } = await import("@/stores/widgets");
    const store = useWidgetsStore();
    await store.fetchCrossDeckList();

    dispatchDrop(wrapper, JSON.stringify({ widget_id: widget.id, deck_id: "deck-1" }));
    await flushPromises();

    expect(widgetsApi.copyIntoDeck).not.toHaveBeenCalled();
    expect(widgetsApi.attachToSlide).toHaveBeenCalledTimes(1);
    const [deckId, slideId, body] = vi.mocked(widgetsApi.attachToSlide).mock.calls[0];
    expect(deckId).toBe("deck-1");
    expect(slideId).toBe("slide-a");
    expect(body.widget_id).toBe(widget.id);
    expect(body.placement_id).toMatch(/^poll-[0-9a-f]+$/);
  });

  it("copies a cross-deck widget into this deck before attaching", async () => {
    const sourceWidget = fakeWidget({ id: "src-w", deck_id: "deck-OTHER" });
    const copied = fakeWidget({ id: "copy-w", deck_id: "deck-1", derived_from_id: "src-w" });

    vi.mocked(decksApi.get).mockResolvedValue(emptyDeck());
    vi.mocked(widgetsApi.list).mockResolvedValue([]);
    vi.mocked(widgetsApi.get).mockResolvedValue(sourceWidget);
    vi.mocked(widgetsApi.copyIntoDeck).mockResolvedValue(copied);
    vi.mocked(widgetsApi.attachToSlide).mockResolvedValue({
      placement_id: "poll-bbbb2222",
      widget_id: copied.id,
      revision_id: null,
      kind: copied.kind,
      name: copied.name,
      props: {},
    });

    wrapper = mountEditor();
    await flushPromises();

    dispatchDrop(wrapper, JSON.stringify({ widget_id: sourceWidget.id, deck_id: "deck-OTHER" }));
    await flushPromises();

    expect(widgetsApi.copyIntoDeck).toHaveBeenCalledTimes(1);
    expect(widgetsApi.copyIntoDeck).toHaveBeenCalledWith("deck-1", sourceWidget.id);
    expect(widgetsApi.attachToSlide).toHaveBeenCalledTimes(1);
    const [, , body] = vi.mocked(widgetsApi.attachToSlide).mock.calls[0];
    // The attach must use the COPY's id, not the source.
    expect(body.widget_id).toBe(copied.id);
  });

  it("detaches the existing widget before attaching the new one (replace)", async () => {
    const existingPlacementId = "old-placement-id";
    const existingWidgetId = "widget-old";
    const incoming = fakeWidget({ id: "widget-new", deck_id: "deck-1" });

    // Deck starts with a slide that already carries a widget.
    const seededDeck: Deck = {
      ...emptyDeck(),
      slides: [
        slide({
          id: "slide-a",
          position: 0,
          markdown: `# A\n\n{{widget:${existingPlacementId}}}`,
          widgets: [
            {
              placement_id: existingPlacementId,
              widget_id: existingWidgetId,
              revision_id: null,
              kind: "quiz",
              name: "Old",
              props: {},
            },
          ],
        }),
      ],
    };
    vi.mocked(decksApi.get).mockResolvedValue(seededDeck);
    vi.mocked(widgetsApi.list).mockResolvedValue([
      {
        id: incoming.id,
        deck_id: incoming.deck_id,
        derived_from_id: null,
        name: incoming.name,
        kind: incoming.kind,
        description: null,
        tags: [],
        version: incoming.version,
        behavior: incoming.behavior,
      },
    ]);
    vi.mocked(widgetsApi.get).mockResolvedValue(incoming);
    vi.mocked(widgetsApi.detachFromSlide).mockResolvedValue(undefined);
    vi.mocked(widgetsApi.attachToSlide).mockResolvedValue({
      placement_id: "poll-newxxxx",
      widget_id: incoming.id,
      revision_id: null,
      kind: incoming.kind,
      name: incoming.name,
      props: {},
    });

    wrapper = mountEditor();
    await flushPromises();
    const { useWidgetsStore } = await import("@/stores/widgets");
    await useWidgetsStore().fetchCrossDeckList();

    dispatchDrop(wrapper, JSON.stringify({ widget_id: incoming.id, deck_id: "deck-1" }));
    await flushPromises();

    expect(widgetsApi.detachFromSlide).toHaveBeenCalledTimes(1);
    expect(widgetsApi.detachFromSlide).toHaveBeenCalledWith("deck-1", "slide-a", existingPlacementId);
    expect(widgetsApi.attachToSlide).toHaveBeenCalledTimes(1);
    const [, , body] = vi.mocked(widgetsApi.attachToSlide).mock.calls[0];
    expect(body.widget_id).toBe(incoming.id);
  });

  it("reuses an existing local copy on repeated cross-deck drops (dedupe by lineage)", async () => {
    const sourceWidget = fakeWidget({ id: "src-w", deck_id: "deck-OTHER" });
    const existingCopySummary = {
      id: "copy-w",
      deck_id: "deck-1",
      derived_from_id: "src-w",
      name: "Source",
      kind: "poll",
      description: null,
      tags: [],
      version: "v0.1",
      behavior: { kind: "quiet" },
    };

    vi.mocked(decksApi.get).mockResolvedValue(emptyDeck());
    vi.mocked(widgetsApi.list).mockResolvedValue([sourceWidget as never]);
    vi.mocked(widgetsApi.listForDeck).mockResolvedValue([existingCopySummary as never]);
    vi.mocked(widgetsApi.get).mockResolvedValue(sourceWidget);
    vi.mocked(widgetsApi.attachToSlide).mockResolvedValue({
      placement_id: "poll-already1",
      widget_id: existingCopySummary.id,
      revision_id: null,
      kind: existingCopySummary.kind,
      name: existingCopySummary.name,
      props: {},
    });

    wrapper = mountEditor();
    await flushPromises();
    // Seed the store's deck-local summaries with the existing copy so the
    // onWidgetDrop handler's lineage lookup hits.
    const { useWidgetsStore } = await import("@/stores/widgets");
    const store = useWidgetsStore();
    await store.fetchListForDeck("deck-1");

    dispatchDrop(wrapper, JSON.stringify({ widget_id: sourceWidget.id, deck_id: "deck-OTHER" }));
    await flushPromises();

    // Crucial: copyIntoDeck must NOT fire a second time when a lineage
    // match already exists in the local deck.
    expect(widgetsApi.copyIntoDeck).not.toHaveBeenCalled();
    expect(widgetsApi.attachToSlide).toHaveBeenCalledTimes(1);
    const [, , body] = vi.mocked(widgetsApi.attachToSlide).mock.calls[0];
    expect(body.widget_id).toBe(existingCopySummary.id);
  });

  it("ignores drops without our custom MIME payload", async () => {
    vi.mocked(decksApi.get).mockResolvedValue(emptyDeck());

    wrapper = mountEditor();
    await flushPromises();

    dispatchDrop(wrapper, null);
    await flushPromises();

    expect(widgetsApi.attachToSlide).not.toHaveBeenCalled();
    expect(widgetsApi.copyIntoDeck).not.toHaveBeenCalled();
  });
});
