import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { authApi } from "@/api/auth";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import Workspace from "@/pages/Workspace.vue";
import { useAuthStore } from "@/stores/auth";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useRoute: () => ({ query: {} }),
}));

vi.mock("@/api/auth", () => ({
  authApi: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    me: vi.fn(),
  },
}));

vi.mock("@/api/decks", () => ({
  decksApi: {
    list: vi.fn(),
    create: vi.fn(),
    importDeck: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("@/api/sessions", () => ({
  sessionsApi: {
    list: vi.fn(),
    guestJoin: vi.fn(),
  },
}));

describe("workspace join session button", () => {
  beforeEach(async () => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(decksApi.list).mockResolvedValue([]);
    vi.mocked(sessionsApi.list).mockResolvedValue([]);
    vi.mocked(authApi.signIn).mockResolvedValue({
      access: "access",
      refresh: "refresh",
      user: {
        id: "u1",
        email: "you@studio.press",
        display_name: "Field Notes",
        role: "owner",
        approval_status: "approved",
      },
    });
    await useAuthStore().signIn("you@studio.press", "slaides");
  });

  it("opens an inline join menu and joins with the signed-in account identity", async () => {
    vi.mocked(sessionsApi.guestJoin).mockResolvedValue({
      session_id: "sess-1",
      participant_id: "participant-1",
      participant_ref: "ref-1",
      token: "guest-token",
      display_name: null,
      anon: true,
    });

    const wrapper = mount(Workspace, {
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          DeckCard: true,
          DeckList: true,
          NewDeckCard: true,
          SettingsDrawer: true,
          Toggle: {
            props: ["modelValue"],
            emits: ["update:modelValue"],
            template:
              '<input data-testid="workspace-join-anonymous-toggle" type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
          },
        },
      },
    });

    expect(wrapper.get('[data-testid="workspace-header-actions"]').html()).toContain(
      'data-testid="workspace-join-session-button"',
    );

    await wrapper.get('[data-testid="workspace-join-session-button"]').trigger("click");

    expect(push).not.toHaveBeenCalledWith("/join");
    expect(wrapper.get('[data-testid="workspace-join-menu"]').text()).toContain("Session code");

    const codeInput = wrapper.get('[data-testid="workspace-join-code-input"]');
    await codeInput.trigger("paste", {
      clipboardData: { getData: () => "http://slides.example/j/sld-2k4f-92" },
    });
    await nextTick();
    expect((codeInput.element as HTMLInputElement).value).toBe("SLD-2K4F-92");
    await wrapper.get('[data-testid="workspace-join-anonymous-toggle"]').setValue(true);
    await wrapper.get('[data-testid="workspace-join-form"]').trigger("submit");

    expect(sessionsApi.guestJoin).toHaveBeenCalledWith("SLD-2K4F-92", "you@studio.press", "Field Notes", true);
    expect(push).toHaveBeenCalledWith("/audience/sess-1");
  });
});
