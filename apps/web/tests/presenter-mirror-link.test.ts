import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import Presenter from "../src/pages/Presenter.vue";
import { sessionsApi } from "../src/api/sessions";
import { useAuthStore } from "../src/stores/auth";
import type { SessionSnapshot } from "../src/api/types";

vi.mock("@/preview/handshake", () => ({
  maybeReceivePreviewAuth: vi.fn(async () => ({ isPreview: false })),
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState = 1;
  onopen: ((ev: any) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.({}));
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.();
  }
}
(MockWebSocket as any).OPEN = 1;

const snapshot: SessionSnapshot = {
  id: "sess-1",
  code: "ABC123",
  deck_id: "deck-1",
  deck_title: "Deck",
  owner_id: "owner-1",
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
      markdown: "# Slide",
      updated_at: "2026-06-06T00:00:00Z",
      widgets: [],
    },
  ],
  session_slides: [],
  questions: [],
  audience_count: 0,
};

describe("Presenter mirror link", () => {
  let originalWS: typeof WebSocket;
  const open = vi.fn(() => null);
  const writeText = vi.fn(async () => undefined);

  beforeEach(() => {
    setActivePinia(createPinia());
    originalWS = globalThis.WebSocket;
    // @ts-expect-error mock
    globalThis.WebSocket = MockWebSocket;
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    Object.defineProperty(window, "location", {
      value: new URL("https://slides.example/present/sess-1"),
      configurable: true,
    });
    vi.spyOn(window, "open").mockImplementation(open as unknown as typeof window.open);
    const auth = useAuthStore();
    auth.access = "host-token";
    vi.spyOn(sessionsApi, "get").mockResolvedValue(structuredClone(snapshot));
    vi.spyOn(sessionsApi, "mirrorLink").mockResolvedValue({
      url: "/mirror/sess-1?token=mirror-token",
      token: "mirror-token",
      access_mode: "link",
    });
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    vi.restoreAllMocks();
    writeText.mockClear();
    open.mockClear();
  });

  it("copies an absolute mirror URL from the presenter toolbar", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/present/:sessionId", name: "presenter", component: Presenter, props: true },
        { path: "/signin", name: "signin", component: { template: "<div />" } },
        { path: "/workspace", name: "workspace", component: { template: "<div />" } },
      ],
    });
    await router.push("/present/sess-1");
    await router.isReady();

    const wrapper = mount(Presenter, {
      props: { sessionId: "sess-1" },
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          AnswerModerationRail: true,
          LiveInteractionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          OpenInteractionFab: true,
          PresenterRail: true,
          SlideStage: true,
          Wordmark: true,
        },
      },
    });
    await flushPromises();

    const mirrorButton = wrapper.findAll("button").find((button) => button.text().includes("Mirror"));
    expect(mirrorButton).toBeTruthy();
    await mirrorButton!.trigger("click");
    await flushPromises();

    expect(sessionsApi.mirrorLink).toHaveBeenCalledWith("sess-1");
    expect(writeText).toHaveBeenCalledWith("https://slides.example/mirror/sess-1?token=mirror-token");
  });

  it("opens the mirror URL in a new tab on ctrl-click", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/present/:sessionId", name: "presenter", component: Presenter, props: true },
        { path: "/signin", name: "signin", component: { template: "<div />" } },
        { path: "/workspace", name: "workspace", component: { template: "<div />" } },
      ],
    });
    await router.push("/present/sess-1");
    await router.isReady();

    const wrapper = mount(Presenter, {
      props: { sessionId: "sess-1" },
      global: {
        plugins: [router],
        stubs: {
          AccountMenu: true,
          AnswerModerationRail: true,
          LiveInteractionSheet: true,
          LivePollSlide: true,
          LiveQuestionSlide: true,
          LiveRandomAudienceSlide: true,
          OpenInteractionFab: true,
          PresenterRail: true,
          SlideStage: true,
          Wordmark: true,
        },
      },
    });
    await flushPromises();

    const mirrorButton = wrapper.findAll("button").find((button) => button.text().includes("Mirror"));
    expect(mirrorButton).toBeTruthy();
    await mirrorButton!.trigger("click", { ctrlKey: true });
    await flushPromises();

    expect(sessionsApi.mirrorLink).toHaveBeenCalledWith("sess-1");
    expect(open).toHaveBeenCalledWith(
      "https://slides.example/mirror/sess-1?token=mirror-token",
      "_blank",
      "noopener,noreferrer",
    );
    expect(writeText).not.toHaveBeenCalled();
  });
});
