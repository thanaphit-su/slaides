import { api } from "./client";
import type {
  GuestJoinResponse,
  OpenAnswer,
  PollChoice,
  PreviewSessionResponse,
  SessionListItem,
  SessionPublic,
  SessionSlide,
  SessionSnapshot,
  Widget,
} from "./types";

export const sessionsApi = {
  list: () => api<SessionListItem[]>("/sessions"),
  active: (deckId: string) =>
    api<SessionListItem | null>(`/sessions/active?deck_id=${deckId}`),
  create: (deckId: string) =>
    api<SessionSnapshot>("/sessions", { method: "POST", body: { deck_id: deckId } }),
  createPreview: (deckId: string, audienceCount: number) =>
    api<PreviewSessionResponse>("/sessions/preview", {
      method: "POST",
      body: { deck_id: deckId, audience_count: audienceCount },
    }),
  get: (id: string) => api<SessionSnapshot>(`/sessions/${id}`),
  audienceSnapshot: (id: string, guestToken: string) =>
    api<SessionSnapshot>(`/sessions/${id}/audience`, {
      headers: { Authorization: `Bearer ${guestToken}` },
    }),
  end: (id: string) => api<SessionSnapshot>(`/sessions/${id}/end`, { method: "POST" }),
  advance: (id: string, slideId: string, isSessionSlide = false) =>
    api<SessionSnapshot>(`/sessions/${id}/advance`, {
      method: "POST",
      body: { slide_id: slideId, is_session_slide: isSessionSlide },
    }),
  byCode: (code: string) => api<SessionPublic>(`/sessions/by-code/${code}`),
  openInteraction: (
    id: string,
    body: {
      kind: string;
      parent_slide_id?: string | null;
      widget_id?: string | null;
      spec?: Record<string, unknown>;
      inverted_theme?: boolean;
    },
  ) => api<SessionSlide>(`/sessions/${id}/interactions`, { method: "POST", body }),

  patchInteraction: (
    sessionId: string,
    sessionSlideId: string,
    patch: {
      question?: string;
      prompt?: string;
      choices?: PollChoice[];
      config?: Record<string, unknown>;
    },
  ) =>
    api<SessionSlide>(`/sessions/${sessionId}/interactions/${sessionSlideId}`, {
      method: "PATCH",
      body: patch,
    }),

  listAnswers: (sessionId: string, sessionSlideId: string) =>
    api<OpenAnswer[]>(`/sessions/${sessionId}/interactions/${sessionSlideId}/answers`),

  promoteAnswer: (sessionId: string, sessionSlideId: string, logId: number) =>
    api<SessionSlide>(
      `/sessions/${sessionId}/interactions/${sessionSlideId}/promote/${logId}`,
      { method: "POST" },
    ),
  unpromoteAnswer: (sessionId: string, sessionSlideId: string, logId: number) =>
    api<SessionSlide>(
      `/sessions/${sessionId}/interactions/${sessionSlideId}/unpromote/${logId}`,
      { method: "POST" },
    ),
  hideAnswer: (sessionId: string, sessionSlideId: string, logId: number) =>
    api<SessionSlide>(
      `/sessions/${sessionId}/interactions/${sessionSlideId}/hide/${logId}`,
      { method: "POST" },
    ),
  resetPoll: (sessionId: string, sessionSlideId: string) =>
    api<SessionSlide>(`/sessions/${sessionId}/interactions/${sessionSlideId}/reset`, {
      method: "POST",
    }),
  closeVoting: (sessionId: string, sessionSlideId: string) =>
    api<SessionSlide>(`/sessions/${sessionId}/interactions/${sessionSlideId}/close`, {
      method: "POST",
    }),
  reopenVoting: (sessionId: string, sessionSlideId: string) =>
    api<SessionSlide>(`/sessions/${sessionId}/interactions/${sessionSlideId}/reopen`, {
      method: "POST",
    }),
  saveInteractionAsWidget: (sessionSlideId: string) =>
    api<Widget>(`/widgets/from-interaction`, {
      method: "POST",
      body: { session_slide_id: sessionSlideId },
    }),

  guestJoin: (code: string, email: string, displayName: string, anonymous: boolean) =>
    api<GuestJoinResponse>("/auth/guest", {
      method: "POST",
      body: { code, email, display_name: displayName, anonymous },
    }),
};
