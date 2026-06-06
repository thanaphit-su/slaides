import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsDrawer from "../src/components/SettingsDrawer.vue";
import { workspaceApi } from "../src/api/workspace";
import type { Workspace } from "../src/api/types";

vi.mock("../src/api/workspace", () => ({
  workspaceApi: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

function workspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    id: "workspace-1",
    name: "Test",
    llm_base_url: "https://api.openai.com/v1",
    llm_model: "gpt-4.1-mini",
    llm_caps: { inline_write: true, interpret: true, widget_generate: true },
    llm_models: [{ id: "gpt-4.1-mini", supports_image_input: false }],
    llm_capability_models: {
      inline_write: "gpt-4.1-mini",
      interpret: "gpt-4.1-mini",
      widget_generate: "gpt-4.1-mini",
    },
    llm_key_configured: false,
    interpret_quick_options: [
      { label: "AI", instruction: "in plain English" },
      { label: "Simple definition", instruction: "show a simple definition" },
      { label: "Why it matters", instruction: "explain why this matters for this slide" },
    ],
    log_llm_prompts_for_transcript: false,
    ...overrides,
  };
}

describe("SettingsDrawer session settings", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    localStorage.clear();
    document.documentElement.classList.remove("dark", "light");
  });

  it("saves quick options before emitting start-session", async () => {
    const original = workspace();
    const saved = workspace({
      interpret_quick_options: [{ label: "Define", instruction: "show a simple definition" }],
    });
    vi.mocked(workspaceApi.get).mockResolvedValue(original);
    vi.mocked(workspaceApi.patch).mockResolvedValue(saved);

    const wrapper = mount(SettingsDrawer, {
      props: { open: true, canStartSession: true },
      global: { stubs: { Teleport: true, Toggle: true } },
    });
    await flushPromises();

    await wrapper.findAll(".settings-tabs button").find((button) => button.text() === "Session")!.trigger("click");
    const inputs = wrapper.findAll(".quick-option-row input");
    await inputs[0].setValue("Define");
    await inputs[1].setValue("show a simple definition");
    await wrapper.find("button.btn-primary").trigger("click");
    await flushPromises();

    expect(workspaceApi.patch).toHaveBeenCalledWith(
      expect.objectContaining({
        interpret_quick_options: expect.arrayContaining([
          { label: "Define", instruction: "show a simple definition" },
        ]),
      }),
    );
    expect(wrapper.emitted("saved")?.[0]).toEqual([saved]);
    expect(wrapper.emitted("start-session")).toHaveLength(1);
  });

  it("changes theme mode from the Display tab", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue(workspace());

    const wrapper = mount(SettingsDrawer, {
      props: { open: true, userName: "Instructor", userEmail: "instructor@example.com" },
      global: { stubs: { Teleport: true, Toggle: true } },
    });
    await flushPromises();

    await wrapper.findAll(".settings-tabs button").find((button) => button.text() === "Display")!.trigger("click");
    await wrapper.get('[data-testid="theme-mode-dark"]').trigger("click");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("slaides:theme-mode")).toBe("dark");
  });

  it("emits mirror access saves for owner and link modes", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue(workspace());

    const wrapper = mount(SettingsDrawer, {
      props: {
        open: true,
        mirrorAccess: { mode: "owner", allowed_emails: [] },
      },
      global: { stubs: { Teleport: true, Toggle: true } },
    });
    await flushPromises();

    await wrapper.findAll(".settings-tabs button").find((button) => button.text() === "Session")!.trigger("click");
    await wrapper.findAll(".mirror-mode-option").find((button) => button.text().includes("Only owner"))!.trigger("click");
    await wrapper.get('[data-testid="mirror-access-settings"] .settings-actions button').trigger("click");
    await wrapper.findAll(".mirror-mode-option").find((button) => button.text().includes("Anyone with link"))!.trigger("click");
    await wrapper.get('[data-testid="mirror-access-settings"] .settings-actions button').trigger("click");

    expect(wrapper.emitted("save-mirror-access")).toEqual([
      [{ mode: "owner", allowed_emails: [] }],
      [{ mode: "link", allowed_emails: [] }],
    ]);
  });

  it("normalizes allowed mirror emails and displays normalized saved props", async () => {
    vi.mocked(workspaceApi.get).mockResolvedValue(workspace());

    const wrapper = mount(SettingsDrawer, {
      props: {
        open: true,
        mirrorAccess: { mode: "allowed", allowed_emails: ["existing@example.com"] },
      },
      global: { stubs: { Teleport: true, Toggle: true } },
    });
    await flushPromises();

    await wrapper.findAll(".settings-tabs button").find((button) => button.text() === "Session")!.trigger("click");
    const textarea = wrapper.get<HTMLTextAreaElement>(".mirror-email-input");
    await textarea.setValue(" Ada@Example.com, bob@example.com\nada@example.com ");
    await wrapper.get('[data-testid="mirror-access-settings"] .settings-actions button').trigger("click");

    expect(wrapper.emitted("save-mirror-access")?.[0]).toEqual([
      {
        mode: "allowed",
        allowed_emails: ["ada@example.com", "bob@example.com"],
      },
    ]);

    await wrapper.setProps({
      mirrorAccess: {
        mode: "allowed",
        allowed_emails: ["ada@example.com", "bob@example.com"],
      },
    });

    expect((wrapper.get(".mirror-email-input").element as HTMLTextAreaElement).value).toBe(
      "ada@example.com\nbob@example.com",
    );
  });
});
