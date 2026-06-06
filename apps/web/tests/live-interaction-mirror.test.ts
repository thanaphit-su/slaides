import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import LivePollSlide from "../src/components/LivePollSlide.vue";
import LiveQuestionSlide from "../src/components/LiveQuestionSlide.vue";
import LiveRandomAudienceSlide from "../src/components/LiveRandomAudienceSlide.vue";
import type { SessionSlide } from "../src/api/types";

function baseSlide(overrides: Partial<SessionSlide> = {}): SessionSlide {
  return {
    id: "ss-1",
    session_id: "sess-1",
    parent_slide_id: "slide-1",
    widget_id: null,
    position: 0,
    kind: "poll",
    spec: {},
    results: {},
    inverted_theme: false,
    opened_at: "2026-06-06T00:00:00Z",
    closed_at: null,
    ...overrides,
  };
}

describe("live interaction mirror role", () => {
  it("renders poll results without vote buttons or presenter controls", () => {
    setActivePinia(createPinia());
    const wrapper = mount(LivePollSlide, {
      props: {
        role: "mirror",
        inverted: false,
        slide: baseSlide({
          spec: {
            type: "poll",
            question: "Pick one",
            choices: [
              { id: "a", label: "A" },
              { id: "b", label: "B" },
            ],
            config: { allow_other: true, show_results_live: true, anonymous: true },
            state: { voting_closed: false, choices_locked: false },
          },
          results: { tally: { a: 2 }, voters: 2 },
        }),
      },
    });

    expect(wrapper.text()).toContain("Pick one");
    expect(wrapper.find(".choice-readout").exists()).toBe(true);
    expect(wrapper.find(".choice-btn").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Presenter controls");
    expect(wrapper.text()).not.toContain("Other");
  });

  it("renders promoted question answers without answer input or presenter controls", () => {
    setActivePinia(createPinia());
    const wrapper = mount(LiveQuestionSlide, {
      props: {
        role: "mirror",
        inverted: false,
        slide: baseSlide({
          kind: "question",
          spec: { type: "question", prompt: "What changed?", config: { anonymous: true } },
          results: {
            total_answers: 2,
            promoted: [{ id: "a-1", text: "The scope", display_name: "Ada", anon: false }],
          },
        }),
      },
    });

    expect(wrapper.text()).toContain("What changed?");
    expect(wrapper.text()).toContain("The scope");
    expect(wrapper.find("textarea").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Save to library");
  });

  it("shows random audience picks like presenter view", () => {
    const wrapper = mount(LiveRandomAudienceSlide, {
      props: {
        role: "mirror",
        inverted: false,
        slide: baseSlide({
          kind: "random",
          spec: { type: "random", count: 1 },
          results: {
            requested_count: 1,
            eligible_count: 5,
            picked: [{ participant_ref: "participant-123456", display_name: "Lin", anon: false }],
          },
        }),
      },
    });

    expect(wrapper.text()).toContain("Lin");
    expect(wrapper.text()).not.toContain("The presenter is running a room activity.");
  });
});
