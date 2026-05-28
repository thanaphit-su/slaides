import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useSessionStore, saveGuestToken } from "../src/stores/session";
import { useAuthStore } from "../src/stores/auth";
import { sessionsApi } from "../src/api/sessions";
import type { SessionSnapshot } from "../src/api/types";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = 0;
  onopen: ((ev: any) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(url: string) {
    this.url = url;
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

const baseSnapshot: SessionSnapshot = {
  id: "sess-1",
  code: "SLD-TEST",
  deck_id: "deck-1",
  deck_title: "Test deck",
  owner_id: "owner-1",
  started_at: new Date().toISOString(),
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
  ],
  session_slides: [],
  questions: [],
  audience_count: 0,
};

describe("session store WS dispatch", () => {
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    setActivePinia(createPinia());
    originalWS = globalThis.WebSocket;
    // @ts-expect-error mock
    globalThis.WebSocket = MockWebSocket;
    MockWebSocket.instances = [];
    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "p-1",
      participant_ref: "ref",
      token: "guest-token",
      display_name: "Bob",
      anon: false,
    });
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    sessionStorage.clear();
  });

  it("updates current_slide_id on slide.changed", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toContain("/ws/sessions/sess-1");
    expect(ws.url).toContain("token=guest-token");

    ws.onmessage?.({
      data: JSON.stringify({ type: "slide.changed", payload: { slide_id: "slide-2" } }),
    });
    expect(store.snapshot!.current_slide_id).toBe("slide-2");
  });

  it("uses an explicit preview guest for audience snapshot and websocket auth", async () => {
    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "stored",
      participant_ref: "stored-ref",
      token: "stored-token",
      display_name: "Stored",
      anon: false,
    });
    const previewGuest = {
      session_id: "sess-1",
      participant_id: "preview",
      participant_ref: "preview-ref",
      token: "preview-token",
      display_name: "Alice",
      anon: false,
    };
    const snapshotSpy = vi.spyOn(sessionsApi, "audienceSnapshot").mockResolvedValueOnce(
      structuredClone(baseSnapshot),
    );

    const store = useSessionStore();
    await store.loadAudience("sess-1", previewGuest);
    store.connect("audience", "sess-1", previewGuest);
    await new Promise<void>((r) => queueMicrotask(() => r()));

    expect(snapshotSpy).toHaveBeenCalledWith("sess-1", "preview-token");
    expect(MockWebSocket.instances[0].url).toContain("token=preview-token");
    expect(MockWebSocket.instances[0].url).not.toContain("token=stored-token");
    snapshotSpy.mockRestore();
  });

  it("tracks presenter-passed slides without forcing audiences off a previous slide", async () => {
    const store = useSessionStore();
    const snap = structuredClone(baseSnapshot);
    snap.slides.push({
      id: "slide-3",
      deck_id: "deck-1",
      section_id: null,
      position: 2,
      kicker: null,
      markdown: "# Three",
      updated_at: new Date().toISOString(),
      widgets: [],
    });
    store.snapshot = snap;
    store.goToLiveSlide();
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({ type: "slide.changed", payload: { slide_id: "slide-2" } }),
    });
    expect(store.audienceCurrentSlideId).toBe("slide-2");
    expect(store.audiencePassedSlides.map((s) => s.id)).toEqual(["slide-1", "slide-2"]);

    store.stepAudienceSlide(-1);
    expect(store.audienceCurrentSlideId).toBe("slide-1");

    ws.onmessage?.({
      data: JSON.stringify({ type: "slide.changed", payload: { slide_id: "slide-3" } }),
    });

    expect(store.currentSlideId).toBe("slide-3");
    expect(store.audienceCurrentSlideId).toBe("slide-1");
    expect(store.audiencePassedSlides.map((s) => s.id)).toEqual(["slide-1", "slide-2", "slide-3"]);
    expect(store.canAudienceStepNext).toBe(true);
  });

  it("adds a live interaction slide and advances when the server broadcasts both events", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "session_slide.inserted",
        payload: {
          id: "ss-1",
          session_id: "sess-1",
          parent_slide_id: "slide-1",
          widget_id: null,
          position: 0,
          kind: "poll",
          spec: {
            type: "poll",
            question: "?",
            choices: [{ id: "c1", label: "A" }, { id: "c2", label: "B" }],
            config: { allow_other: false, show_results_live: true, anonymous: true },
            state: { voting_closed: false, choices_locked: false },
          },
          results: { tally: {}, voters: 0 },
          inverted_theme: false,
          opened_at: new Date().toISOString(),
          closed_at: null,
        },
      }),
    });
    ws.onmessage?.({
      data: JSON.stringify({ type: "slide.changed", payload: { slide_id: "ss-1", is_session_slide: true } }),
    });

    expect(store.snapshot!.session_slides.map((s) => s.id)).toEqual(["ss-1"]);
    expect(store.snapshot!.current_slide_id).toBe("ss-1");
  });

  it("appends new questions on question.new", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "question.new",
        payload: {
          id: "q-1",
          slide_id: "slide-1",
          participant_ref: "ref",
          anon: false,
          text: "Hello",
          raised_at: new Date().toISOString(),
          answered_at: null,
        },
      }),
    });
    expect(store.snapshot!.questions).toHaveLength(1);
    expect(store.snapshot!.questions[0].text).toBe("Hello");
  });

  it("tracks audience count from participant events", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "participant.joined",
        payload: { ref: "x", count: 3 },
      }),
    });
    expect(store.audienceCount).toBe(3);

    ws.onmessage?.({
      data: JSON.stringify({
        type: "participant.left",
        payload: { ref: "x", count: 2 },
      }),
    });
    expect(store.audienceCount).toBe(2);
  });

  it("raiseQuestion sends a question.raise frame", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    store.raiseQuestion("Why?", true);
    expect(ws.sent).toHaveLength(1);
    const parsed = JSON.parse(ws.sent[0]);
    expect(parsed.type).toBe("question.raise");
    expect(parsed.payload.text).toBe("Why?");
    expect(parsed.payload.anonymous).toBe(true);
  });

  it("interaction.tally updates the matching session_slide results", async () => {
    const store = useSessionStore();
    const snap = structuredClone(baseSnapshot);
    snap.session_slides = [
      {
        id: "ss-1",
        session_id: "sess-1",
        parent_slide_id: null,
        widget_id: null,
        position: 0,
        kind: "poll",
        spec: {
          type: "poll",
          question: "?",
          choices: [{ id: "c1", label: "A" }, { id: "c2", label: "B" }],
          config: { allow_other: false, show_results_live: true, anonymous: true },
          state: { voting_closed: false, choices_locked: false },
        },
        results: { tally: {}, voters: 0 },
        inverted_theme: true,
        opened_at: new Date().toISOString(),
        closed_at: null,
      },
    ];
    store.snapshot = snap;
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "interaction.tally",
        payload: {
          session_slide_id: "ss-1",
          results: { tally: { c1: 2, c2: 5 }, voters: 7 },
          spec_state: { voting_closed: false, choices_locked: true },
        },
      }),
    });
    const slide = store.snapshot!.session_slides[0];
    expect((slide.results as any).tally).toEqual({ c1: 2, c2: 5 });
    expect((slide.spec as any).state.choices_locked).toBe(true);
  });

  it("interaction_results.updated overwrites the session_slide results", async () => {
    const store = useSessionStore();
    const snap = structuredClone(baseSnapshot);
    snap.session_slides = [
      {
        id: "ss-q",
        session_id: "sess-1",
        parent_slide_id: null,
        widget_id: null,
        position: 0,
        kind: "question",
        spec: { type: "question", prompt: "?", config: { anonymous: true } },
        results: { promoted: [], total_answers: 0 },
        inverted_theme: true,
        opened_at: new Date().toISOString(),
        closed_at: null,
      },
    ];
    store.snapshot = snap;
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "interaction_results.updated",
        payload: {
          session_slide_id: "ss-q",
          results: {
            promoted: [{ id: "1", text: "Featured!", display_name: null, anon: true }],
            total_answers: 3,
          },
        },
      }),
    });
    const slide = store.snapshot!.session_slides[0];
    expect((slide.results as any).promoted).toHaveLength(1);
    expect((slide.results as any).total_answers).toBe(3);
  });

  it("question_answer.new buffers host-only answers per session slide", async () => {
    // Host connect requires an access token from the auth store.
    const auth = useAuthStore();
    auth.access = "host-token";
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("host", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    ws.onmessage?.({
      data: JSON.stringify({
        type: "question_answer.new",
        payload: {
          session_slide_id: "ss-x",
          answer: {
            id: 11,
            text: "Hello",
            participant_ref: "ref",
            display_name: null,
            anon: true,
            occurred_at: new Date().toISOString(),
            promoted: false,
          },
        },
      }),
    });
    const drained = store.takeIncomingAnswers("ss-x");
    expect(drained).toHaveLength(1);
    expect(drained[0].text).toBe("Hello");
    // Second take after drain is empty.
    expect(store.takeIncomingAnswers("ss-x")).toHaveLength(0);
  });

  it("submitPollVote sends a widget.contribute frame (Widgets v2 unified protocol)", async () => {
    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    store.submitPollVote("ss-1", "c2");
    const parsed = JSON.parse(ws.sent.at(-1)!);
    expect(parsed.type).toBe("widget.contribute");
    expect(parsed.payload).toEqual({ placement_id: "ss-1", value: "c2" });
  });

  it("widget.state for a slide_widget placement updates the placement_states cache + dispatches to the iframe", async () => {
    const store = useSessionStore();
    const snap = structuredClone(baseSnapshot);
    snap.slides[0].widgets = [
      {
        placement_id: "loud-1",
        widget_id: "w-loud",
        revision_id: null,
        kind: "custom",
        name: "Loud",
        props: {},
      },
    ];
    store.snapshot = snap;
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    const events: { widgetId: string; type: string; payload: Record<string, unknown> }[] = [];
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail;
      events.push(detail);
    };
    window.addEventListener("slaides:widget-broadcast", handler as EventListener);
    try {
      ws.onmessage?.({
        data: JSON.stringify({
          type: "widget.state",
          payload: {
            placement_id: "loud-1",
            state: { tally: { yes: 3, no: 1 } },
            state_version: 4,
            closed: false,
          },
        }),
      });

      // Cache picks up the new state.
      expect(store.placementStates["loud-1"]).toEqual({
        placement_id: "loud-1",
        widget_id: null,
        aggregator: "",
        state: { tally: { yes: 3, no: 1 } },
        state_version: 4,
        closed: false,
      });
      // The iframe (mounted as widget id w-loud) receives a `state` event.
      const dispatched = events.find((e) => e.widgetId === "w-loud" && e.type === "state");
      expect(dispatched).toBeTruthy();
      expect(dispatched!.payload).toEqual({
        placement_id: "loud-1",
        state: { tally: { yes: 3, no: 1 } },
        state_version: 4,
        closed: false,
      });

      // Stale event ignored.
      ws.onmessage?.({
        data: JSON.stringify({
          type: "widget.state",
          payload: {
            placement_id: "loud-1",
            state: { tally: { yes: 999 } },
            state_version: 2,
          },
        }),
      });
      expect((store.placementStates["loud-1"].state as any).tally).toEqual({ yes: 3, no: 1 });
    } finally {
      window.removeEventListener("slaides:widget-broadcast", handler as EventListener);
    }
  });

  it("widget.state event updates session_slide results and respects state_version", async () => {
    const store = useSessionStore();
    const snap = structuredClone(baseSnapshot);
    snap.session_slides = [
      {
        id: "ss-poll",
        session_id: "sess-1",
        parent_slide_id: null,
        widget_id: null,
        position: 0,
        kind: "poll",
        spec: {
          type: "poll",
          question: "?",
          choices: [{ id: "c1", label: "A" }, { id: "c2", label: "B" }],
          config: { allow_other: false, show_results_live: true, anonymous: true },
          state: { voting_closed: false, choices_locked: false },
        },
        results: { tally: {}, voters: 0 },
        inverted_theme: false,
        opened_at: new Date().toISOString(),
        closed_at: null,
      },
    ];
    store.snapshot = snap;
    store.connect("audience", "sess-1");
    await new Promise<void>((r) => queueMicrotask(() => r()));
    const ws = MockWebSocket.instances[0];

    // Latest state lands and merges spec_state into slide.spec.state.
    ws.onmessage?.({
      data: JSON.stringify({
        type: "widget.state",
        payload: {
          placement_id: "ss-poll",
          state: {
            tally: { c1: 1 },
            voters: 1,
            spec_state: { voting_closed: false, choices_locked: true },
          },
          state_version: 5,
          closed: false,
        },
      }),
    });
    let slide = store.snapshot!.session_slides[0];
    expect((slide.results as any).tally).toEqual({ c1: 1 });
    expect((slide.spec as any).state.choices_locked).toBe(true);

    // Stale event (lower version) is ignored.
    ws.onmessage?.({
      data: JSON.stringify({
        type: "widget.state",
        payload: {
          placement_id: "ss-poll",
          state: { tally: { c1: 999 }, voters: 999 },
          state_version: 1,
        },
      }),
    });
    slide = store.snapshot!.session_slides[0];
    expect((slide.results as any).tally).toEqual({ c1: 1 });
  });
});

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return { ...actual, attemptRefresh: vi.fn(async () => true) };
});

describe("session store host WS reconnect refreshes the access token", () => {
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    setActivePinia(createPinia());
    originalWS = globalThis.WebSocket;
    // @ts-expect-error mock
    globalThis.WebSocket = MockWebSocket;
    MockWebSocket.instances = [];
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.WebSocket = originalWS;
    vi.useRealTimers();
    sessionStorage.clear();
  });

  it("host reconnect awaits attemptRefresh and reuses the fresh access token", async () => {
    const auth = useAuthStore();
    auth.access = "tok_v1";
    auth.refresh = "refresh_v1";
    auth.user = { id: "u-1", email: "u@x", display_name: null, role: "instructor", approval_status: "approved" } as any;

    const client = await import("../src/api/client");
    const refreshSpy = vi.mocked(client.attemptRefresh);
    refreshSpy.mockReset();
    refreshSpy.mockImplementation(async () => {
      auth.access = "tok_v2";
      return true;
    });

    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("host", "sess-1");
    await Promise.resolve();
    expect(MockWebSocket.instances[0].url).toContain("token=tok_v1");

    // Simulate the WS dropping (e.g. server restart, network blip).
    MockWebSocket.instances[0].close();
    // Reconnect runs from setTimeout with exponential backoff.
    await vi.advanceTimersByTimeAsync(20_000);
    await Promise.resolve();

    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    expect(MockWebSocket.instances[1].url).toContain("token=tok_v2");
  });

  it("audience reconnect does NOT call attemptRefresh", async () => {
    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "p-1",
      participant_ref: "ref",
      token: "guest-token",
      display_name: "Bob",
      anon: false,
    });

    const client = await import("../src/api/client");
    const refreshSpy = vi.mocked(client.attemptRefresh);
    refreshSpy.mockReset();
    refreshSpy.mockResolvedValue(true);

    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1");
    await Promise.resolve();

    MockWebSocket.instances[0].close();
    await vi.advanceTimersByTimeAsync(20_000);
    await Promise.resolve();

    expect(refreshSpy).not.toHaveBeenCalled();
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    expect(MockWebSocket.instances[1].url).toContain("token=guest-token");
  });

  it("audience reconnect preserves an explicit preview guest even if shared storage changes", async () => {
    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "stored",
      participant_ref: "stored-ref",
      token: "stored-token",
      display_name: "Stored",
      anon: false,
    });
    const previewGuest = {
      session_id: "sess-1",
      participant_id: "preview",
      participant_ref: "preview-ref",
      token: "preview-token",
      display_name: "Alice",
      anon: false,
    };

    const store = useSessionStore();
    store.snapshot = structuredClone(baseSnapshot);
    store.connect("audience", "sess-1", previewGuest);
    await Promise.resolve();
    expect(MockWebSocket.instances[0].url).toContain("token=preview-token");

    saveGuestToken("sess-1", {
      session_id: "sess-1",
      participant_id: "stored-2",
      participant_ref: "stored-ref-2",
      token: "stored-token-2",
      display_name: "Stored 2",
      anon: false,
    });

    MockWebSocket.instances[0].close();
    await vi.advanceTimersByTimeAsync(20_000);
    await Promise.resolve();

    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    expect(MockWebSocket.instances[1].url).toContain("token=preview-token");
    expect(MockWebSocket.instances[1].url).not.toContain("token=stored-token-2");
  });
});

// silence unused import warnings under TS strict
void vi;
