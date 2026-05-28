import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import Workspace from "@/pages/Workspace.vue";
import { authApi } from "@/api/auth";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
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

describe("workspace avatar menu", () => {
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

  it("opens account menu from avatar and signs out from the menu item", async () => {
    const wrapper = mount(Workspace, {
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          DeckCard: true,
          DeckList: true,
          NewDeckCard: true,
          SettingsDrawer: true,
        },
      },
    });

    const auth = useAuthStore();
    const signOut = vi.spyOn(auth, "signOut");

    await wrapper.get('[data-testid="account-avatar-button"]').trigger("click");

    expect(signOut).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="account-menu"]').text()).toContain("Field Notes");

    await wrapper.get('[data-testid="account-menu-signout"]').trigger("click");

    expect(signOut).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith("/signin");
  });
});
