import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { nextTick } from "vue";
import WidgetCollection from "../src/components/WidgetCollection.vue";
import { useWidgetsStore } from "../src/stores/widgets";

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
    listForDeck: vi.fn(async () => []),
    listCrossDeck: vi.fn(async () => []),
    get: vi.fn(async () => null),
    delete: vi.fn(async () => ({})),
    remove: vi.fn(async () => ({})),
    createInDeck: vi.fn(async (_deckId: string, body: Record<string, unknown>) => ({
      id: "w-new",
      ...body,
    })),
    copyIntoDeck: vi.fn(async () => ({})),
    patch: vi.fn(async () => ({})),
    getAiThread: vi.fn(async () => null),
    createAiThread: vi.fn(async () => ({
      id: "thread-1",
      widget_id: "w-existing",
      title: null,
      compact_summary: {},
      messages: [],
    })),
    appendAiMessage: vi.fn(async (_widgetId: string, _threadId: string, body: Record<string, unknown>) => ({
      id: "msg-1",
      thread_id: _threadId,
      ...body,
    })),
  },
}));

import { llmApi } from "../src/api/llm";
import { widgetsApi } from "../src/api/widgets";

const llmMock = vi.mocked(llmApi.completeText);
const createInDeckMock = vi.mocked(widgetsApi.createInDeck);
const patchMock = vi.mocked(widgetsApi.patch);
const getAiThreadMock = vi.mocked(widgetsApi.getAiThread);
const appendAiMessageMock = vi.mocked(widgetsApi.appendAiMessage);

async function mountInCreateMode() {
  const wrapper = mount(WidgetCollection, {
    props: { initialTab: "generate", deckId: "deck-1" },
  });
  // Let onMounted (workspace fetch) settle.
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  return wrapper;
}

async function mountInAdjustMode() {
  const store = useWidgetsStore();
  store.cache["w-existing"] = {
    id: "w-existing",
    deck_id: "deck-1",
    derived_from_id: null,
    name: "Existing",
    kind: "custom",
    description: null,
    html: "<section>old</section>",
    js: "",
    css: "",
    props_schema: {},
    tags: [],
    version: "1",
    behavior: { kind: "quiet" },
  };
  const wrapper = mount(WidgetCollection, {
    props: {
      initialTab: "generate",
      mode: "adjust",
      deckId: "deck-1",
      placement: {
        placement_id: "p1",
        widget_id: "w-existing",
        revision_id: null,
        kind: "custom",
        name: "Existing",
        props: {},
      },
    },
  });
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  return wrapper;
}

async function streamCompletion(json: Record<string, unknown> | string) {
  llmMock.mockImplementation(async () =>
    typeof json === "string" ? json : JSON.stringify(json),
  );
}

beforeEach(() => {
  setActivePinia(createPinia());
  llmMock.mockReset();
  createInDeckMock.mockClear();
  patchMock.mockClear();
  getAiThreadMock.mockReset();
  getAiThreadMock.mockResolvedValue(null);
  appendAiMessageMock.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function sendPrompt(wrapper: ReturnType<typeof mount>) {
  const textarea = wrapper.find("textarea.widget-chat-input");
  await textarea.setValue("an audience poll about lunch");
  await wrapper.find("form.widget-chat-composer").trigger("submit.prevent");
  // sendMessage awaits llm + parseDraft.
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
}

async function chooseClarifyFirst(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-testid="widget-workflow-mode-trigger"]').trigger("click");
  await wrapper.get('[data-testid="widget-workflow-mode-clarify"]').trigger("click");
}

describe("WidgetCollection — structured widget workflow", () => {
  it("does not render a behavior picker in create mode", async () => {
    const wrapper = await mountInCreateMode();
    expect(wrapper.find('button[title="Behavior"]').exists()).toBe(false);
  });

  it("renders AI clarification options as a bottom ask-back block", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "question",
      question: "Should this be private or shared?",
      options: [
        { id: "quiet", label: "Private per viewer", value: { behavior: { kind: "quiet" } } },
        { id: "loud", label: "Shared live results", value: { behavior: { kind: "loud" } } },
      ],
    });
    await sendPrompt(wrapper);

    const options = wrapper.find('[data-testid="widget-question-options"]');
    expect(options.exists()).toBe(true);
    expect(options.text()).toContain("Private per viewer");
    expect(options.text()).toContain("Shared live results");
    expect(wrapper.find(".chat-message.assistant [data-testid='widget-question-options']").exists()).toBe(false);
    expect(options.element.parentElement?.classList.contains("widget-chat-thread")).toBe(true);
    expect(wrapper.find(".widget-chat-composer [data-testid='widget-question-options']").exists()).toBe(false);
    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
  });

  it("submits a custom clarification answer from the active question", async () => {
    const wrapper = await mountInCreateMode();
    llmMock
      .mockResolvedValueOnce(JSON.stringify({
        type: "question",
        question: "How should voting work?",
        options: [
          { id: "live", label: "Show results live" },
          { id: "hidden", label: "Hide results until vote" },
        ],
      }))
      .mockResolvedValueOnce(JSON.stringify({
        type: "plan",
        plan: ["Use the custom voting rule"],
        reflection: "I will use the custom answer.",
      }));

    await sendPrompt(wrapper);
    await wrapper.get('[data-testid="widget-question-custom-input"]').setValue("Only reveal results when presenter clicks reveal");
    await wrapper.get('[data-testid="widget-question-custom-form"]').trigger("submit.prevent");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(llmMock).toHaveBeenCalledTimes(2);
    const request = llmMock.mock.calls[1][0] as { prompt: string };
    expect(request.prompt).toContain("Only reveal results when presenter clicks reveal");
    expect(wrapper.find('[data-testid="widget-question-options"]').exists()).toBe(false);
  });

  it("sends Clarify First mode in the widget workflow context", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "question",
      question: "What should the audience submit?",
      options: [{ id: "mood", label: "Mood" }],
    });

    await chooseClarifyFirst(wrapper);
    await sendPrompt(wrapper);

    const request = llmMock.mock.calls[0][0] as { context: Record<string, unknown> };
    expect(request.context.widget_workflow_mode).toBe("clarify_first");
    expect(String(request.context.contract)).toContain("Do not return type=draft");
  });

  it("does not present Clarify First requests as drafting while waiting", async () => {
    const wrapper = await mountInCreateMode();
    let resolveCompletion!: (value: string) => void;
    llmMock.mockImplementation(async () => new Promise<string>((resolve) => {
      resolveCompletion = resolve;
    }));

    await chooseClarifyFirst(wrapper);
    const textarea = wrapper.find("textarea.widget-chat-input");
    await textarea.setValue("a mood poll");
    await wrapper.find("form.widget-chat-composer").trigger("submit.prevent");
    await nextTick();

    expect(wrapper.text()).toContain("Preparing a clarification");
    expect(wrapper.text()).not.toContain("Drafting your widget");

    resolveCompletion(JSON.stringify({
      type: "question",
      question: "How should voting work?",
      options: [{ id: "live", label: "Show results live" }],
    }));
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
  });

  it("stops Clarify First streaming when the model starts returning a draft", async () => {
    const wrapper = await mountInCreateMode();
    let abortedAfterDraftToken = false;
    llmMock.mockImplementation(async (_body, opts) => {
      opts?.onToken?.('{"type":"draft","widget":');
      abortedAfterDraftToken = !!opts?.signal?.aborted;
      if (opts?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      return JSON.stringify({
        type: "draft",
        widget: {
          name: "Mood Poll",
          kind: "poll",
          html: "<section>poll</section>",
          js: "",
          css: "",
          props_schema: {},
          tags: [],
        },
      });
    });

    await chooseClarifyFirst(wrapper);
    await sendPrompt(wrapper);

    expect(abortedAfterDraftToken).toBe(true);
    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
    const options = wrapper.get('[data-testid="widget-question-options"]');
    expect(options.text()).toContain("Build now");
    expect(options.text()).toContain("Clarify more");
  });

  it("does not show a draft when Clarify First mode receives a draft response", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "draft",
      widget: {
        name: "Lunch Poll",
        kind: "poll",
        html: "<section>poll</section>",
        js: "",
        css: "",
        props_schema: {},
        tags: [],
      },
      ai_spec: { intent: "poll" },
      example_props: {},
    });

    await chooseClarifyFirst(wrapper);
    await sendPrompt(wrapper);

    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
    const options = wrapper.get('[data-testid="widget-question-options"]');
    expect(options.text()).toContain("Build now");
    expect(options.text()).toContain("Clarify more");
  });

  it("renders workflow mode as a compact composer toolbar menu", async () => {
    const wrapper = await mountInCreateMode();

    expect(wrapper.find(".widget-workflow-mode").exists()).toBe(false);
    const trigger = wrapper.get('[data-testid="widget-workflow-mode-trigger"]');
    expect(trigger.text()).toContain("Build now");

    await trigger.trigger("click");

    const menu = wrapper.get('[data-testid="widget-workflow-mode-menu"]');
    expect(menu.text()).toContain("Clarify first");
    expect(menu.text()).toContain("Build now");
  });

  it("renders standalone plan envelopes as workflow progress", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "plan",
      plan: ["inspect current spec", "draft source"],
      reflection: "Need one more pass before drafting.",
    });
    await sendPrompt(wrapper);

    expect(wrapper.text()).toContain("inspect current spec");
    expect(wrapper.text()).toContain("Need one more pass before drafting.");
    expect(wrapper.text()).not.toContain("AI response was not a valid widget workflow.");
  });

  it("fails closed when the model returns legacy flat widget JSON", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      name: "Word cloud",
      kind: "custom",
      description: "x",
      html: "<section>cloud</section>",
      js: "",
      css: "",
      props_schema: {},
      tags: [],
    });
    await sendPrompt(wrapper);

    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
    expect(wrapper.text()).toContain("AI returned an invalid widget workflow response.");
    expect(createInDeckMock).not.toHaveBeenCalled();
  });

  it("self-repairs an invalid workflow response before showing the draft", async () => {
    const wrapper = await mountInCreateMode();
    llmMock
      .mockResolvedValueOnce(JSON.stringify({
        name: "Word cloud",
        html: "<section>legacy</section>",
      }))
      .mockResolvedValueOnce(JSON.stringify({
        type: "draft",
        widget: {
          name: "Word cloud",
          kind: "wordcloud",
          description: "x",
          html: "<section>cloud</section>",
          js: "",
          css: "",
          props_schema: {},
          tags: [],
        },
      }));

    await sendPrompt(wrapper);

    expect(llmMock).toHaveBeenCalledTimes(2);
    const repairRequest = llmMock.mock.calls[1][0] as { prompt: string; context: Record<string, unknown> };
    expect(repairRequest.prompt).toContain("Repair the previous widget response");
    expect(String(repairRequest.context.repair_error)).toContain("workflow response type");
    expect(wrapper.find(".widget-preview-card").exists()).toBe(true);
    expect(wrapper.text()).toContain("Word cloud");
  });

  it("self-repairs broken draft JavaScript before rendering a preview", async () => {
    const wrapper = await mountInCreateMode();
    llmMock
      .mockResolvedValueOnce(JSON.stringify({
        type: "draft",
        widget: {
          name: "Broken JS",
          kind: "custom",
          description: "x",
          html: "<section>broken</section>",
          js: "function () {",
          css: "",
          props_schema: {},
          tags: [],
        },
      }))
      .mockResolvedValueOnce(JSON.stringify({
        type: "draft",
        widget: {
          name: "Fixed JS",
          kind: "custom",
          description: "x",
          html: "<section>fixed</section>",
          js: "function init() { return true; }",
          css: "",
          props_schema: {},
          tags: [],
        },
      }));

    await sendPrompt(wrapper);

    expect(llmMock).toHaveBeenCalledTimes(2);
    expect(wrapper.find(".widget-preview-card").exists()).toBe(true);
    expect(wrapper.text()).toContain("Fixed JS");
    expect(wrapper.text()).not.toContain("AI JS has a syntax error");
  });

  it("stops self-repair after 3 attempts for one message", async () => {
    const wrapper = await mountInCreateMode();
    llmMock.mockResolvedValue(JSON.stringify({
      name: "Still legacy",
      html: "<section>legacy</section>",
    }));

    await sendPrompt(wrapper);

    expect(llmMock).toHaveBeenCalledTimes(3);
    expect(wrapper.find(".widget-preview-card").exists()).toBe(false);
    expect(wrapper.text()).toContain("AI returned an invalid widget workflow response.");
  });

  it("persists a valid draft envelope with behavior block", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "draft",
      plan: ["choose behavior"],
      reflection: "Uses props for copy.",
      widget: {
        name: "Quiz",
        kind: "quiz",
        description: "x",
        html: "<section>quiz</section>",
        js: "window.slaides.contribute('a');",
        css: "",
        props_schema: {},
        tags: [],
        behavior: {
          kind: "loud",
          aggregator: "keyed_tally",
          contribution_schema: { type: "string" },
        },
      },
      ai_spec: { intent: "quiz" },
      example_props: { title: "Lunch quiz" },
    });
    await sendPrompt(wrapper);

    await wrapper.find(".widget-preview-insert").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    const body = createInDeckMock.mock.calls[0][1] as Record<string, unknown>;
    expect((body.behavior as Record<string, unknown>).aggregator).toBe("keyed_tally");
    expect(body.ai_spec).toEqual({ intent: "quiz" });
    expect(body.example_props).toEqual({ title: "Lunch quiz" });
    expect(appendAiMessageMock).toHaveBeenCalledWith(
      "w-new",
      "thread-1",
      expect.objectContaining({
        role: "user",
        message_type: "user",
      }),
    );
    expect(appendAiMessageMock).toHaveBeenCalledWith(
      "w-new",
      "thread-1",
      expect.objectContaining({
        role: "assistant",
        message_type: "draft",
      }),
    );
  });

  it("hydrates persisted AI thread in adjust mode", async () => {
    getAiThreadMock.mockResolvedValue({
      id: "thread-1",
      widget_id: "w-existing",
      title: "Existing thread",
      compact_summary: { intent: "loaded" },
      messages: [
        {
          id: "m-user",
          thread_id: "thread-1",
          role: "user",
          message_type: "user",
          content: { text: "Make it shared" },
          revision_id: null,
        },
        {
          id: "m-plan",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "plan",
          content: { plan: ["switch behavior"], reflection: "Will use tally." },
          revision_id: "rev-1",
        },
      ],
    });

    const wrapper = await mountInAdjustMode();

    expect(wrapper.text()).toContain("Make it shared");
    expect(wrapper.text()).toContain("switch behavior");
    expect(wrapper.text()).toContain("Will use tally.");
  });

  it("hydrates apply records as compact draft references, not duplicate previews", async () => {
    getAiThreadMock.mockResolvedValue({
      id: "thread-1",
      widget_id: "w-existing",
      title: "Existing thread",
      compact_summary: {},
      messages: [
        {
          id: "m-draft",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "draft",
          content: {
            text: "Here's an adjustment.",
            widget: { html: "<section>draft</section>", css: "", js: "", kind: "custom" },
          },
          revision_id: "rev-1",
        },
        {
          id: "m-apply",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "apply",
          content: {
            text: "Applied to the widget.",
            widget: { html: "<section>draft</section>", css: "", js: "", kind: "custom" },
            applied_from_draft_number: 1,
          },
          revision_id: "rev-2",
        },
      ],
    });

    const wrapper = await mountInAdjustMode();

    expect(wrapper.findAll(".widget-preview-card")).toHaveLength(1);
    const applied = wrapper.get('[data-testid="widget-applied-reference"]');
    expect(applied.text()).toContain("Applied to the widget from Draft #1");
  });

  it("does not restore stale clarification options after a later draft is applied", async () => {
    getAiThreadMock.mockResolvedValue({
      id: "thread-1",
      widget_id: "w-existing",
      title: "Existing thread",
      compact_summary: {},
      messages: [
        {
          id: "m-question",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "question",
          content: {
            question: "Clarify First is on. Build from this direction now, or clarify one more detail first?",
            options: [
              { id: "build_now", label: "Build now", value: { workflow_mode: "build_now" } },
              { id: "clarify_more", label: "Clarify more", value: { workflow_mode: "clarify_first" } },
            ],
          },
          revision_id: "rev-1",
        },
        {
          id: "m-user",
          thread_id: "thread-1",
          role: "user",
          message_type: "user",
          content: { text: "Choose: Build now" },
          revision_id: null,
        },
        {
          id: "m-draft",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "draft",
          content: {
            text: "Here's an adjustment.",
            widget: { html: "<section>draft</section>", css: "", js: "", kind: "custom" },
          },
          revision_id: "rev-1",
        },
        {
          id: "m-apply",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "apply",
          content: { text: "Applied to the widget.", applied_from_draft_number: 1 },
          revision_id: "rev-2",
        },
      ],
    });

    const wrapper = await mountInAdjustMode();

    expect(wrapper.find('[data-testid="widget-question-options"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("Applied to the widget from Draft #1");
  });

  it("clicking an applied draft reference scrolls to the original draft", async () => {
    getAiThreadMock.mockResolvedValue({
      id: "thread-1",
      widget_id: "w-existing",
      title: "Existing thread",
      compact_summary: {},
      messages: [
        {
          id: "m-draft",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "draft",
          content: {
            text: "Here's an adjustment.",
            widget: { html: "<section>draft</section>", css: "", js: "", kind: "custom" },
          },
          revision_id: "rev-1",
        },
        {
          id: "m-apply",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "apply",
          content: { text: "Applied to the widget.", applied_from_draft_number: 1 },
          revision_id: "rev-2",
        },
      ],
    });
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    const wrapper = await mountInAdjustMode();

    await wrapper.get('[data-testid="widget-applied-reference-button"]').trigger("click");

    expect(scrollSpy).toHaveBeenCalled();
  });

  it("keeps persisted AI thread when placement props refresh for the same widget", async () => {
    getAiThreadMock.mockResolvedValue({
      id: "thread-1",
      widget_id: "w-existing",
      title: "Existing thread",
      compact_summary: { intent: "loaded" },
      messages: [
        {
          id: "m-user",
          thread_id: "thread-1",
          role: "user",
          message_type: "user",
          content: { text: "Make it shared" },
          revision_id: null,
        },
        {
          id: "m-plan",
          thread_id: "thread-1",
          role: "assistant",
          message_type: "plan",
          content: { plan: ["switch behavior"], reflection: "Will use tally." },
          revision_id: "rev-1",
        },
      ],
    });
    const wrapper = await mountInAdjustMode();
    expect(wrapper.text()).toContain("Make it shared");

    await wrapper.setProps({
      placement: {
        placement_id: "p1",
        widget_id: "w-existing",
        revision_id: null,
        kind: "custom",
        name: "Existing",
        props: { title: "Updated title" },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Make it shared");
    expect(wrapper.text()).toContain("switch behavior");
    expect(wrapper.text()).toContain("Will use tally.");
  });

  it("persists adjust apply messages to the widget AI thread", async () => {
    const wrapper = await mountInAdjustMode();
    patchMock.mockResolvedValue({
      id: "w-existing",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Existing",
      kind: "custom",
      description: null,
      html: "<section><p>new adjusted widget content</p></section>",
      js: "",
      css: "",
      props_schema: {},
      tags: [],
      version: "1",
      behavior: { kind: "loud", aggregator: "tally", contribution_schema: { type: "string" } },
      current_revision_id: "rev-2",
      example_props: {},
      ai_spec: { intent: "shared" },
    });
    await streamCompletion({
      type: "draft",
      widget: {
        behavior: { kind: "loud", aggregator: "tally", contribution_schema: { type: "string" } },
      },
      ai_spec: { intent: "shared" },
      example_props: {},
    });
    await sendPrompt(wrapper);

    await wrapper.find(".widget-preview-insert").trigger("click");
    await new Promise((r) => setTimeout(r, 0));

    expect(appendAiMessageMock).toHaveBeenCalledWith(
      "w-existing",
      "thread-1",
      expect.objectContaining({
        role: "assistant",
        message_type: "apply",
        revision_id: "rev-2",
      }),
    );
    const applyCall = appendAiMessageMock.mock.calls.find((call) => {
      const body = call[2] as Record<string, unknown>;
      return body.message_type === "apply";
    });
    const content = applyCall?.[2].content as Record<string, unknown>;
    expect(content).toEqual({
      text: "Applied to the widget.",
      applied_from_draft_number: 1,
      applied_from_message_id: expect.any(String),
    });
    expect(content.widget).toBeUndefined();
  });

  it("clears adjust apply button state after the widget patch succeeds even if thread history stalls", async () => {
    const wrapper = await mountInAdjustMode();
    patchMock.mockResolvedValue({
      id: "w-existing",
      deck_id: "deck-1",
      derived_from_id: null,
      name: "Existing",
      kind: "custom",
      description: null,
      html: "<section>new</section>",
      js: "",
      css: "",
      props_schema: {},
      tags: [],
      version: "1",
      behavior: { kind: "quiet" },
      current_revision_id: "rev-2",
      example_props: {},
      ai_spec: {},
    });
    appendAiMessageMock.mockImplementation(async (_widgetId, threadId, body) => {
      if (body.message_type === "apply") {
        return new Promise(() => {});
      }
      return {
        id: `msg-${body.message_type}`,
        thread_id: threadId,
        ...body,
        revision_id: body.revision_id ?? null,
      };
    });
    await streamCompletion({
      type: "draft",
      widget: {
        html: "<section><p>new adjusted widget content</p></section>",
      },
    });
    await sendPrompt(wrapper);

    await wrapper.find(".widget-preview-insert").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(appendAiMessageMock.mock.calls.some((call) => call[2]?.message_type === "apply")).toBe(true);
    const buttonTexts = wrapper.findAll(".widget-preview-insert").map((button) => button.text());
    expect(buttonTexts.some((text) => text.includes("applying"))).toBe(false);
    expect(wrapper.find(".widget-preview-applied-chip").exists()).toBe(true);
  });

  it("renders backend validator warnings inline with the draft preview", async () => {
    const wrapper = await mountInCreateMode();
    llmMock.mockImplementation(async (_body, opts) => {
      opts?.onWarnings?.([
        "Loud widget never calls slaides.contribute() — the audience can't actually contribute to the shared state.",
        "Widget declared props_schema but never reads window.slaides.props.",
      ]);
      return JSON.stringify({
        type: "draft",
        widget: {
          name: "Broken loud",
          kind: "poll",
          description: "x",
          html: "<section>x</section>",
          js: "",
          css: "",
          props_schema: { properties: { q: { type: "string" } } },
          tags: [],
          behavior: {
            kind: "loud",
            aggregator: "tally",
            contribution_schema: { type: "string" },
          },
        },
      });
    });
    await sendPrompt(wrapper);

    const warningsList = wrapper.find('[data-testid="validator-warnings"]');
    expect(warningsList.exists()).toBe(true);
    const items = warningsList.findAll("li");
    expect(items.length).toBe(2);
    expect(items[0].text()).toContain("never calls slaides.contribute");
    expect(items[1].text()).toContain("never reads window.slaides.props");
  });

  it("does not render the validator-warnings list when there are no warnings", async () => {
    const wrapper = await mountInCreateMode();
    await streamCompletion({
      type: "draft",
      widget: {
        name: "Clean",
        kind: "custom",
        description: "x",
        html: "<section>ok</section>",
        js: "",
        css: "",
        props_schema: {},
        tags: [],
      },
    });
    await sendPrompt(wrapper);
    expect(wrapper.find('[data-testid="validator-warnings"]').exists()).toBe(false);
  });

  it("does not invent behavior when a draft envelope omits it", async () => {
    const wrapper = await mountInCreateMode();
    // Leave behavior at Quiet (default).
    await streamCompletion({
      type: "draft",
      widget: {
        name: "Flashcards",
        kind: "custom",
        description: "x",
        html: "<section>card</section>",
        js: "",
        css: "",
        props_schema: {},
        tags: [],
      },
    });
    await sendPrompt(wrapper);

    await wrapper.find(".widget-preview-insert").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    const body = createInDeckMock.mock.calls[0][1] as Record<string, unknown>;
    expect(body.behavior).toBeUndefined();
  });

  it("allows adjust mode to send an explicit behavior swap", async () => {
    const wrapper = await mountInAdjustMode();
    await streamCompletion({
      type: "draft",
      widget: {
        behavior: {
          kind: "loud",
          aggregator: "append",
          contribution_schema: { type: "object" },
        },
        js: "window.slaides.contribute({ text: 'hello' });",
      },
    });
    await sendPrompt(wrapper);

    await wrapper.find(".widget-preview-insert").trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    expect(patchMock).toHaveBeenCalledTimes(1);
    const body = patchMock.mock.calls[0][1] as Record<string, unknown>;
    expect(body.behavior).toEqual({
      kind: "loud",
      aggregator: "append",
      contribution_schema: { type: "object" },
    });
  });
});
