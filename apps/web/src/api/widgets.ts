import { api, apiBlob } from "./client";
import type { SlideWidgetEmbed, Widget, WidgetAiMessage, WidgetAiThread, WidgetRevision, WidgetSummary } from "./types";

export const widgetsApi = {
  /** Workspace-wide listing (across every deck the caller owns). Used by
   * the "copy from another deck" picker; the editor sidebar uses the
   * deck-scoped `listForDeck` instead. */
  list: () => api<WidgetSummary[]>("/widgets"),
  listForDeck: (deckId: string) => api<WidgetSummary[]>(`/decks/${deckId}/widgets`),
  get: (id: string) => api<Widget>(`/widgets/${id}`),
  getAs: (id: string, token: string) =>
    api<Widget>(`/widgets/${id}`, { headers: { Authorization: `Bearer ${token}` } }),
  /** Widgets v2 — widgets are deck-local. Use createInDeck so the new
   * widget is owned by an actual deck. */
  createInDeck: (deckId: string, body: Partial<Widget>) =>
    api<Widget>(`/decks/${deckId}/widgets`, { method: "POST", body }),
  copyIntoDeck: (deckId: string, sourceWidgetId: string) =>
    api<Widget>(`/decks/${deckId}/widgets/copy`, {
      method: "POST",
      body: { source_widget_id: sourceWidgetId },
    }),
  patch: (id: string, body: Partial<Widget>, opts: { resetState?: boolean } = {}) =>
    api<Widget>(
      `/widgets/${id}${opts.resetState ? "?reset_state=true" : ""}`,
      { method: "PATCH", body },
    ),
  getAiThread: (widgetId: string) =>
    api<WidgetAiThread | null>(`/widgets/${widgetId}/ai-thread`),
  createAiThread: (
    widgetId: string,
    body: { title?: string | null; compact_summary?: Record<string, unknown> },
  ) =>
    api<WidgetAiThread>(`/widgets/${widgetId}/ai-thread`, { method: "POST", body }),
  appendAiMessage: (
    widgetId: string,
    threadId: string,
    body: {
      role: string;
      message_type: string;
      content: Record<string, unknown>;
      revision_id?: string | null;
    },
  ) =>
    api<WidgetAiMessage>(`/widgets/${widgetId}/ai-thread/${threadId}/messages`, {
      method: "POST",
      body,
    }),
  listRevisions: (widgetId: string) =>
    api<WidgetRevision[]>(`/widgets/${widgetId}/revisions`),
  rollbackRevision: (widgetId: string, revisionId: string) =>
    api<Widget>(`/widgets/${widgetId}/revisions/${revisionId}/rollback`, { method: "POST" }),
  remove: (id: string, opts: { force?: boolean } = {}) =>
    api<void>(`/widgets/${id}${opts.force ? "?force=true" : ""}`, { method: "DELETE" }),

  exportWidget: (id: string) => apiBlob(`/widgets/${id}/export`, { method: "POST" }),
  importIntoDeck: (deckId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api<Widget>(`/decks/${deckId}/widgets/import`, {
      method: "POST",
      formData: form,
    });
  },

  attachToSlide: (deckId: string, slideId: string, body: {
    placement_id: string;
    widget_id: string;
    props?: Record<string, unknown>;
  }) =>
    api<SlideWidgetEmbed>(`/decks/${deckId}/slides/${slideId}/widgets`, {
      method: "POST",
      body,
    }),
  detachFromSlide: (deckId: string, slideId: string, placementId: string) =>
    api<void>(`/decks/${deckId}/slides/${slideId}/widgets/${placementId}`, {
      method: "DELETE",
    }),
  patchPlacementProps: (
    deckId: string,
    slideId: string,
    placementId: string,
    props: Record<string, unknown>,
    opts: { resetState?: boolean } = {},
  ) =>
    api<SlideWidgetEmbed>(
      `/decks/${deckId}/slides/${slideId}/widgets/${placementId}${opts.resetState ? "?reset_state=true" : ""}`,
      { method: "PATCH", body: { props } },
    ),
};
