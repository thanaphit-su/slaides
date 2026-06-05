import { defineStore } from "pinia";
import { ref } from "vue";
import { decksApi, sectionsApi } from "@/api/decks";
import { widgetsApi } from "@/api/widgets";
import type { Deck, Section, Slide, WidgetSummary } from "@/api/types";

const AUTOSAVE_MS = 450;

export const useEditorStore = defineStore("editor", () => {
  const deck = ref<Deck | null>(null);
  const activeSlideId = ref<string | null>(null);
  const loading = ref(false);
  const saving = ref(false);

  const pending = new Map<string, { markdown: string; kicker?: string | null; timer: number }>();

  async function loadDeck(id: string) {
    loading.value = true;
    try {
      deck.value = await decksApi.get(id);
      activeSlideId.value = deck.value.slides[0]?.id ?? null;
    } finally {
      loading.value = false;
    }
  }

  function setActive(id: string) {
    activeSlideId.value = id;
  }

  function setTitle(title: string) {
    if (deck.value) deck.value.title = title;
  }

  async function patchTitle(title: string) {
    if (!deck.value) return;
    const updated = await decksApi.patch(deck.value.id, { title });
    deck.value.title = updated.title;
  }

  async function flushSlide(slideId: string): Promise<Slide[] | null> {
    if (!deck.value) return null;
    const job = pending.get(slideId);
    if (!job) return null;
    clearTimeout(job.timer);
    pending.delete(slideId);
    saving.value = true;
    try {
      const res = await decksApi.updateSlide(deck.value.id, slideId, job.markdown, job.kicker);
      mergeSlides(slideId, res.slides);
      return res.slides;
    } finally {
      saving.value = false;
    }
  }

  async function patchSlideNotes(slideId: string, presenterNotes: string | null): Promise<void> {
    if (!deck.value) return;
    const updated = await decksApi.updateSlideNotes(deck.value.id, slideId, presenterNotes);
    const slide = deck.value.slides.find((s) => s.id === slideId);
    if (slide) {
      slide.presenter_notes = updated.presenter_notes;
      slide.updated_at = updated.updated_at;
    }
  }

  function mergeSlides(originalId: string, returned: Slide[]) {
    if (!deck.value) return;
    const originalIdx = deck.value.slides.findIndex((s) => s.id === originalId);
    if (originalIdx === -1) {
      deck.value.slides.push(...returned);
      deck.value.slides.sort((a, b) => a.position - b.position);
      return;
    }
    deck.value.slides.splice(originalIdx, 1, ...returned);
    // Renumber: positions may have shifted for slides after the replaced range.
    deck.value.slides.sort((a, b) => a.position - b.position);
  }

  function queueSlideUpdate(slideId: string, markdown: string, kicker?: string | null) {
    if (!deck.value) return;
    // Update local view immediately so subsequent edits build on the change.
    const slide = deck.value.slides.find((s) => s.id === slideId);
    if (slide) {
      slide.markdown = markdown;
      if (kicker !== undefined) slide.kicker = kicker ?? null;
    }
    const existing = pending.get(slideId);
    if (existing) clearTimeout(existing.timer);
    const timer = window.setTimeout(() => {
      void flushSlide(slideId);
    }, AUTOSAVE_MS);
    pending.set(slideId, { markdown, kicker, timer });
  }

  async function deleteSlide(slideId: string): Promise<void> {
    if (!deck.value) return;
    const slides = deck.value.slides;
    if (slides.length <= 1) {
      throw new Error("Can't delete the last slide in a deck.");
    }
    // Pick a replacement active slide (next, else previous) before removing.
    const idx = slides.findIndex((s) => s.id === slideId);
    let nextActive: string | null = activeSlideId.value;
    if (activeSlideId.value === slideId) {
      const replacement = slides[idx + 1] || slides[idx - 1];
      nextActive = replacement?.id ?? null;
    }
    // Drop any pending autosave for this slide so a late flush doesn't recreate it.
    const pendingJob = pending.get(slideId);
    if (pendingJob) {
      clearTimeout(pendingJob.timer);
      pending.delete(slideId);
    }
    await decksApi.deleteSlide(deck.value.id, slideId);
    deck.value = await decksApi.get(deck.value.id);
    activeSlideId.value = nextActive;
  }

  async function insertSlideAt(position: number, sectionId?: string | null): Promise<Slide | null> {
    if (!deck.value) return null;
    const activeSlide = deck.value.slides.find((s) => s.id === activeSlideId.value);
    const inheritedSectionId = sectionId === undefined ? (activeSlide?.section_id ?? null) : sectionId;
    const slide = await decksApi.insertSlide(deck.value.id, position, "", inheritedSectionId);
    deck.value = await decksApi.get(deck.value.id);
    activeSlideId.value = slide.id;
    return slide;
  }

  async function insertSlideInSection(sectionId: string): Promise<Slide | null> {
    if (!deck.value) return null;
    const sections = deck.value.sections.slice().sort((a, b) => a.position - b.position);
    const sectionIndex = new Map(sections.map((s, idx) => [s.id, idx] as const));
    const targetIndex = sectionIndex.get(sectionId);
    if (targetIndex === undefined) return null;

    const slides = deck.value.slides.slice().sort((a, b) => a.position - b.position);
    const sectionSlides = slides.filter((s) => s.section_id === sectionId);
    let position = slides.length;
    if (sectionSlides.length) {
      position = Math.max(...sectionSlides.map((s) => s.position)) + 1;
    } else {
      const firstLaterSlide = slides.find((s) => {
        const idx = s.section_id ? sectionIndex.get(s.section_id) : sections.length;
        return idx !== undefined && idx > targetIndex;
      });
      position = firstLaterSlide?.position ?? slides.length;
    }

    const slide = await decksApi.insertSlide(deck.value.id, position, "", sectionId);
    deck.value = await decksApi.get(deck.value.id);
    activeSlideId.value = slide.id;
    return slide;
  }

  async function exportZip(): Promise<Blob | null> {
    if (!deck.value) return null;
    return decksApi.exportDeck(deck.value.id);
  }

  async function attachWidget(slideId: string, widget: WidgetSummary): Promise<void> {
    if (!deck.value) return;
    // Flush any pending edits on this slide first so we don't overwrite the
    // placeholder the server is about to insert.
    await flushSlide(slideId);
    const placementId = `${widget.kind}-${crypto.randomUUID().slice(0, 8)}`;
    await widgetsApi.attachToSlide(deck.value.id, slideId, {
      placement_id: placementId,
      widget_id: widget.id,
      props: {},
    });
    // The server mutated the slide's markdown; reload the whole deck to pick
    // up the placeholder and the widgets[] array.
    deck.value = await decksApi.get(deck.value.id);
  }

  async function detachWidget(slideId: string, placementId: string): Promise<void> {
    if (!deck.value) return;
    await flushSlide(slideId);
    await widgetsApi.detachFromSlide(deck.value.id, slideId, placementId);
    deck.value = await decksApi.get(deck.value.id);
  }

  async function patchPlacementProps(
    slideId: string,
    placementId: string,
    props: Record<string, unknown>,
    opts: { resetState?: boolean } = {},
  ): Promise<void> {
    if (!deck.value) return;
    await flushSlide(slideId);
    // Rethrows ApiError on 409 edit_requires_reset so the caller can prompt
    // the user and retry with `resetState: true`.
    await widgetsApi.patchPlacementProps(deck.value.id, slideId, placementId, props, opts);
    // Reload the deck so `slide.widgets[i].props` reflects the new values
    // (the bridge re-boots with them on next paint).
    deck.value = await decksApi.get(deck.value.id);
  }

  async function createSection(title: string, position?: number): Promise<Section | null> {
    if (!deck.value) return null;
    const section = await sectionsApi.create(deck.value.id, title, position);
    deck.value = await decksApi.get(deck.value.id);
    return section;
  }

  async function renameSection(sectionId: string, title: string): Promise<void> {
    if (!deck.value) return;
    const trimmed = title.trim();
    if (!trimmed) return;
    const target = deck.value.sections.find((s) => s.id === sectionId);
    const original = target?.title;
    if (target) target.title = trimmed;
    try {
      await sectionsApi.update(deck.value.id, sectionId, { title: trimmed });
    } catch (err) {
      if (target && original !== undefined) target.title = original;
      throw err;
    }
  }

  async function deleteSection(sectionId: string): Promise<void> {
    if (!deck.value) return;
    await sectionsApi.remove(deck.value.id, sectionId);
    deck.value = await decksApi.get(deck.value.id);
  }

  async function reorderSlides(
    order: { id: string; section_id: string | null }[],
  ): Promise<void> {
    if (!deck.value) return;
    const snapshot = deck.value.slides.slice();
    const byId = new Map(snapshot.map((s) => [s.id, s] as const));
    // Optimistic local update.
    const reordered: Slide[] = [];
    order.forEach((entry, idx) => {
      const s = byId.get(entry.id);
      if (s) reordered.push({ ...s, position: idx, section_id: entry.section_id });
    });
    if (reordered.length === snapshot.length) {
      deck.value.slides = reordered;
    }
    try {
      const updated = await decksApi.reorderSlides(deck.value.id, order);
      // Server returns canonical slides (with widget placements) — trust it.
      if (deck.value) deck.value.slides = updated;
    } catch (err) {
      if (deck.value) deck.value.slides = snapshot;
      throw err;
    }
  }

  async function reorderSections(orderedIds: string[]): Promise<void> {
    if (!deck.value) return;
    const snapshot = deck.value.sections.slice();
    const byId = new Map(snapshot.map((s) => [s.id, s] as const));
    const reordered: Section[] = [];
    orderedIds.forEach((id, idx) => {
      const s = byId.get(id);
      if (s) reordered.push({ ...s, position: idx });
    });
    if (reordered.length === snapshot.length) {
      deck.value.sections = reordered;
    }
    try {
      await sectionsApi.reorder(deck.value.id, orderedIds);
    } catch (err) {
      // Roll back local state.
      if (deck.value) deck.value.sections = snapshot;
      throw err;
    }
  }

  return {
    deck,
    activeSlideId,
    loading,
    saving,
    loadDeck,
    setActive,
    setTitle,
    patchTitle,
    queueSlideUpdate,
    flushSlide,
    patchSlideNotes,
    insertSlideAt,
    insertSlideInSection,
    deleteSlide,
    exportZip,
    attachWidget,
    detachWidget,
    patchPlacementProps,
    createSection,
    renameSection,
    deleteSection,
    reorderSections,
    reorderSlides,
  };
});
