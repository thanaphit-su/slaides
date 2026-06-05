import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DeckCover from "@/components/DeckCover.vue";

describe("DeckCover", () => {
  it("renders first-slide previews without decorative dot marks", () => {
    const wrapper = mount(DeckCover, {
      props: {
        markdown: "# Welcome to SLAIDES\n\nYou build a deck like a writer.",
        kicker: "$ 01 - Hello",
      },
    });

    expect(wrapper.findAll("circle")).toHaveLength(0);
  });

  it("renders the default fieldnotes cover without decorative dot marks", () => {
    const wrapper = mount(DeckCover, {
      props: {
        variant: "fieldnotes",
      },
    });

    expect(wrapper.findAll("circle")).toHaveLength(0);
  });

  it("uses theme variables for first-slide preview colors", () => {
    const wrapper = mount(DeckCover, {
      props: {
        markdown: "# Welcome to SLAIDES\n\nYou build a deck like a writer.",
        kicker: "$ 01 - Hello",
      },
    });

    const svg = wrapper.get("svg");
    expect(svg.html()).toContain('fill="var(--paper)"');
    expect(svg.html()).toContain('fill="var(--ink)"');
    expect(svg.html()).toContain('fill="var(--accent)"');
  });
});
