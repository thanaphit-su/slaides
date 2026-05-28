import { defineStore } from "pinia";
import { ref } from "vue";
import { widgetsApi } from "@/api/widgets";
import type { Widget, WidgetSummary } from "@/api/types";

export const useWidgetsStore = defineStore("widgets", () => {
  /** Widgets v2 — `summaries` holds the widgets belonging to the
   * currently-loaded deck. The cross-deck picker uses `crossDeck` to keep
   * those rows separate so switching decks doesn't churn the picker view. */
  const summaries = ref<WidgetSummary[]>([]);
  const crossDeck = ref<WidgetSummary[]>([]);
  const cache = ref<Record<string, Widget>>({});
  const loading = ref(false);
  const currentDeckId = ref<string | null>(null);

  async function fetchListForDeck(deckId: string) {
    loading.value = true;
    currentDeckId.value = deckId;
    try {
      summaries.value = await widgetsApi.listForDeck(deckId);
    } finally {
      loading.value = false;
    }
  }

  async function fetchCrossDeckList() {
    crossDeck.value = await widgetsApi.list();
  }

  async function fetchOne(id: string): Promise<Widget> {
    if (cache.value[id]) return cache.value[id];
    const w = await widgetsApi.get(id);
    cache.value[id] = w;
    return w;
  }

  async function ensureLoaded(ids: string[]) {
    const missing = ids.filter((id) => !cache.value[id]);
    await Promise.all(missing.map((id) => fetchOne(id)));
  }

  function invalidate(id: string) {
    delete cache.value[id];
  }

  function reset() {
    summaries.value = [];
    crossDeck.value = [];
    currentDeckId.value = null;
  }

  return {
    summaries,
    crossDeck,
    cache,
    loading,
    currentDeckId,
    fetchListForDeck,
    fetchCrossDeckList,
    fetchOne,
    ensureLoaded,
    invalidate,
    reset,
  };
});
