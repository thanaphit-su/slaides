import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import PresenterRail from "../src/components/PresenterRail.vue";
import type { SessionQuestion } from "../src/api/types";

function question(overrides: Partial<SessionQuestion> = {}): SessionQuestion {
  return {
    id: "q-1",
    slide_id: "slide-1",
    participant_ref: "participant-1",
    anon: false,
    text: "How does pricing work?",
    raised_at: new Date().toISOString(),
    answered_at: null,
    ...overrides,
  };
}

describe("PresenterRail", () => {
  it("shows notes for the current deck slide by default", () => {
    const wrapper = mount(PresenterRail, {
      props: {
        notes: "Mention pilot constraints before Q&A.",
        questions: [question()],
      },
    });

    expect(wrapper.find('[data-testid="presenter-rail-tab-notes"]').classes()).toContain("active");
    expect(wrapper.text()).toContain("Mention pilot constraints before Q&A.");
    expect(wrapper.text()).not.toContain("How does pricing work?");
  });

  it("switches to questions and emits answer actions", async () => {
    const wrapper = mount(PresenterRail, {
      props: {
        notes: "Mention pilot constraints before Q&A.",
        questions: [question()],
      },
    });

    await wrapper.find('[data-testid="presenter-rail-tab-questions"]').trigger("click");
    expect(wrapper.text()).toContain("How does pricing work?");

    await wrapper.find("button.btn").trigger("click");
    expect(wrapper.emitted("answer")).toEqual([["q-1"]]);
  });
});
