import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { nextTick } from "vue";
import WidgetCollection from "../src/components/WidgetCollection.vue";
import { ApiError } from "../src/api/client";

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
    getAs: vi.fn(async () => null),
    delete: vi.fn(async () => ({})),
    remove: vi.fn(async () => ({})),
    createInDeck: vi.fn(async () => ({ id: "w-new" })),
    copyIntoDeck: vi.fn(async () => ({})),
    patch: vi.fn(),
    patchPlacementProps: vi.fn(),
  },
}));

import { widgetsApi } from "../src/api/widgets";

const patchMock = vi.mocked(widgetsApi.patch);
const widgetGet = vi.mocked(widgetsApi.get);

beforeEach(() => {
  setActivePinia(createPinia());
  patchMock.mockReset();
  widgetGet.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const fakeWidget = {
  id: "wid-1",
  deck_id: "deck-1",
  name: "Live poll",
  kind: "poll",
  description: "x",
  html: "<section>p</section>",
  js: "",
  css: "",
  props_schema: {},
  tags: [],
  version: 1,
  behavior: { kind: "loud", aggregator: "tally", contribution_schema: { type: "string" } },
};

const placement = {
  placement_id: "live-1",
  widget_id: "wid-1",
  kind: "poll",
  name: "Live poll",
  props: {},
  position: 0,
};

async function mountInAdjustMode() {
  widgetGet.mockResolvedValue(fakeWidget as never);
  const wrapper = mount(WidgetCollection, {
    props: {
      mode: "adjust",
      placement: placement as never,
      deckId: "deck-1",
    },
  });
  // Let onMounted (workspace + widget fetch) settle.
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  return wrapper;
}

describe("WidgetCollection — reset-confirm modal", () => {
  it("opens the modal on 409 edit_requires_reset and retries with resetState on confirm", async () => {
    const wrapper = await mountInAdjustMode();

    // Make the first patch call return 409, the second (resetState=true) succeed.
    patchMock.mockImplementation(async (_id, _body, opts) => {
      if (opts?.resetState) {
        return { ...fakeWidget, html: "<section>edited</section>" } as never;
      }
      throw new ApiError(409, "edit_requires_reset", {
        detail: {
          error: "edit_requires_reset",
          open_session_count: 2,
          open_placement_count: 3,
          message: "live",
        },
      });
    });

    // Open code tab + edit + save.
    const codeTabBtn = wrapper.findAll(".widget-tab-strip button").find((b) => b.text() === "Code");
    expect(codeTabBtn).toBeTruthy();
    await codeTabBtn!.trigger("click");
    await nextTick();
    const textarea = wrapper.find("textarea.widget-code-body");
    await textarea.setValue("<section>edited</section>");
    await nextTick();
    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save");
    expect(saveBtn).toBeTruthy();
    await saveBtn!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    // First call rejected → modal appears.
    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(patchMock.mock.calls[0][2]).toEqual({});
    const modal = wrapper.find('[data-testid="reset-confirm-modal"]');
    expect(modal.exists()).toBe(true);
    expect(modal.text()).toContain("2 sessions");
    expect(modal.text()).toContain("3 placements");

    // Confirm — modal closes and second call ran with resetState=true.
    await wrapper.find('[data-testid="reset-confirm-button"]').trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();
    expect(patchMock).toHaveBeenCalledTimes(2);
    expect(patchMock.mock.calls[1][2]).toEqual({ resetState: true });
    expect(wrapper.find('[data-testid="reset-confirm-modal"]').exists()).toBe(false);
  });

  it("cancelling the modal does not retry and surfaces the error", async () => {
    const wrapper = await mountInAdjustMode();
    patchMock.mockImplementation(async (_id, _body, _opts) => {
      throw new ApiError(409, "edit_requires_reset", {
        detail: { error: "edit_requires_reset", open_session_count: 1, open_placement_count: 1 },
      });
    });

    const codeTabBtn = wrapper.findAll(".widget-tab-strip button").find((b) => b.text() === "Code");
    await codeTabBtn!.trigger("click");
    await nextTick();
    await wrapper.find("textarea.widget-code-body").setValue("<section>x</section>");
    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save");
    await saveBtn!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(wrapper.find('[data-testid="reset-confirm-modal"]').exists()).toBe(true);
    // Click Cancel.
    const cancelBtn = wrapper.findAll('[data-testid="reset-confirm-modal"] button').find((b) => b.text() === "Cancel");
    await cancelBtn!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(wrapper.find('[data-testid="reset-confirm-modal"]').exists()).toBe(false);
  });

  it("non-409 errors bypass the modal and propagate as plain errors", async () => {
    const wrapper = await mountInAdjustMode();
    patchMock.mockRejectedValue(new ApiError(500, "boom", {}));

    const codeTabBtn = wrapper.findAll(".widget-tab-strip button").find((b) => b.text() === "Code");
    await codeTabBtn!.trigger("click");
    await nextTick();
    await wrapper.find("textarea.widget-code-body").setValue("<section>x</section>");
    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save");
    await saveBtn!.trigger("click");
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(wrapper.find('[data-testid="reset-confirm-modal"]').exists()).toBe(false);
    expect(patchMock).toHaveBeenCalledTimes(1);
  });
});
