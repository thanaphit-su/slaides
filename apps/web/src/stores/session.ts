import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { attemptRefresh } from "@/api/client";
import { sessionsApi } from "@/api/sessions";
import { useAuthStore } from "@/stores/auth";
import type {
  GuestJoinResponse,
  OpenAnswer,
  PlacementState,
  SessionQuestion,
  SessionSlide,
  SessionSnapshot,
} from "@/api/types";

const GUEST_KEY_PREFIX = "slaides:guest:";
const HEARTBEAT_MS = 10_000;
type TimelineSlide = SessionSnapshot["slides"][number] | SessionSlide;

function apiBase(): string {
  return import.meta.env.VITE_API_URL || "/api/v1";
}

function wsUrl(sessionId: string, token: string): string {
  const base = apiBase();
  // VITE_API_URL is like "http://localhost:8000/api/v1"; strip the /api/v1 to get host root.
  const root = base.replace(/\/api\/v1\/?$/, "");
  let httpRoot: string;
  if (root) {
    httpRoot = root;
  } else {
    httpRoot = `${window.location.protocol}//${window.location.host}`;
  }
  const wsRoot = httpRoot.replace(/^http/, "ws");
  return `${wsRoot}/ws/sessions/${sessionId}?token=${encodeURIComponent(token)}`;
}

export function loadGuestToken(sessionId: string): GuestJoinResponse | null {
  try {
    const raw = sessionStorage.getItem(GUEST_KEY_PREFIX + sessionId);
    if (!raw) return null;
    return JSON.parse(raw) as GuestJoinResponse;
  } catch {
    return null;
  }
}

export function saveGuestToken(sessionId: string, data: GuestJoinResponse): void {
  sessionStorage.setItem(GUEST_KEY_PREFIX + sessionId, JSON.stringify(data));
}

export function clearGuestToken(sessionId: string): void {
  sessionStorage.removeItem(GUEST_KEY_PREFIX + sessionId);
}

export const useSessionStore = defineStore("session", () => {
  const snapshot = ref<SessionSnapshot | null>(null);
  const role = ref<"host" | "audience" | null>(null);
  const connected = ref(false);
  const ended = ref(false);
  const audienceCount = ref(0);
  const audienceSlideId = ref<string | null>(null);
  const passedSlideIds = ref<string[]>([]);
  // Host-only buffer of incoming open-question answers (one list per session
  // slide id). Audience tabs never receive these — the WS event is host-only.
  const incomingAnswers = ref<Record<string, OpenAnswer[]>>({});
  // Widgets v2 Step 4 — placement_id → latest aggregated state for Loud
  // iframe widgets mounted on deck slides. Late-joiner snapshot fills this
  // up front; live `widget.state` events update it; WidgetFrame instances
  // pull from it on mount via `slaides:widget-broadcast` CustomEvents.
  const placementStates = ref<Record<string, PlacementState>>({});
  const ws = ref<WebSocket | null>(null);
  let heartbeatTimer = 0;
  let reconnectAttempts = 0;
  let intentionallyClosed = false;
  let currentSessionId: string | null = null;
  let currentToken: string | null = null;
  let currentAudienceGuest: { sessionId: string; guest: GuestJoinResponse } | null = null;

  const currentSlideId = computed(() => snapshot.value?.current_slide_id ?? null);

  const currentSlide = computed(() => {
    if (!snapshot.value) return null;
    const id = snapshot.value.current_slide_id;
    if (!id) return snapshot.value.slides[0] ?? null;
    return (
      snapshot.value.slides.find((s) => s.id === id) ||
      snapshot.value.session_slides.find((s) => s.id === id) ||
      null
    );
  });

  const isOnSessionSlide = computed(() => {
    if (!snapshot.value) return false;
    return snapshot.value.session_slides.some((s) => s.id === snapshot.value!.current_slide_id);
  });

  const presentationOrder = computed<TimelineSlide[]>(() => {
    const snap = snapshot.value;
    if (!snap) return [];
    const byParent = new Map<string, SessionSlide[]>();
    const orphans: SessionSlide[] = [];
    for (const sessionSlide of snap.session_slides) {
      if (!sessionSlide.parent_slide_id) {
        orphans.push(sessionSlide);
        continue;
      }
      const group = byParent.get(sessionSlide.parent_slide_id) || [];
      group.push(sessionSlide);
      byParent.set(sessionSlide.parent_slide_id, group);
    }

    const ordered: TimelineSlide[] = [];
    for (const slide of snap.slides) {
      ordered.push(slide);
      ordered.push(...(byParent.get(slide.id) || []).slice().sort((a, b) => a.position - b.position));
    }
    ordered.push(...orphans.slice().sort((a, b) => a.position - b.position));
    return ordered;
  });

  const audienceCurrentSlideId = computed(() => audienceSlideId.value ?? currentSlideId.value);
  const audiencePassedSlides = computed(() =>
    presentationOrder.value.filter((slide) => passedSlideIds.value.includes(slide.id)),
  );
  const audienceStepIndex = computed(() =>
    audiencePassedSlides.value.findIndex((slide) => slide.id === audienceCurrentSlideId.value),
  );
  const canAudienceStepPrev = computed(() => audienceStepIndex.value > 0);
  const canAudienceStepNext = computed(
    () => audienceStepIndex.value >= 0 && audienceStepIndex.value < audiencePassedSlides.value.length - 1,
  );
  const isAudienceViewingLive = computed(() => audienceCurrentSlideId.value === currentSlideId.value);

  function markPassedThrough(slideId: string | null | undefined): void {
    if (!slideId) return;
    const order = presentationOrder.value;
    const idx = order.findIndex((slide) => slide.id === slideId);
    const nextIds = idx >= 0 ? order.slice(0, idx + 1).map((slide) => slide.id) : [slideId];
    const merged = [...passedSlideIds.value];
    for (const id of nextIds) {
      if (!merged.includes(id)) merged.push(id);
    }
    passedSlideIds.value = order.length
      ? order.map((slide) => slide.id).filter((id) => merged.includes(id))
      : merged;
  }

  function resetAudienceProgress(): void {
    passedSlideIds.value = [];
    audienceSlideId.value = snapshot.value?.current_slide_id ?? null;
    markPassedThrough(audienceSlideId.value);
  }

  function syncPresenterSlide(slideId: string | null | undefined): void {
    if (!snapshot.value || !slideId) return;
    const wasFollowingLive = !audienceSlideId.value || audienceSlideId.value === snapshot.value.current_slide_id;
    snapshot.value.current_slide_id = slideId;
    markPassedThrough(slideId);
    if (role.value === "audience" && wasFollowingLive) {
      audienceSlideId.value = slideId;
    }
  }

  function stepAudienceSlide(delta: -1 | 1): void {
    const slides = audiencePassedSlides.value;
    const idx = audienceStepIndex.value;
    const next = slides[idx + delta];
    if (next) audienceSlideId.value = next.id;
  }

  function goToAudienceSlide(slideId: string): void {
    if (passedSlideIds.value.includes(slideId)) audienceSlideId.value = slideId;
  }

  function goToLiveSlide(): void {
    if (!currentSlideId.value) return;
    markPassedThrough(currentSlideId.value);
    audienceSlideId.value = currentSlideId.value;
  }

  function seedPlacementStates(): void {
    const list = snapshot.value?.placement_states || [];
    const next: Record<string, PlacementState> = {};
    for (const entry of list) next[entry.placement_id] = entry;
    placementStates.value = next;
  }

  async function loadHost(sessionId: string): Promise<void> {
    snapshot.value = await sessionsApi.get(sessionId);
    audienceCount.value = snapshot.value.audience_count;
    seedPlacementStates();
  }

  function resolveAudienceGuest(
    sessionId: string,
    guestOverride?: GuestJoinResponse | null,
  ): GuestJoinResponse | null {
    if (guestOverride) {
      currentAudienceGuest = { sessionId, guest: guestOverride };
      return guestOverride;
    }
    if (currentAudienceGuest?.sessionId === sessionId) {
      return currentAudienceGuest.guest;
    }
    const guest = loadGuestToken(sessionId);
    currentAudienceGuest = guest ? { sessionId, guest } : null;
    return guest;
  }

  async function loadAudience(
    sessionId: string,
    guestOverride?: GuestJoinResponse | null,
  ): Promise<void> {
    const guest = resolveAudienceGuest(sessionId, guestOverride);
    if (!guest) {
      snapshot.value = null;
      return;
    }
    snapshot.value = await sessionsApi.audienceSnapshot(sessionId, guest.token);
    audienceCount.value = snapshot.value.audience_count;
    resetAudienceProgress();
    seedPlacementStates();
  }

  function dispatchToWidget(widgetId: string, type: string, payload: Record<string, unknown>) {
    const ev = new CustomEvent("slaides:widget-broadcast", {
      detail: { widgetId, type, payload },
    });
    window.dispatchEvent(ev);
  }

  function buildHandlers(): Record<string, (payload: any) => void> {
    return {
      "session.state": (payload) => {
        if (snapshot.value && payload?.current_slide_id) {
          syncPresenterSlide(payload.current_slide_id);
        }
      },
      "slide.changed": (payload) => {
        if (!snapshot.value) return;
        syncPresenterSlide(payload.slide_id);
      },
      "session_slide.inserted": (payload: SessionSlide) => {
        if (!snapshot.value) return;
        const existing = snapshot.value.session_slides.findIndex((s) => s.id === payload.id);
        if (existing >= 0) snapshot.value.session_slides[existing] = payload;
        else snapshot.value.session_slides.push(payload);
      },
      "question.new": (payload: SessionQuestion) => {
        if (!snapshot.value) return;
        if (!snapshot.value.questions.find((q) => q.id === payload.id)) {
          snapshot.value.questions.push(payload);
        }
      },
      "question.answered": (payload) => {
        if (!snapshot.value) return;
        const q = snapshot.value.questions.find((qq) => qq.id === payload.question_id);
        if (q) q.answered_at = new Date().toISOString();
      },
      "participant.joined": (payload) => {
        if (typeof payload?.count === "number") audienceCount.value = payload.count;
      },
      "participant.left": (payload) => {
        if (typeof payload?.count === "number") audienceCount.value = payload.count;
      },
      "interaction.vote": (payload) => {
        if (payload?.widget_id) {
          dispatchToWidget(payload.widget_id, "vote.broadcast", payload);
        }
      },
      "interaction.text": (payload) => {
        if (payload?.widget_id) {
          dispatchToWidget(payload.widget_id, "text.broadcast", payload);
        }
      },
      "interaction.slider": (payload) => {
        if (payload?.widget_id) {
          dispatchToWidget(payload.widget_id, "slider.broadcast", payload);
        }
      },
      "interaction.tally": (payload) => {
        if (!snapshot.value) return;
        const slide = snapshot.value.session_slides.find(
          (s) => s.id === payload?.session_slide_id,
        );
        if (!slide) return;
        if (payload?.results) slide.results = payload.results;
        if (payload?.spec_state) {
          slide.spec = { ...(slide.spec || {}), state: payload.spec_state };
        }
      },
      "interaction_spec.updated": (payload) => {
        if (!snapshot.value) return;
        const slide = snapshot.value.session_slides.find(
          (s) => s.id === payload?.session_slide_id,
        );
        if (slide && payload?.spec) slide.spec = payload.spec;
      },
      "interaction_results.updated": (payload) => {
        if (!snapshot.value) return;
        const slide = snapshot.value.session_slides.find(
          (s) => s.id === payload?.session_slide_id,
        );
        if (slide && payload?.results) slide.results = payload.results;
      },
      // Widgets v2 Step 3 — canonical contribution-result event. For native
      // polls and open questions, `placement_id` is the `session_slide.id`
      // and `state` is the same shape `interaction.tally` /
      // `interaction_results.updated` already carry. We mirror it onto
      // `session_slide.results` and gate on `state_version` so out-of-order
      // events can't roll back a newer state.
      "widget.state": (payload) => {
        const placementId: string | undefined = payload?.placement_id;
        if (!placementId) return;
        const next = payload?.state || {};
        const incomingVersion = Number(payload?.state_version) || 0;
        const closed = Boolean(payload?.closed);

        // Native polls/questions (Step 3) — placement_id matches a
        // session_slide.id. Mirror onto slide.results gated on state_version.
        const slide = snapshot.value?.session_slides.find((s) => s.id === placementId);
        if (slide) {
          const currentVersion = Number((slide.results as { _state_version?: number })?._state_version) || 0;
          if (!incomingVersion || incomingVersion >= currentVersion) {
            slide.results = { ...next, _state_version: incomingVersion };
            const specState = (next as { spec_state?: unknown }).spec_state;
            if (specState && typeof specState === "object") {
              slide.spec = { ...(slide.spec || {}), state: specState as Record<string, unknown> };
            }
          }
          return;
        }

        // Widgets v2 Step 4 — Loud iframe widget on a deck slide. Update
        // the placement_states cache and dispatch into any mounted
        // WidgetFrame instances via the existing broadcast CustomEvent.
        const prior = placementStates.value[placementId];
        if (prior && incomingVersion && incomingVersion < prior.state_version) return;
        const entry: PlacementState = {
          placement_id: placementId,
          widget_id: prior?.widget_id ?? null,
          aggregator: prior?.aggregator ?? "",
          state: next as Record<string, unknown>,
          state_version: incomingVersion,
          closed,
        };
        placementStates.value = { ...placementStates.value, [placementId]: entry };
        // Find a WidgetFrame mounted for this placement and post the state
        // into its iframe. The dispatch goes by widget_id (the broadcast
        // contract WidgetFrame already implements); we resolve via the
        // snapshot's slide widgets list.
        const widgetId = resolveWidgetIdForPlacement(placementId);
        if (widgetId) {
          dispatchToWidget(widgetId, "state", {
            placement_id: placementId,
            state: next,
            state_version: incomingVersion,
            closed,
          });
        }
      },
      "question_answer.new": (payload) => {
        const slideId: string | undefined = payload?.session_slide_id;
        const answer: OpenAnswer | undefined = payload?.answer;
        if (!slideId || !answer) return;
        const existing = incomingAnswers.value[slideId] || [];
        if (existing.some((a) => a.id === answer.id)) return;
        incomingAnswers.value = {
          ...incomingAnswers.value,
          [slideId]: [answer, ...existing],
        };
      },
      "widget.update": (payload) => {
        if (payload?.widget_id) {
          dispatchToWidget(payload.widget_id, "widget.update", payload);
        }
      },
      "session.ended": () => {
        if (snapshot.value) {
          snapshot.value.ended_at = new Date().toISOString();
        }
        ended.value = true;
      },
    };
  }

  function forwardWidgetEvent(
    placement: { widget_id: string; placement_id: string },
    event: { type: string; payload: Record<string, unknown> },
  ): void {
    const slideId = currentSlideId.value;
    if (event.type === "widget.contribute") {
      // Widgets v2 Step 4 — Loud iframe widget contribution. The server
      // looks up the placement by `placement_id`, runs the aggregator,
      // and broadcasts back as `widget.state`.
      sendRaw({
        type: "widget.contribute",
        payload: { placement_id: placement.placement_id, value: event.payload?.value },
      });
      return;
    }
    if (event.type === "vote") {
      sendRaw({
        type: "interaction.vote",
        payload: { widget_id: placement.widget_id, slide_id: slideId, ...event.payload },
      });
    } else if (event.type === "text") {
      sendRaw({
        type: "interaction.text",
        payload: { widget_id: placement.widget_id, slide_id: slideId, ...event.payload },
      });
    } else if (event.type === "slider") {
      sendRaw({
        type: "interaction.slider",
        payload: { widget_id: placement.widget_id, slide_id: slideId, ...event.payload },
      });
    }
    // Other widget events (state.set, llm.request) are not yet forwarded.
  }

  function resolveWidgetIdForPlacement(placementId: string): string | null {
    if (!snapshot.value) return null;
    for (const slide of snapshot.value.slides) {
      const placement = slide.widgets.find((w) => w.placement_id === placementId);
      if (placement) return placement.widget_id;
    }
    return null;
  }

  let beforeUnloadHandler: ((ev: BeforeUnloadEvent) => void) | null = null;

  function connect(
    mode: "host" | "audience",
    sessionId: string,
    guestOverride?: GuestJoinResponse | null,
  ): void {
    intentionallyClosed = false;
    role.value = mode;
    currentSessionId = sessionId;

    let token: string | null = null;
    if (mode === "host") {
      currentAudienceGuest = null;
      token = useAuthStore().access;
    } else {
      const guest = resolveAudienceGuest(sessionId, guestOverride);
      token = guest?.token ?? null;
    }
    if (!token) return;
    currentToken = token;

    const socket = new WebSocket(wsUrl(sessionId, token));
    ws.value = socket;
    const handlers = buildHandlers();

    socket.onopen = () => {
      connected.value = true;
      reconnectAttempts = 0;
      if (mode === "audience") {
        // Start heartbeat so server presence stays alive.
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "heartbeat" }));
          }
        }, HEARTBEAT_MS);
      }
      // Fast-close on tab unload so the server drops presence + publishes
      // `participant.left` immediately instead of waiting for the 30s TTL.
      if (!beforeUnloadHandler) {
        beforeUnloadHandler = () => {
          intentionallyClosed = true;
          try {
            socket.close();
          } catch {
            // ignore
          }
        };
        window.addEventListener("beforeunload", beforeUnloadHandler);
        window.addEventListener("pagehide", beforeUnloadHandler);
      }
    };

    socket.onmessage = (ev) => {
      try {
        const event = JSON.parse(ev.data) as { type: string; payload: unknown };
        const fn = handlers[event.type];
        if (fn) fn(event.payload);
      } catch {
        // ignore
      }
    };

    socket.onclose = () => {
      connected.value = false;
      window.clearInterval(heartbeatTimer);
      if (intentionallyClosed) return;
      // Reconnect with exponential backoff up to ~16s.
      reconnectAttempts = Math.min(reconnectAttempts + 1, 5);
      const delay = Math.min(1000 * 2 ** reconnectAttempts, 16_000);
      const sid = currentSessionId;
      const r = role.value;
      if (!sid || !r) return;
      window.setTimeout(async () => {
        if (intentionallyClosed) return;
        if (r === "host") {
          // Access token may have expired during the WS pause. Refresh
          // through the standard auth endpoint so connect() reads a
          // fresh access from the auth store before re-handshaking.
          try {
            await attemptRefresh();
          } catch {
            // ignore — connect() will read whatever the store currently has
          }
        }
        if (!intentionallyClosed) connect(r, sid);
      }, delay);
    };
  }

  function disconnect(): void {
    intentionallyClosed = true;
    window.clearInterval(heartbeatTimer);
    if (beforeUnloadHandler) {
      window.removeEventListener("beforeunload", beforeUnloadHandler);
      window.removeEventListener("pagehide", beforeUnloadHandler);
      beforeUnloadHandler = null;
    }
    if (ws.value) {
      try {
        ws.value.close();
      } catch {
        // ignore
      }
    }
    ws.value = null;
    connected.value = false;
    currentAudienceGuest = null;
  }

  function sendRaw(message: unknown): void {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(message));
    }
  }

  async function advanceTo(slideId: string, isSessionSlide = false): Promise<void> {
    if (!snapshot.value || role.value !== "host") return;
    await sessionsApi.advance(snapshot.value.id, slideId, isSessionSlide);
    // Optimistic — also broadcast on the WS via REST endpoint already publishes.
    snapshot.value.current_slide_id = slideId;
  }

  async function openInteraction(
    body: {
      kind: string;
      parent_slide_id?: string | null;
      widget_id?: string | null;
      spec?: Record<string, unknown>;
      inverted_theme?: boolean;
    },
  ): Promise<SessionSlide | null> {
    if (!snapshot.value || role.value !== "host") return null;
    const inserted = await sessionsApi.openInteraction(snapshot.value.id, body);
    if (!snapshot.value.session_slides.find((s) => s.id === inserted.id)) {
      snapshot.value.session_slides.push(inserted);
    }
    snapshot.value.current_slide_id = inserted.id;
    return inserted;
  }

  function vote(widgetId: string, slideId: string | null, choice: unknown): void {
    sendRaw({
      type: "interaction.vote",
      payload: { widget_id: widgetId, slide_id: slideId, choice },
    });
  }

  // Widgets v2 Step 3 — the audience-side contribution path is now the
  // unified `widget.contribute` event. For native polls/questions the
  // `placement_id` is the `session_slide.id`; the backend infers the
  // aggregator (tally vs append) from the slide's kind.
  function submitPollVote(sessionSlideId: string, choiceId: string): void {
    sendRaw({
      type: "widget.contribute",
      payload: { placement_id: sessionSlideId, value: choiceId },
    });
  }

  function submitPollOther(sessionSlideId: string, text: string): void {
    sendRaw({
      type: "widget.contribute",
      payload: { placement_id: sessionSlideId, value: text },
    });
  }

  function submitOpenAnswer(sessionSlideId: string, text: string): void {
    sendRaw({
      type: "widget.contribute",
      payload: { placement_id: sessionSlideId, value: text },
    });
  }

  function takeIncomingAnswers(sessionSlideId: string): OpenAnswer[] {
    const out = incomingAnswers.value[sessionSlideId] || [];
    if (out.length) {
      const next = { ...incomingAnswers.value };
      delete next[sessionSlideId];
      incomingAnswers.value = next;
    }
    return out;
  }

  function raiseQuestion(text: string, anonymous: boolean): void {
    sendRaw({
      type: "question.raise",
      payload: { text, anonymous, slide_id: role.value === "audience" ? audienceCurrentSlideId.value : currentSlideId.value },
    });
  }

  function markAnswered(questionId: string): void {
    sendRaw({ type: "question.answered", payload: { question_id: questionId } });
    if (!snapshot.value) return;
    const q = snapshot.value.questions.find((qq) => qq.id === questionId);
    if (q) q.answered_at = new Date().toISOString();
  }

  async function endSession(): Promise<void> {
    if (!snapshot.value || role.value !== "host") return;
    const ended = await sessionsApi.end(snapshot.value.id);
    snapshot.value = ended;
    disconnect();
  }

  return {
    snapshot,
    role,
    connected,
    ended,
    audienceCount,
    audienceSlideId,
    passedSlideIds,
    placementStates,
    currentSlideId,
    currentSlide,
    isOnSessionSlide,
    presentationOrder,
    audienceCurrentSlideId,
    audiencePassedSlides,
    audienceStepIndex,
    canAudienceStepPrev,
    canAudienceStepNext,
    isAudienceViewingLive,
    stepAudienceSlide,
    goToAudienceSlide,
    goToLiveSlide,
    loadHost,
    loadAudience,
    connect,
    disconnect,
    advanceTo,
    openInteraction,
    forwardWidgetEvent,
    vote,
    submitPollVote,
    submitPollOther,
    submitOpenAnswer,
    incomingAnswers,
    takeIncomingAnswers,
    raiseQuestion,
    markAnswered,
    endSession,
  };
});
