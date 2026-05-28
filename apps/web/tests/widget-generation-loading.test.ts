import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { nextTick } from "vue";
import WidgetCollection from "../src/components/WidgetCollection.vue";

vi.mock("../src/api/llm", () => ({
  llmApi: {
    completeText: vi.fn(),
  },
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

describe("WidgetCollection — generation loading feedback", () => {
  it("shows an animated grip before the drafting message while the model is responding", async () => {
    // Capture the callbacks so we can drive streaming from the test.
    let resolveCompletion!: (text: string) => void;
    let capturedOnToken: ((delta: string) => void) | undefined;
    llmMock.mockImplementation(async (_body, opts) => {
      capturedOnToken = opts?.onToken;
      return await new Promise<string>((res) => {
        resolveCompletion = res;
      });
    });

    const wrapper = mount(WidgetCollection, { props: { initialTab: "generate" } });
    // Let onMounted promises (workspace fetch) settle.
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    const textarea = wrapper.find("textarea.widget-chat-input");
    await textarea.setValue("Make a poll with two options");
    const form = wrapper.find("form.widget-chat-composer");
    await form.trigger("submit.prevent");
    await nextTick();

    // Right after submit, before any tokens have streamed: the animated grip should
    // be visible, no preview card yet, and the waiting-meta string should
    // appear (since streamedChars is still 0).
    expect(wrapper.find('[data-testid="chat-loading-grip"]').exists()).toBe(true);
    expect(wrapper.find(".chat-typing").exists()).toBe(false);
    expect(wrapper.html().indexOf('data-testid="chat-loading-grip"')).toBeLessThan(
      wrapper.html().indexOf("Drafting your widget"),
    );
    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
    expect(wrapper.text()).toContain("Waiting for the model to start");

    // Stream a few chunks. The progress line should flip to a character count
    // and the .chat-stream-tail preview should appear.
    expect(capturedOnToken).toBeTypeOf("function");
    capturedOnToken!("{\"name\":\"Poll\",");
    capturedOnToken!("\"kind\":\"poll\",\"html\":\"<section>...");
    await nextTick();

    expect(wrapper.text()).toContain("Streaming widget source");
    expect(wrapper.find(".chat-stream-tail").exists()).toBe(true);
    expect(wrapper.find(".chat-stream-tail").text()).toContain("poll");

    // Resolve completion: streaming UI should clear; the grip and tail
    // disappear.
    resolveCompletion(
      JSON.stringify({
        type: "draft",
        widget: {
          name: "Poll",
          kind: "poll",
          description: "Two options",
          html: "<section><p>x</p></section>",
          js: "",
          css: "",
          props_schema: {},
          tags: [],
        },
        ai_spec: { intent: "two option poll" },
        example_props: {},
      }),
    );
    // Allow the .then/await chain inside sendMessage to settle.
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(wrapper.find('[data-testid="chat-loading-grip"]').exists()).toBe(false);
    expect(wrapper.find(".chat-stream-tail").exists()).toBe(false);
    expect(wrapper.find(".widget-preview-card").exists()).toBe(true);
  });

  it("renders draft previews with the shared widget theme tokens", async () => {
    llmMock.mockResolvedValue(
      JSON.stringify({
        type: "draft",
        widget: {
          name: "Mood",
          kind: "poll",
          description: "Mood picker",
          html: "<section class='mood'>Mood check</section>",
          js: "",
          css: ".mood { background: var(--card); color: var(--card-foreground); font-family: var(--font-serif); }",
          props_schema: {},
          tags: [],
        },
        ai_spec: { intent: "mood check" },
        example_props: {},
      }),
    );

    const wrapper = mount(WidgetCollection, { props: { initialTab: "generate" } });
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    await wrapper.find("textarea.widget-chat-input").setValue("Make a mood widget");
    await wrapper.find("form.widget-chat-composer").trigger("submit.prevent");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    const srcdoc = wrapper.find(".widget-preview-card iframe").attributes("srcdoc") || "";
    expect(srcdoc).toContain("--card:");
    expect(srcdoc).toContain("--font-serif:");
    expect(srcdoc).toContain("background: var(--card)");
  });
});
