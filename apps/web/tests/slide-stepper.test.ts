import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { Slide } from "@/api/types";
import SlideStepper from "@/components/SlideStepper.vue";

function slide(index: number): Slide {
  return {
    id: `slide-${index}`,
    deck_id: "deck-1",
    section_id: null,
    position: index - 1,
    kicker: null,
    markdown: `# Slide ${index}`,
    updated_at: "2026-06-07T00:00:00Z",
    widgets: [],
  };
}

describe("SlideStepper", () => {
  it("uses a seven-dot fading window for long decks", async () => {
    const slides = Array.from({ length: 46 }, (_, index) => slide(index + 1));
    const wrapper = mount(SlideStepper, {
      props: {
        slides,
        activeSlideId: "slide-12",
      },
      global: {
        stubs: {
          Icon: true,
        },
      },
    });

    const window = wrapper.get('[data-testid="editor-slide-stepper-window"]');
    const dots = window.findAll('[data-testid="editor-slide-stepper-dot"]');
    expect(dots).toHaveLength(7);
    expect(window.find('[data-testid="editor-slide-stepper-fade-left"]').exists()).toBe(true);
    expect(window.find('[data-testid="editor-slide-stepper-fade-right"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("12 / 46");

    await dots[0].trigger("click");

    expect(wrapper.emitted("select")?.[0]).toEqual(["slide-9"]);
  });

  it("only shows the trailing fade near the start of a long deck", () => {
    const slides = Array.from({ length: 46 }, (_, index) => slide(index + 1));
    const wrapper = mount(SlideStepper, {
      props: {
        slides,
        activeSlideId: "slide-1",
      },
      global: {
        stubs: {
          Icon: true,
        },
      },
    });

    const window = wrapper.get('[data-testid="editor-slide-stepper-window"]');
    expect(window.find('[data-testid="editor-slide-stepper-fade-left"]').exists()).toBe(false);
    expect(window.find('[data-testid="editor-slide-stepper-fade-right"]').exists()).toBe(true);
  });
});
