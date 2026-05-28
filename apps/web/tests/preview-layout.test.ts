import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import Preview from "../src/pages/Preview.vue";
import { sessionsApi } from "../src/api/sessions";

vi.mock("../src/api/decks", () => ({
  decksApi: {
    get: vi.fn(async () => ({
      id: "d-1",
      title: "Test deck",
      subtitle: null,
      manifest: {},
      sections: [],
      slides: [
        {
          id: "s-1",
          deck_id: "d-1",
          section_id: null,
          position: 0,
          kicker: null,
          markdown: "# slide one\n",
          updated_at: "2026-01-01T00:00:00Z",
          widgets: [],
        },
      ],
    })),
  },
}));

vi.mock("../src/api/sessions", () => ({
  sessionsApi: {
    createPreview: vi.fn(async () => ({
      session_id: "sess-1",
      code: "SLD-AAAA-AA",
      fake_guests: [
        { participant_id: "p-1", participant_ref: "ref-1", display_name: "Alice", token: "tok-1" },
        { participant_id: "p-2", participant_ref: "ref-2", display_name: "Bob", token: "tok-2" },
        { participant_id: "p-3", participant_ref: "ref-3", display_name: "Carol", token: "tok-3" },
      ],
    })),
    advance: vi.fn(async () => ({})),
    end: vi.fn(async () => ({})),
  },
}));

// WidgetCollection imports a lot of things; stub it out — the layout test
// doesn't care about its internals.
vi.mock("../src/components/WidgetCollection.vue", () => ({
  default: {
    name: "WidgetCollection",
    template: '<div data-testid="stub-widget-collection" />',
  },
}));

// ResizeObserver isn't available in happy-dom by default.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof FakeResizeObserver }).ResizeObserver =
  FakeResizeObserver;

function makeRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: "/decks/:deckId/preview", name: "deck-preview", component: { template: "<div />" } },
    ],
  });
}

beforeEach(() => {
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("Preview.vue meeting-app layout", () => {
  it("renders one thumbnail per tile (presenter + 3 audiences) after spin-up", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    const thumbs = wrapper.findAll(".preview-thumb");
    expect(thumbs).toHaveLength(4);
    const names = thumbs.map((t) => t.find(".preview-thumb-name").text());
    expect(names).toEqual(["Presenter", "Alice", "Bob", "Carol"]);
  });

  it("clamps the preview audience count to five before creating the session", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview?audience=8");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    expect(sessionsApi.createPreview).toHaveBeenCalledWith("d-1", 5);
    expect(wrapper.find(".preview-controls-count").text()).toBe("5");
    expect(wrapper.findAll(".preview-controls-group")[1].findAll("button")[1].attributes("disabled")).toBeDefined();
  });

  it("defaults to presenter active (ring on presenter thumb, chrome shows Presenter)", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    const presenterThumb = wrapper.find('[data-testid="preview-thumb-presenter"]');
    expect(presenterThumb.classes()).toContain("active");

    // Non-active thumbs do NOT have .active
    const aliceThumb = wrapper.find('[data-testid="preview-thumb-aud-ref-1"]');
    expect(aliceThumb.classes()).not.toContain("active");

    const chrome = wrapper.find('[data-testid="preview-stage-chrome"]');
    expect(chrome.text()).toContain("Presenter");
    expect(chrome.text()).toContain("PRESENTER");
  });

  it("clicking another thumb moves the active ring + updates stage chrome", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    await wrapper.find('[data-testid="preview-thumb-aud-ref-1"]').trigger("click");
    await flushPromises();

    expect(wrapper.find('[data-testid="preview-thumb-presenter"]').classes()).not.toContain("active");
    expect(wrapper.find('[data-testid="preview-thumb-aud-ref-1"]').classes()).toContain("active");

    const chrome = wrapper.find('[data-testid="preview-stage-chrome"]');
    expect(chrome.text()).toContain("Alice");
    expect(chrome.text()).toContain("AUDIENCE");
  });

  it("inactive thumbs get a click-shield; the active thumb does not", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    // 3 inactive thumbs → 3 shields. The active presenter thumb has none.
    expect(wrapper.findAll(".preview-thumb-shield")).toHaveLength(3);
    const presenter = wrapper.find('[data-testid="preview-thumb-presenter"]');
    expect(presenter.find(".preview-thumb-shield").exists()).toBe(false);
  });

  it("moves the right-aligned reset+inspect group via .preview-controls-group--right", async () => {
    const router = makeRouter();
    await router.push("/decks/d-1/preview");
    const wrapper = mount(Preview, {
      props: { deckId: "d-1" },
      global: { plugins: [router] },
    });
    await flushPromises();

    const rightGroup = wrapper.find(".preview-controls-group--right");
    expect(rightGroup.exists()).toBe(true);
    expect(rightGroup.text()).toContain("reset");
    expect(rightGroup.text()).toContain("inspect");
  });
});
