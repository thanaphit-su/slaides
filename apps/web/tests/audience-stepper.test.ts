import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sessionsApi } from "@/api/sessions";
import { widgetsApi } from "@/api/widgets";
import type { SessionSnapshot } from "@/api/types";
import Audience from "@/pages/Audience.vue";
import { saveGuestToken } from "@/stores/session";
import { useAuthStore } from "@/stores/auth";

const replace = vi.fn();

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState = 0;
  onopen: ((ev: any) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];

  constructor() {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = 1;
      this.onopen?.({});
    });
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}
(MockWebSocket as any).OPEN = 1;

enableAutoUnmount(afterEach);

const snapshot: SessionSnapshot = {
  id: "sess-1",
  code: "SLD-TEST",
  deck_id: "deck-1",
  deck_title: "Test deck",
  owner_id: "owner-1",
  started_at: new Date().toISOString(),
  ended_at: null,
  current_slide_id: "slide-2",
  sections: [],
  slides: [
    {
      id: "slide-1",
      deck_id: "deck-1",
      section_id: null,
      position: 0,
      kicker: null,
      markdown: "# One",
      updated_at: new Date().toISOString(),
      widgets: [],
    },
    {
      id: "slide-2",
      deck_id: "deck-1",
      section_id: null,
      position: 1,
      kicker: null,
      markdown: "# Two",
      updated_at: new Date().toISOString(),
      widgets: [],
    },
    {
      id: "slide-3",
      deck_id: "deck-1",
      section_id: null,
      position: 2,
      kicker: null,
      markdown: "# Three",
      updated_at: new Date().toISOString(),
      widgets: [],
    },
  ],
  session_slides: [],
  questions: [],
  audience_count: 4,
};

vi.mock("vue-router", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/api/sessions", () => ({
  sessionsApi: {
    audienceSnapshot: vi.fn(),
  },
}));

vi.mock("@/api/widgets", () => ({
  widgetsApi: {
    getAs: vi.fn(),
  },
}));

describe("audience slide stepper", () => {
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    originalWS = globalThis.WebSocket;
    // @ts-expect-error test WebSocket shim
    globalThis.WebSocket = MockWebSocket;
    MockWebSocket.instances = [];
    vi.mocked(sessionsApi.audienceSnapshot).mockResolvedValue(structuredClone(snapshot));
    vi.mocked(widgetsApi.getAs).mockResolvedValue({
      id: "w1",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Widget",
      kind: "custom",
      description: null,
      html: "",
      js: null,
      css: null,
      props_schema: {},
      tags: [],
      version: "1",
      behavior: { kind: "quiet" },
    });
    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "p-1",
      participant_ref: "ref",
      token: "guest-token",
      display_name: "Audience",
      anon: false,
    });
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    sessionStorage.clear();
  });

  it("lets audiences step back through slides already passed by the presenter", async () => {
    const wrapper = mount(Audience, {
      props: { sessionId: "sess-1" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          RaiseQuestionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="audience-slide">{{ slide.id }}</div>',
          },
        },
      },
    });
    await flushPromises();

    expect(wrapper.get('[data-testid="audience-slide"]').text()).toBe("slide-2");
    expect(wrapper.get('[data-testid="audience-stepper"]').text()).toContain("Prev");
    expect(wrapper.get('[data-testid="audience-stepper"]').text()).toContain("Next");
    expect(wrapper.get('[data-testid="audience-stepper"]').classes()).toContain("audience-footer-sticky");
    expect(wrapper.findAll('[data-testid="audience-step-dot"]')).toHaveLength(2);
    expect(wrapper.get('[data-testid="audience-step-next"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="audience-step-live"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="audience-raise-question-fab"]').attributes("aria-label")).toBe("Raise question");
    expect(wrapper.get('[data-testid="audience-raise-question-fab"]').text().trim()).toBe("?");

    await wrapper.get('[data-testid="audience-step-prev"]').trigger("click");

    expect(wrapper.get('[data-testid="audience-slide"]').text()).toBe("slide-1");
    expect(wrapper.get('[data-testid="audience-step-status"]').text()).toContain("1 / 2");
  });

  it("lets audiences use arrow keys for slides already passed by the presenter", async () => {
    const wrapper = mount(Audience, {
      props: { sessionId: "sess-1" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          RaiseQuestionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="audience-slide">{{ slide.id }}</div>',
          },
        },
      },
    });
    await flushPromises();

    expect(wrapper.get('[data-testid="audience-slide"]').text()).toBe("slide-2");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }));
    await flushPromises();

    expect(wrapper.get('[data-testid="audience-slide"]').text()).toBe("slide-1");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    await flushPromises();

    expect(wrapper.get('[data-testid="audience-slide"]').text()).toBe("slide-2");
  });

  it("compacts audience history dots with a fade for large passed slide sets", async () => {
    const manySlides = structuredClone(snapshot);
    manySlides.slides = Array.from({ length: 46 }, (_, index) => ({
      id: `slide-${index + 1}`,
      deck_id: "deck-1",
      section_id: null,
      position: index,
      kicker: null,
      markdown: `# Slide ${index + 1}`,
      updated_at: new Date().toISOString(),
      widgets: [],
    }));
    manySlides.current_slide_id = "slide-12";
    vi.mocked(sessionsApi.audienceSnapshot).mockResolvedValueOnce(manySlides);
    const wrapper = mount(Audience, {
      props: { sessionId: "sess-1" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          RaiseQuestionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          SlideStage: {
            props: ["slide"],
            template: '<div data-testid="audience-slide">{{ slide.id }}</div>',
          },
        },
      },
    });
    await flushPromises();

    const window = wrapper.get('[data-testid="audience-step-window"]');
    expect(window.findAll('[data-testid="audience-step-dot"]').length).toBeLessThanOrEqual(7);
    expect(window.find('[data-testid="audience-step-fade-left"]').exists()).toBe(true);
    expect(window.find('[data-testid="audience-step-fade-right"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="audience-step-status"]').text()).toContain("12 / 12");
    expect(wrapper.get('[data-testid="audience-step-status"]').text()).toContain("46 total");
  });

  it("returns signed-in audience members to workspace when they leave", async () => {
    const auth = useAuthStore();
    auth.access = "access";
    auth.refresh = "refresh";
    auth.user = {
      id: "u1",
      email: "you@studio.press",
      display_name: "Field Notes",
      role: "owner",
      approval_status: "approved",
    };
    const wrapper = mount(Audience, {
      props: { sessionId: "sess-1" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          RaiseQuestionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          SlideStage: true,
        },
      },
    });
    await flushPromises();

    await wrapper.get('button[title="Leave session"]').trigger("click");

    expect(replace).toHaveBeenCalledWith({ name: "workspace" });
  });

  it("returns signed-in audience members to workspace when the session ends", async () => {
    const auth = useAuthStore();
    auth.access = "access";
    auth.refresh = "refresh";
    auth.user = {
      id: "u1",
      email: "you@studio.press",
      display_name: "Field Notes",
      role: "owner",
      approval_status: "approved",
    };
    mount(Audience, {
      props: { sessionId: "sess-1" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          RaiseQuestionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          SlideStage: true,
        },
      },
    });
    await flushPromises();

    MockWebSocket.instances[0].onmessage?.({
      data: JSON.stringify({ type: "session.ended", payload: {} }),
    });
    await flushPromises();

    expect(replace).toHaveBeenCalledWith({ name: "workspace" });
  });
});
