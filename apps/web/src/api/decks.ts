import { api, apiBlob } from "./client";
import type { Deck, DeckListItem, Section, Slide, SlideMutationResult } from "./types";

export const sectionsApi = {
  create: (deckId: string, title: string, position?: number) =>
    api<Section>(`/decks/${deckId}/sections`, {
      method: "POST",
      body: { title, position },
    }),
  update: (deckId: string, sectionId: string, patch: { title?: string; position?: number }) =>
    api<Section>(`/decks/${deckId}/sections/${sectionId}`, {
      method: "PATCH",
      body: patch,
    }),
  remove: (deckId: string, sectionId: string) =>
    api<void>(`/decks/${deckId}/sections/${sectionId}`, { method: "DELETE" }),
  reorder: (deckId: string, order: string[]) =>
    api<Section[]>(`/decks/${deckId}/sections/reorder`, {
      method: "POST",
      body: { order },
    }),
};

export const decksApi = {
  list: () => api<DeckListItem[]>("/decks"),
  create: (title?: string) =>
    api<Deck>("/decks", { method: "POST", body: { title } }),
  get: (id: string) => api<Deck>(`/decks/${id}`),
  patch: (id: string, patch: { title?: string; subtitle?: string; manifest?: Record<string, unknown> }) =>
    api<Deck>(`/decks/${id}`, { method: "PATCH", body: patch }),
  remove: (id: string) => api<void>(`/decks/${id}`, { method: "DELETE" }),
  duplicate: (id: string) => api<Deck>(`/decks/${id}/duplicate`, { method: "POST" }),

  insertSlide: (deckId: string, position: number, markdown = "", sectionId?: string | null) =>
    api<Slide>(`/decks/${deckId}/slides`, {
      method: "POST",
      body: { position, markdown, section_id: sectionId ?? null },
    }),
  updateSlide: (deckId: string, slideId: string, markdown: string, kicker?: string | null) =>
    api<SlideMutationResult>(`/decks/${deckId}/slides/${slideId}`, {
      method: "PUT",
      body: { markdown, kicker },
    }),
  deleteSlide: (deckId: string, slideId: string) =>
    api<void>(`/decks/${deckId}/slides/${slideId}`, { method: "DELETE" }),
  reorderSlides: (deckId: string, order: { id: string; section_id: string | null }[]) =>
    api<Slide[]>(`/decks/${deckId}/slides/reorder`, {
      method: "POST",
      body: { order },
    }),

  exportDeck: (id: string) => apiBlob(`/decks/${id}/export`, { method: "POST" }),
  importDeck: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api<Deck>("/decks/import", { method: "POST", formData: form });
  },
};
