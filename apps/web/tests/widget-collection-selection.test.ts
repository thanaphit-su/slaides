import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { nextTick } from "vue";
import WidgetCollection from "../src/components/WidgetCollection.vue";

vi.mock("../src/api/llm", () => ({
  llmApi: { completeText: vi.fn() },
}));
vi.mock("../src/api/workspace", () => ({
  workspaceApi: {
    get: vi.fn(async () => ({
      id: "ws-1",
      name: "Test",
      llm_base_url: "https://x",
      llm_model: "m-1",
      llm_caps: { widget_generate: true, inline_write: true, interpret: true },
      llm_models: [{ id: "m-1" }],
      llm_capability_models: { widget_generate: "m-1", inline_write: "m-1", interpret: "m-1" },
      llm_key_configured: true,
    })),
  },
}));
vi.mock("../src/api/widgets", () => ({
  widgetsApi: {
    list: vi.fn(async () => []),
    get: vi.fn(async () => null),
    delete: vi.fn(async () => ({})),
  },
}));

import { llmApi } from "../src/api/llm";

const llmMock = vi.mocked(llmApi.completeText);

beforeEach(() => {
  setActivePinia(createPinia());
  llmMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("WidgetCollection — preview-mode selection chip", () => {
  it("renders the selection chip when selectedTarget is provided", async () => {
    const wrapper = mount(WidgetCollection, {
      props: {
        initialTab: "generate",
        selectedTarget: {
          selector: "button.start",
          tag: "button",
          classes: ["start"],
          text: "Start Quiz",
        },
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    const chip = wrapper.find('[data-testid="composer-selection-chip"]');
    expect(chip.exists()).toBe(true);
    expect(chip.text()).toContain("button.start");
    expect(chip.text()).toContain("Start Quiz");
  });

  it("does not render the chip when selectedTarget is null/absent", async () => {
    const wrapper = mount(WidgetCollection, { props: { initialTab: "generate" } });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    expect(wrapper.find('[data-testid="composer-selection-chip"]').exists()).toBe(false);
  });

  it("clicking the chip's clear button emits clear-selected-target", async () => {
    const wrapper = mount(WidgetCollection, {
      props: {
        initialTab: "generate",
        selectedTarget: {
          selector: "button.start",
          tag: "button",
          classes: ["start"],
          text: "Start Quiz",
        },
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    await wrapper.find(".composer-selection-clear").trigger("click");
    expect(wrapper.emitted("clear-selected-target")).toBeTruthy();
  });

  it("send prepends the selection chip text to the LLM prompt", async () => {
    let capturedPrompt = "";
    llmMock.mockImplementation(async (body) => {
      capturedPrompt = body.prompt;
      return "{}";
    });

    const wrapper = mount(WidgetCollection, {
      props: {
        initialTab: "generate",
        selectedTarget: {
          selector: "button.start",
          tag: "button",
          classes: ["start"],
          text: "Start Quiz",
        },
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    const textarea = wrapper.find("textarea.widget-chat-input");
    await textarea.setValue("make it bigger and red");
    await wrapper.find("form.widget-chat-composer").trigger("submit.prevent");
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));

    expect(capturedPrompt).toContain('re: <button.start "Start Quiz">');
    expect(capturedPrompt).toContain("make it bigger and red");
    // Sending also clears the chip.
    expect(wrapper.emitted("clear-selected-target")).toBeTruthy();
  });

  it("renders a Note tab and saves slide presenter notes", async () => {
    const saveNotes = vi.fn(async () => {});
    const wrapper = mount(WidgetCollection, {
      props: {
        initialTab: "note",
        slideNotes: "Opening cue",
        onPatchSlideNotes: saveNotes,
      },
    });

    expect(wrapper.find('[data-testid="widget-tab-note"]').exists()).toBe(true);
    expect((wrapper.find('[data-testid="slide-notes-input"]').element as HTMLTextAreaElement).value).toBe("Opening cue");

    await wrapper.find('[data-testid="slide-notes-input"]').setValue("Updated cue");
    await wrapper.find('[data-testid="slide-notes-save"]').trigger("click");

    expect(saveNotes).toHaveBeenCalledWith("Updated cue");
  });
});
