import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { DeckListItem } from "@/api/types";
import DeckList from "@/components/DeckList.vue";

function deck(overrides: Partial<DeckListItem> = {}): DeckListItem {
  return {
    id: "deck-1",
    title: "AI",
    subtitle: null,
    cover: null,
    updated_at: "2026-05-22T00:00:00Z",
    slide_count: 8,
    preview_kicker: null,
    preview_markdown: "# Artificial Intelligence",
    ...overrides,
  };
}

describe("DeckList", () => {
  it("shows a live badge on rows with active sessions", () => {
    const wrapper = mount(DeckList, {
      props: {
        decks: [deck({ id: "live-deck", title: "Live deck" }), deck({ id: "quiet-deck", title: "Quiet deck" })],
        liveDeckIds: new Set(["live-deck"]),
      },
      global: {
        stubs: {
          Icon: true,
        },
      },
    });

    const rows = wrapper.findAll('[data-testid="deck-list-row"]');
    expect(rows[0].text()).toContain("LIVE");
    expect(rows[1].text()).not.toContain("LIVE");
  });
});
