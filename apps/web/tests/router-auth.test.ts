import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { router } from "@/router";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/api/auth", () => ({
  authApi: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    me: vi.fn(),
  },
}));

describe("router auth guard", () => {
  beforeEach(async () => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
    await router.push("/signin");
    await router.isReady();
  });

  it("allows pending instructors into workspace but keeps them out of approved-only routes", async () => {
    vi.mocked(authApi.signUp).mockResolvedValue({
      access: "access",
      refresh: "refresh",
      user: {
        id: "u1",
        email: "pending@example.com",
        display_name: "Pending",
        role: "instructor",
        approval_status: "pending",
      },
    });

    const auth = useAuthStore();
    await auth.signUp("pending@example.com", "secret123", "Pending");

    await router.push("/workspace");

    expect(router.currentRoute.value.name).toBe("workspace");

    await router.push("/editor/deck-1");

    expect(router.currentRoute.value.name).toBe("workspace");
    expect(router.currentRoute.value.query.pending).toBe("1");
  });
});
