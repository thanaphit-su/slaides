import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";

vi.mock("@/api/auth", () => ({
  authApi: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    me: vi.fn(),
  },
}));

// Build a Supabase-shaped access token with a `exp` claim N seconds out.
// We don't verify the signature on the client, so the secret is irrelevant.
function fakeAccessToken(expOffsetSeconds: number): string {
  const now = Math.floor(Date.now() / 1000);
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({ sub: "u-1", email: "a@b.c", exp: now + expOffsetSeconds, aud: "authenticated" }),
  );
  return `${header}.${payload}.sig`;
}

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stores pending approval state after signup", async () => {
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

    expect(auth.isSignedIn).toBe(true);
    expect(auth.isApproved).toBe(false);
    expect(auth.approvalStatus).toBe("pending");
  });

  it("marks approved users as approved after sign in", async () => {
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

    const auth = useAuthStore();
    await auth.signIn("you@studio.press", "slaides");

    expect(auth.isSignedIn).toBe(true);
    expect(auth.isApproved).toBe(true);
  });

  it("schedules a proactive refresh ~60s before the JWT exp on sign-in", async () => {
    vi.useFakeTimers();
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");

    // 5 minutes (300s) from now -> refresh should fire at ~240s.
    vi.mocked(authApi.signIn).mockResolvedValue({
      access: fakeAccessToken(300),
      refresh: "rt",
      user: {
        id: "u1",
        email: "you@studio.press",
        display_name: "Field Notes",
        role: "owner",
        approval_status: "approved",
      },
    });

    const auth = useAuthStore();
    await auth.signIn("you@studio.press", "slaides");

    // Find the call that scheduled the refresh — the only one in the
    // ~240 000 ms range (Vue Router / Pinia don't schedule anything close).
    const refreshCall = setTimeoutSpy.mock.calls.find(([, delay]) => {
      return typeof delay === "number" && Math.abs(delay - 240_000) < 2_000;
    });
    expect(refreshCall).toBeTruthy();
  });

  it("signOut cancels the scheduled refresh timer", async () => {
    vi.useFakeTimers();
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");

    vi.mocked(authApi.signIn).mockResolvedValue({
      access: fakeAccessToken(300),
      refresh: "rt",
      user: {
        id: "u1",
        email: "you@studio.press",
        display_name: "Field Notes",
        role: "owner",
        approval_status: "approved",
      },
    });

    const auth = useAuthStore();
    await auth.signIn("you@studio.press", "slaides");

    // Capture the handle of the refresh timer (the call with delay ≈ 240s).
    const refreshCall = setTimeoutSpy.mock.results.find((res, idx) => {
      const args = setTimeoutSpy.mock.calls[idx];
      const delay = args[1];
      return typeof delay === "number" && Math.abs(delay - 240_000) < 2_000;
    });
    expect(refreshCall).toBeTruthy();
    const handle = refreshCall!.value;

    auth.signOut();

    expect(clearTimeoutSpy).toHaveBeenCalledWith(handle);
  });

  it("does not schedule a timer when the access token is not a parseable JWT", async () => {
    vi.useFakeTimers();
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");

    vi.mocked(authApi.signIn).mockResolvedValue({
      access: "not-a-jwt",
      refresh: "rt",
      user: {
        id: "u1",
        email: "you@studio.press",
        display_name: "Field Notes",
        role: "owner",
        approval_status: "approved",
      },
    });

    const auth = useAuthStore();
    await auth.signIn("you@studio.press", "slaides");

    // No setTimeout call with the characteristic ~minutes-out delay.
    const refreshish = setTimeoutSpy.mock.calls.find(
      ([, delay]) => typeof delay === "number" && delay > 30_000,
    );
    expect(refreshish).toBeUndefined();
  });
});
