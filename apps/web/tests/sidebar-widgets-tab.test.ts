import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import SidebarOpen from "../src/components/SidebarOpen.vue";
import type { Deck, Widget, WidgetSummary } from "../src/api/types";

vi.mock("../src/api/widgets", () => ({
  widgetsApi: {
    list: vi.fn(),
    listForDeck: vi.fn(async () => []),
    get: vi.fn(),
    remove: vi.fn(),
  },
}));

import { widgetsApi } from "../src/api/widgets";
import { useWidgetsStore } from "../src/stores/widgets";

const apiList = vi.mocked(widgetsApi.list);
const apiGet = vi.mocked(widgetsApi.get);
const apiRemove = vi.mocked(widgetsApi.remove);

function fakeSummary(id: string, deckId: string, name: string): WidgetSummary {
  return {
    id,
    deck_id: deckId,
    derived_from_id: null,
    name,
    kind: "poll",
    description: "x",
    tags: [],
    version: "v0.1",
    behavior: { kind: "quiet" },
  };
}

function fakeWidget(id: string, deckId: string, name: string): Widget {
  return {
    id,
    deck_id: deckId,
    derived_from_id: null,
    name,
    kind: "poll",
    description: "x",
    html: `<section>${name}</section>`,
    js: "",
    css: "",
    props_schema: {},
    tags: [],
    version: "v0.1",
    behavior: { kind: "quiet" },
  } as Widget;
}

const deck: Deck = {
  id: "deck-A",
  workspace_id: "ws-1",
  owner_id: "u-1",
  title: "Live deck",
  subtitle: "",
  cover: null,
  manifest: {},
  slides: [],
  sections: [],
  created_at: "",
  updated_at: "",
} as unknown as Deck;

beforeEach(() => {
  setActivePinia(createPinia());
  apiList.mockReset();
  apiGet.mockReset();
  apiRemove.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SidebarOpen — widgets tab", () => {
  it("renders sections / widgets / theme rail buttons", () => {
    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "sections" },
    });
    // VSCode-style rail: tabs are icon-only buttons identified by their
    // `title` (and matching aria-label) for hover tooltips.
    const titles = wrapper
      .findAll(".sidebar-rail-btn")
      .map((b) => b.attributes("title"));
    expect(titles).toEqual(["Sections", "Widgets", "Theme", "Collapse sidebar"]);
  });

  it("splits widgets into 'this deck' and 'other decks' sections", async () => {
    apiList.mockResolvedValue([
      fakeSummary("w-1", "deck-A", "Local"),
      fakeSummary("w-2", "deck-B", "From another"),
    ]);
    apiGet.mockImplementation(async (id: string) =>
      fakeWidget(id, id === "w-1" ? "deck-A" : "deck-B", `Widget ${id}`),
    );

    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "widgets" },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    const thisDeckSection = wrapper.find('[data-testid="widgets-section-this-deck"]');
    const otherDecksSection = wrapper.find('[data-testid="widgets-section-other-decks"]');
    expect(thisDeckSection.exists()).toBe(true);
    expect(otherDecksSection.exists()).toBe(true);

    expect(thisDeckSection.findAll('[data-testid="widget-thumbnail"]').length).toBe(1);
    expect(otherDecksSection.findAll('[data-testid="widget-thumbnail"]').length).toBe(1);

    // The other-deck card carries the new pill badge.
    expect(otherDecksSection.find(".widget-thumbnail-crossdeck").text()).toBe("OTHER DECK");
    // The this-deck card does not.
    expect(thisDeckSection.find(".widget-thumbnail-crossdeck").exists()).toBe(false);
  });

  it("loads cross-deck widgets and renders a thumbnail per widget", async () => {
    apiList.mockResolvedValue([
      fakeSummary("w-1", "deck-A", "Poll One"),
      fakeSummary("w-2", "deck-B", "Poll Two"),
    ]);
    apiGet.mockImplementation(async (id: string) => fakeWidget(id, id === "w-1" ? "deck-A" : "deck-B", `Widget ${id}`));

    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "widgets" },
    });
    // Let onMounted's loadWidgetsTab promise settle.
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(apiList).toHaveBeenCalledTimes(1);
    expect(apiGet).toHaveBeenCalledTimes(2);

    const thumbs = wrapper.findAll('[data-testid="widget-thumbnail"]');
    expect(thumbs.length).toBe(2);
  });

  it("filters the grid by the search query", async () => {
    apiList.mockResolvedValue([
      fakeSummary("w-1", "deck-A", "Poll One"),
      fakeSummary("w-2", "deck-B", "Word Cloud"),
    ]);
    apiGet.mockImplementation(async (id: string) => fakeWidget(id, "deck-A", id === "w-1" ? "Poll One" : "Word Cloud"));

    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "widgets" },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(wrapper.findAll('[data-testid="widget-thumbnail"]').length).toBe(2);

    const search = wrapper.find(".widgets-tab-search");
    await search.setValue("cloud");
    await nextTick();
    expect(wrapper.findAll('[data-testid="widget-thumbnail"]').length).toBe(1);
  });

  it("emits collapse (not set-tab) when the active rail icon is re-clicked", async () => {
    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "widgets" },
    });
    const widgetsBtn = wrapper
      .findAll(".sidebar-rail-btn")
      .find((b) => b.attributes("title") === "Widgets")!;
    await widgetsBtn.trigger("click");
    expect(wrapper.emitted("set-tab")).toBeUndefined();
    expect(wrapper.emitted("collapse")).toBeTruthy();
  });

  it("deletes a widget through the confirmation modal and refreshes the list", async () => {
    apiList.mockResolvedValueOnce([
      fakeSummary("w-1", "deck-A", "Local"),
      fakeSummary("w-2", "deck-B", "From another"),
    ]);
    apiGet.mockImplementation(async (id: string) =>
      fakeWidget(id, id === "w-1" ? "deck-A" : "deck-B", `Widget ${id}`),
    );

    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "widgets" },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(wrapper.findAll('[data-testid="widget-thumbnail"]').length).toBe(2);

    apiRemove.mockResolvedValueOnce(undefined as unknown as void);
    apiList.mockResolvedValueOnce([fakeSummary("w-2", "deck-B", "From another")]);

    const deleteButtons = wrapper.findAll('[data-testid="widget-thumbnail-delete"]');
    expect(deleteButtons.length).toBe(2);
    await deleteButtons[0].trigger("click");
    await nextTick();

    const modal = wrapper.find('[data-testid="widget-delete-modal"]');
    expect(modal.exists()).toBe(true);

    const confirmBtn = modal.find("button.btn-danger");
    await confirmBtn.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(apiRemove).toHaveBeenCalledWith("w-1", { force: false });
    expect(wrapper.find('[data-testid="widget-delete-modal"]').exists()).toBe(false);
    expect(wrapper.findAll('[data-testid="widget-thumbnail"]').length).toBe(1);
  });

  it("emits set-tab when a rail button is clicked", async () => {
    const wrapper = mount(SidebarOpen, {
      props: { deck, activeSlideId: null, tab: "sections" },
    });
    const widgetsBtn = wrapper
      .findAll(".sidebar-rail-btn")
      .find((b) => b.attributes("title") === "Widgets")!;
    expect(widgetsBtn).toBeTruthy();
    await widgetsBtn.trigger("click");
    const emitted = wrapper.emitted("set-tab");
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual(["widgets"]);
  });
});

// Suppress unused-store warning from useWidgetsStore import being needed
// elsewhere; required to keep the active pinia bound in this test file.
void useWidgetsStore;
