import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

describe("workspace live deck badges", () => {
  beforeEach(async () => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(decksApi.list).mockResolvedValue([
      {
        id: "live-deck",
        title: "Live deck",
        subtitle: null,
        cover: null,
        updated_at: "2026-05-22T00:00:00Z",
        slide_count: 3,
        preview_kicker: null,
        preview_markdown: "# Live",
      },
      {
        id: "quiet-deck",
        title: "Quiet deck",
        subtitle: null,
        cover: null,
        updated_at: "2026-05-22T00:00:00Z",
        slide_count: 2,
        preview_kicker: null,
        preview_markdown: "# Quiet",
      },
    ]);
    vi.mocked(sessionsApi.list).mockResolvedValue([
      {
        id: "sess-1",
        deck_id: "live-deck",
        code: "SLD-LIVE-1",
        started_at: "2026-05-22T00:00:00Z",
        ended_at: null,
        deck_title: "Loud deck",
        participant_count: 3,
        interaction_count: 7,
      },
      {
        id: "sess-2",
        deck_id: "quiet-deck",
        code: "SLD-END-1",
        started_at: "2026-05-21T00:00:00Z",
        ended_at: "2026-05-21T01:00:00Z",
        deck_title: "Quiet deck",
        participant_count: 2,
        interaction_count: 0,
      },
    ]);
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

  it("marks only decks with unended live sessions", async () => {
    const wrapper = mount(Workspace, {
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          NewDeckCard: true,
          SettingsDrawer: true,
        },
      },
    });
    await flushPromises();

    const cards = wrapper.findAllComponents({ name: "DeckCard" });
    expect(cards[0].props("live")).toBe(true);
    expect(cards[1].props("live")).toBe(false);
  });
});
