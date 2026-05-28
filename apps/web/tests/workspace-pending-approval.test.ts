import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import Workspace from "@/pages/Workspace.vue";
import { authApi } from "@/api/auth";
import { decksApi } from "@/api/decks";
import { useAuthStore } from "@/stores/auth";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
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

describe("workspace pending approval access", () => {
  beforeEach(async () => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(decksApi.list).mockResolvedValue([]);
    vi.mocked(authApi.signIn).mockResolvedValue({
      access: "access",
      refresh: "refresh",
      user: {
        id: "u1",
        email: "pending@example.com",
        display_name: "Pending User",
        role: "instructor",
        approval_status: "pending",
      },
    });
    await useAuthStore().signIn("pending@example.com", "secret123");
  });

  it("defaults pending instructors to Sessions and blocks Decks and Widgets with approval messages", async () => {
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

    expect(decksApi.list).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Session history");
    expect(wrapper.text()).toContain("will appear here after approval-aware history ships in M5");

    await wrapper.get('[data-testid="workspace-tab-decks"]').trigger("click");
    expect(wrapper.text()).toContain("Decks require admin approval");
    // After Widgets v2 Step 2 there's no separate Widgets tab — widgets are
    // managed inline from the editor's right sidebar.
    expect(wrapper.find('[data-testid="workspace-tab-widgets"]').exists()).toBe(false);
  });
});
