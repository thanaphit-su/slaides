import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { DeckListItem } from "@/api/types";
import DeckCard from "@/components/DeckCard.vue";

function deck(overrides: Partial<DeckListItem> = {}): DeckListItem {
  return {
    id: "deck-1",
    title: "AI",
    subtitle: "Do not show this subtitle here",
    cover: null,
    updated_at: "2026-05-22T00:00:00Z",
    slide_count: 8,
    preview_kicker: "First slide",
    preview_markdown: "# Artificial Intelligence\n\n## Introduction to artificial intelligence for first-time learners",
    ...overrides,
  };
}

describe("DeckCard", () => {
  it("shows the first slide h2 in the footer metadata and truncates long text", () => {
    const wrapper = mount(DeckCard, {
      props: { deck: deck() },
      global: {
        stubs: {
          DeckCover: true,
          Icon: true,
        },
      },
    });

    const subheader = wrapper.get('[data-testid="deck-card-first-slide-subheader"]');

    expect(subheader.text()).toBe("Introduction to artificial intelligence...");
    expect(subheader.text()).not.toContain("Do not show this subtitle here");
  });

  it("leaves the footer metadata blank when the first slide has no h2", () => {
    const wrapper = mount(DeckCard, {
      props: {
        deck: deck({
          preview_markdown: "# Artificial Intelligence\n\nOpening copy only.",
        }),
      },
      global: {
        stubs: {
          DeckCover: true,
          Icon: true,
        },
      },
    });

    expect(wrapper.get('[data-testid="deck-card-first-slide-subheader"]').text()).toBe("");
  });

  it("shows a live badge when the deck has an active session", () => {
    const wrapper = mount(DeckCard, {
      props: { deck: deck(), live: true },
      global: {
        stubs: {
          DeckCover: true,
          Icon: true,
        },
      },
    });

    const badge = wrapper.get('[data-testid="deck-card-live-badge"]');
    expect(badge.text()).toBe("LIVE");
  });

  it("uses class-based chrome so dark mode can restyle the card shell", () => {
    const wrapper = mount(DeckCard, {
      props: { deck: deck() },
      global: {
        stubs: {
          DeckCover: true,
          Icon: true,
        },
      },
    });

    expect(wrapper.classes()).toContain("deck-card");
    expect(wrapper.find(".deck-card-cover").exists()).toBe(true);
    expect(wrapper.find(".deck-card-body").exists()).toBe(true);
  });
});
