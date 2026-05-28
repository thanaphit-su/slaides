import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authApi } from "@/api/auth";
import { attemptRefresh, configureTokenAccess } from "@/api/client";
import type { User } from "@/api/types";

const STORAGE_KEY = "slaides:auth";
// Refresh this many seconds BEFORE the access token's `exp` claim. Closes
// the small window where the previous request just sent a now-expired token
// and the user sees the 401-retry-with-refresh stall mid-action.
const REFRESH_LEAD_SECONDS = 60;

interface Persisted {
  access: string;
  refresh: string;
  user: User;
}

function load(): Persisted | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Persisted;
  } catch {
    return null;
  }
}

function save(state: Persisted | null) {
  if (state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

/**
 * Decode the `exp` claim from a Supabase access token without verifying
 * the signature — the server is the trust boundary; here we only need the
 * expiry timestamp for scheduling the refresh timer.
 *
 * Returns the exp as Unix seconds, or null if the token isn't a parseable
 * JWT (in which case the caller skips scheduling).
 */
function decodeJwtExp(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    // base64url -> base64
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    // atob requires the standard padding.
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const json = atob(padded);
    const claims = JSON.parse(json) as { exp?: number };
    return typeof claims.exp === "number" ? claims.exp : null;
  } catch {
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const initial = load();
  const access = ref<string | null>(initial?.access ?? null);
  const refresh = ref<string | null>(initial?.refresh ?? null);
  const user = ref<User | null>(initial?.user ?? null);
  const error = ref<string | null>(null);
  const busy = ref(false);

  const isSignedIn = computed(() => !!user.value && !!access.value);
  const approvalStatus = computed(() => user.value?.approval_status ?? null);
  const isApproved = computed(() => approvalStatus.value === "approved");

  // Proactive refresh timer. Replaces itself on every token write and is
  // cancelled on sign-out. If decoding the JWT fails or the token is
  // already past its lead window, we skip — the existing 401-retry path
  // in api/client.ts still catches stragglers.
  let refreshTimer: ReturnType<typeof setTimeout> | null = null;

  function cancelRefresh() {
    if (refreshTimer !== null) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function scheduleRefresh(token: string | null) {
    cancelRefresh();
    if (!token) return;
    const exp = decodeJwtExp(token);
    if (exp === null) return;
    const nowSec = Math.floor(Date.now() / 1000);
    const delaySec = exp - nowSec - REFRESH_LEAD_SECONDS;
    if (delaySec <= 0) {
      // Already inside (or past) the refresh window — kick off immediately.
      void attemptRefresh();
      return;
    }
    refreshTimer = setTimeout(() => {
      void attemptRefresh();
    }, delaySec * 1000);
  }

  configureTokenAccess({
    get: () => ({ access: access.value, refresh: refresh.value }),
    set: ({ access: a, refresh: r }) => {
      access.value = a;
      refresh.value = r;
      if (user.value) save({ access: a, refresh: r, user: user.value });
      scheduleRefresh(a);
    },
    clear: () => {
      access.value = null;
      refresh.value = null;
      user.value = null;
      save(null);
      cancelRefresh();
    },
  });

  // On store init from persisted localStorage, schedule the timer too —
  // otherwise reload-then-idle tabs would only refresh on the next 401.
  if (initial?.access) scheduleRefresh(initial.access);

  async function signIn(email: string, password: string) {
    busy.value = true;
    error.value = null;
    try {
      const res = await authApi.signIn(email, password);
      access.value = res.access;
      refresh.value = res.refresh;
      user.value = res.user;
      save({ access: res.access, refresh: res.refresh, user: res.user });
      scheduleRefresh(res.access);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sign-in failed";
      error.value = msg === "bad credentials" ? "Wrong email or password." : msg;
      throw e;
    } finally {
      busy.value = false;
    }
  }

  async function signUp(email: string, password: string, displayName: string) {
    busy.value = true;
    error.value = null;
    try {
      const res = await authApi.signUp(email, password, displayName);
      access.value = res.access;
      refresh.value = res.refresh;
      user.value = res.user;
      save({ access: res.access, refresh: res.refresh, user: res.user });
      scheduleRefresh(res.access);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sign-up failed";
      error.value = msg;
      throw e;
    } finally {
      busy.value = false;
    }
  }

  function signOut() {
    access.value = null;
    refresh.value = null;
    user.value = null;
    save(null);
    cancelRefresh();
  }

  return {
    access,
    refresh,
    user,
    error,
    busy,
    isSignedIn,
    approvalStatus,
    isApproved,
    signIn,
    signUp,
    signOut,
  };
});
