import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { nextTick } from "vue";
import WidgetCollection from "../src/components/WidgetCollection.vue";

const fixtureWidget = {
  id: "w-poll-1",
  deck_id: "deck-1",
  derived_from_id: null,
  name: "Poll",
  kind: "poll",
  description: "A four-option poll",
  tags: ["live"],
  version: "1.0.0",
  behavior: { kind: "quiet" as const },
};

vi.mock("../src/api/llm", () => ({
  llmApi: { completeText: vi.fn() },
}));
vi.mock("../src/api/workspace", () => ({
  workspaceApi: {
    get: vi.fn(async () => ({
      id: "ws-1",
      name: "Test",
      llm_base_url: "https://x",
      llm_model: "m-1",
      llm_caps: { widget_generate: true, inline_write: true, interpret: true },
      llm_models: [{ id: "m-1" }],
      llm_capability_models: { widget_generate: "m-1", inline_write: "m-1", interpret: "m-1" },
      llm_key_configured: true,
    })),
  },
}));

vi.mock("../src/api/widgets", () => ({
  widgetsApi: {
    list: vi.fn(async () => []),
    listForDeck: vi.fn(async () => [fixtureWidget]),
    get: vi.fn(async () => null),
    copyIntoDeck: vi.fn(async () => ({
      ...fixtureWidget,
      id: "w-poll-2",
      name: "Poll (copy)",
      derived_from_id: fixtureWidget.id,
    })),
    remove: vi.fn(async () => ({})),
  },
}));

import { widgetsApi } from "../src/api/widgets";

beforeEach(() => {
  setActivePinia(createPinia());
  vi.mocked(widgetsApi.copyIntoDeck).mockClear();
  vi.mocked(widgetsApi.listForDeck).mockClear();
});

describe("WidgetCollection — duplicate widget within the same deck", () => {
  it("calls widgetsApi.copyIntoDeck when the per-card duplicate button is clicked, then refreshes the deck list", async () => {
    const wrapper = mount(WidgetCollection, {
      props: { deckId: "deck-1" },
    });
    // Let onMounted promises settle (workspace + deck-list fetch).
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    // The first listForDeck call happens on mount; reset so we can isolate
    // the post-duplicate refresh.
    expect(widgetsApi.listForDeck).toHaveBeenCalled();
    vi.mocked(widgetsApi.listForDeck).mockClear();

    // Open the library popover by clicking the bottom-toolbar library button.
    const libraryToggle = wrapper.find(".widget-tool-library");
    expect(libraryToggle.exists()).toBe(true);
    await libraryToggle.trigger("click");
    await nextTick();

    // The fixture widget should be rendered as a popover row.
    const items = wrapper.findAll(".widget-popover-item");
    expect(items).toHaveLength(1);
    expect(items[0].text()).toContain("Poll");

    // Find the duplicate button (title prefix "Duplicate ...").
    const duplicateBtn = items[0].find('button[title^="Duplicate"]');
    expect(duplicateBtn.exists()).toBe(true);
    await duplicateBtn.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    // It calls copyIntoDeck with (deckId, sourceWidgetId) and then refreshes.
    expect(widgetsApi.copyIntoDeck).toHaveBeenCalledTimes(1);
    expect(widgetsApi.copyIntoDeck).toHaveBeenCalledWith("deck-1", "w-poll-1");
    expect(widgetsApi.listForDeck).toHaveBeenCalledWith("deck-1");
  });

  it("keeps the duplicate button distinct from the delete button (different titles, both with stop-propagation)", async () => {
    const wrapper = mount(WidgetCollection, {
      props: { deckId: "deck-1" },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await wrapper.find(".widget-tool-library").trigger("click");
    await nextTick();

    const item = wrapper.find(".widget-popover-item");
    const buttons = item.findAll("button");
    const titles = buttons.map((b) => b.attributes("title") || "");
    expect(titles).toContain("Duplicate Poll in this deck");
    expect(titles).toContain("Delete Poll");
  });
});
