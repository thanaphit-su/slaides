import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { decksApi } from "@/api/decks";
import type { Deck, DeckListItem } from "@/api/types";

const VIEW_KEY = "slaides:view";

export const useWorkspaceStore = defineStore("workspace", () => {
  const decks = ref<DeckListItem[]>([]);
  const query = ref("");
  const view = ref<"grid" | "list">((localStorage.getItem(VIEW_KEY) as "grid" | "list") || "grid");
  const loading = ref(false);

  const filtered = computed(() =>
    decks.value.filter((d) => d.title.toLowerCase().includes(query.value.toLowerCase()))
  );

  async function fetch() {
    loading.value = true;
    try {
      decks.value = await decksApi.list();
    } finally {
      loading.value = false;
    }
  }

  async function create(title?: string): Promise<Deck> {
    const deck = await decksApi.create(title);
    await fetch();
    return deck;
  }

  async function importDeck(file: File): Promise<Deck> {
    const deck = await decksApi.importDeck(file);
    await fetch();
    return deck;
  }

  async function remove(id: string): Promise<void> {
    await decksApi.remove(id);
    decks.value = decks.value.filter((d) => d.id !== id);
  }

  function setView(v: "grid" | "list") {
    view.value = v;
    localStorage.setItem(VIEW_KEY, v);
  }

  return { decks, query, view, loading, filtered, fetch, create, importDeck, remove, setView };
});
