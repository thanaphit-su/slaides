import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import Mirror from "../src/pages/Mirror.vue";
import { sessionsApi } from "../src/api/sessions";
import { widgetsApi } from "../src/api/widgets";
import { THEME_MODE_STORAGE_KEY } from "../src/theme/useThemeMode";
import type { MirrorSessionSnapshot } from "../src/api/types";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState = 1;
  onopen: ((ev: any) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.({}));
  }
  send() {}
  close() {
    this.onclose?.();
  }
}
(MockWebSocket as any).OPEN = 1;

const snapshot: MirrorSessionSnapshot = {
  id: "sess-1",
  deck_id: "deck-1",
  deck_title: "Mirror deck",
  started_at: "2026-06-06T00:00:00Z",
  ended_at: null,
  current_slide_id: "slide-1",
  sections: [],
  slides: [
    {
      id: "slide-1",
      deck_id: "deck-1",
      section_id: null,
      position: 0,
      kicker: null,
      markdown: "# Public slide",
      updated_at: "2026-06-06T00:00:00Z",
      widgets: [],
    },
  ],
  session_slides: [],
  placement_states: [],
};

describe("Mirror page", () => {
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    document.documentElement.classList.remove("dark", "light");
    originalWS = globalThis.WebSocket;
    // @ts-expect-error mock
    globalThis.WebSocket = MockWebSocket;
    MockWebSocket.instances = [];
    vi.spyOn(sessionsApi, "mirrorSnapshot").mockResolvedValue(structuredClone(snapshot));
    vi.spyOn(widgetsApi, "getAs").mockRejectedValue(new Error("guest widget endpoint should not be used"));
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    vi.restoreAllMocks();
    localStorage.clear();
    document.documentElement.classList.remove("dark", "light");
  });

  it("renders the current slide without audience or presenter controls", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/mirror/:sessionId", name: "mirror", component: Mirror, props: true },
        { path: "/signin", name: "signin", component: { template: "<div />" } },
      ],
    });
    await router.push("/mirror/sess-1?token=mirror-token");
    await router.isReady();

    const wrapper = mount(Mirror, {
      props: { sessionId: "sess-1" },
      global: {
        plugins: [router],
        stubs: {
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="mirror-slide">{{ slide.markdown }}</div>',
          },
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          Wordmark: true,
        },
      },
    });
    await flushPromises();

    expect(sessionsApi.mirrorSnapshot).toHaveBeenCalledWith("sess-1", "mirror-token");
    expect(MockWebSocket.instances[0].url).toContain("role=mirror");
    expect(wrapper.find('[data-testid="mirror-slide"]').text()).toContain("# Public slide");
    expect(wrapper.find('[data-testid="audience-stepper"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="audience-raise-question-fab"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Presenter controls");
  });

  it("exposes the shared theme switch from the avatar menu", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/mirror/:sessionId", name: "mirror", component: Mirror, props: true },
        { path: "/signin", name: "signin", component: { template: "<div />" } },
      ],
    });
    await router.push("/mirror/sess-1?token=mirror-token");
    await router.isReady();

    const wrapper = mount(Mirror, {
      props: { sessionId: "sess-1" },
      global: {
        plugins: [router],
        stubs: {
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="mirror-slide">{{ slide.markdown }}</div>',
          },
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          Wordmark: true,
        },
      },
    });
    await flushPromises();

    await wrapper.get('[data-testid="account-avatar-button"]').trigger("click");
    await wrapper.get('[data-testid="account-theme-dark"]').trigger("click");

    expect(localStorage.getItem(THEME_MODE_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("does not fetch deck-slide widgets with the mirror token when embedded revisions are present", async () => {
    const withWidget = structuredClone(snapshot);
    withWidget.slides[0].markdown = "{{widget:embed-1}}";
    withWidget.slides[0].widgets = [
      {
        placement_id: "embed-1",
        widget_id: "widget-1",
        revision_id: "rev-1",
        kind: "custom",
        name: "Embedded widget",
        props: {},
        revision: {
          id: "rev-1",
          widget_id: "widget-1",
          version_number: 1,
          html: "<section>Embedded mirror widget</section>",
          js: null,
          css: null,
          props_schema: {},
          example_props: {},
          behavior: { kind: "quiet" },
          ai_spec: {},
          created_reason: null,
        },
      },
    ];
    vi.mocked(sessionsApi.mirrorSnapshot).mockResolvedValueOnce(withWidget);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/mirror/:sessionId", name: "mirror", component: Mirror, props: true },
        { path: "/signin", name: "signin", component: { template: "<div />" } },
      ],
    });
    await router.push("/mirror/sess-1?token=mirror-token");
    await router.isReady();

    mount(Mirror, {
      props: { sessionId: "sess-1" },
      global: {
        plugins: [router],
        stubs: {
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="mirror-slide">{{ slide.markdown }}</div>',
          },
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          Wordmark: true,
        },
      },
    });
    await flushPromises();

    expect(widgetsApi.getAs).not.toHaveBeenCalled();
  });
});
