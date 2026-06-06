import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { authApi } from "@/api/auth";
import { sessionsApi } from "@/api/sessions";
import Signin from "@/pages/Signin.vue";
import { useAuthStore } from "@/stores/auth";

const push = vi.fn();
let routeQuery: Record<string, string> = {};

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: routeQuery }),
}));

vi.mock("@/api/auth", () => ({
  authApi: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    me: vi.fn(),
  },
}));

vi.mock("@/api/sessions", () => ({
  sessionsApi: {
    byCode: vi.fn(),
    guestJoin: vi.fn(),
  },
}));

describe("signed-in audience join", () => {
  beforeEach(async () => {
    localStorage.clear();
    routeQuery = {};
    setActivePinia(createPinia());
    vi.clearAllMocks();
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

  it("uses the account identity and only asks whether to join anonymously", async () => {
    vi.mocked(sessionsApi.guestJoin).mockResolvedValue({
      session_id: "sess-1",
      participant_id: "participant-1",
      participant_ref: "ref-1",
      token: "guest-token",
      display_name: null,
      anon: true,
    });

    const wrapper = mount(Signin, {
      props: { joinCode: "sld-test" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          Toggle: {
            props: ["modelValue"],
            emits: ["update:modelValue"],
            template:
              '<input data-testid="anon-toggle" type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
          },
        },
      },
    });
    await nextTick();

    expect(wrapper.get('[data-testid="signed-in-guest-identity"]').text()).toContain("Field Notes");
    expect(wrapper.find('input[type="email"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Display name");

    await wrapper.get('[data-testid="anon-toggle"]').setValue(true);
    await wrapper.get('[data-testid="guest-identity-form"]').trigger("submit");

    expect(sessionsApi.guestJoin).toHaveBeenCalledWith("SLD-TEST", "you@studio.press", "Field Notes", true);
    expect(push).toHaveBeenCalledWith("/audience/sess-1");
  });

  it("starts on the session-code step when launched from the workspace join route", async () => {
    const wrapper = mount(Signin, {
      props: { startGuest: true },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          Toggle: true,
        },
      },
    });
    await nextTick();

    expect(wrapper.text()).toContain("Join a session.");
    expect(wrapper.text()).toContain("Session code");
    expect(wrapper.text()).not.toContain("Welcome back.");
  });

  it("joins the linked session immediately after signing in from a join URL", async () => {
    const auth = useAuthStore();
    auth.signOut();
    vi.mocked(sessionsApi.guestJoin).mockResolvedValue({
      session_id: "sess-2",
      participant_id: "participant-2",
      participant_ref: "ref-2",
      token: "guest-token-2",
      display_name: "Field Notes",
      anon: false,
    });

    const wrapper = mount(Signin, {
      props: { joinCode: "sld-next" },
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          Toggle: true,
        },
      },
    });
    await nextTick();

    const modeSignIn = wrapper.findAll("button").find((button) => button.text() === "Sign in");
    expect(modeSignIn).toBeDefined();
    await modeSignIn!.trigger("click");
    await nextTick();

    await wrapper.get('input[type="email"]').setValue("you@studio.press");
    await wrapper.get('input[type="password"]').setValue("slaides");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(authApi.signIn).toHaveBeenCalledWith("you@studio.press", "slaides");
    expect(sessionsApi.guestJoin).toHaveBeenCalledWith("SLD-NEXT", "you@studio.press", "Field Notes", false);
    expect(push).toHaveBeenCalledWith("/audience/sess-2");
    expect(push).not.toHaveBeenCalledWith("/workspace");
  });

  it("returns signed-in instructors to the mirror next route", async () => {
    const auth = useAuthStore();
    auth.signOut();
    routeQuery = { next: "/mirror/sess-1?token=mirror-token" };

    const wrapper = mount(Signin, {
      global: {
        stubs: {
          Wordmark: true,
          Icon: true,
          Toggle: true,
        },
      },
    });
    await nextTick();

    await wrapper.get('input[type="email"]').setValue("you@studio.press");
    await wrapper.get('input[type="password"]').setValue("slaides");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(authApi.signIn).toHaveBeenCalledWith("you@studio.press", "slaides");
    expect(push).toHaveBeenCalledWith("/mirror/sess-1?token=mirror-token");
    expect(push).not.toHaveBeenCalledWith("/workspace");
  });
});
