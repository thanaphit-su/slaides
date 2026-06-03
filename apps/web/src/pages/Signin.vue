<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { sessionsApi } from "@/api/sessions";
import { saveGuestToken } from "@/stores/session";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import Toggle from "@/components/Toggle.vue";

const props = defineProps<{ joinCode?: string; startGuest?: boolean }>();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const mode = ref<"instructor" | "guest">("instructor");
const instructorMode = ref<"signin" | "signup">("signin");
const step = ref<"credentials" | "code" | "identity">("credentials");

const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const name = ref("");
const code = ref("SLD-2K4F-92");
const anon = ref(false);
const guestNotice = ref<string | null>(null);
const guestBusy = ref(false);
const pendingNotice = ref(false);
const signedInGuestIdentity = computed(() => (auth.isSignedIn && auth.user?.email ? auth.user : null));
const signedInGuestName = computed(
  () => signedInGuestIdentity.value?.display_name || signedInGuestIdentity.value?.email || "",
);

onMounted(() => {
  if (route.query.pending === "1") {
    pendingNotice.value = true;
  }
  if (props.joinCode) {
    code.value = String(props.joinCode).toUpperCase();
    mode.value = "guest";
    step.value = "identity";
  } else if (props.startGuest) {
    mode.value = "guest";
    step.value = "code";
  }
});

async function submitInstructor(e: Event) {
  e.preventDefault();
  try {
    if (instructorMode.value === "signup") {
      if (password.value !== confirmPassword.value) {
        auth.error = "Passwords do not match.";
        return;
      }
      await auth.signUp(email.value, password.value, name.value);
    } else {
      await auth.signIn(email.value, password.value);
    }
    if (!auth.isApproved) {
      pendingNotice.value = true;
    }
    if (props.joinCode) {
      await joinSignedInSession();
      return;
    }
    await router.push("/workspace");
  } catch {
    // error is in auth.error
  }
}

function setMode(m: "instructor" | "guest") {
  mode.value = m;
  step.value = m === "guest" ? "code" : "credentials";
  auth.error = null;
  guestNotice.value = null;
  pendingNotice.value = false;
}

async function submitGuestCode(e: Event) {
  e.preventDefault();
  guestNotice.value = null;
  try {
    await sessionsApi.byCode(code.value.trim().toUpperCase());
    step.value = "identity";
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Could not find that session.";
    guestNotice.value = msg;
  }
}

async function submitGuestIdentity(e: Event) {
  e.preventDefault();
  await joinSessionWithCurrentIdentity();
}

async function joinSignedInSession() {
  if (!(await joinSessionWithCurrentIdentity())) {
    mode.value = "guest";
    step.value = "identity";
  }
}

async function joinSessionWithCurrentIdentity() {
  guestBusy.value = true;
  guestNotice.value = null;
  try {
    const joinIdentity = signedInGuestIdentity.value
      ? {
          email: signedInGuestIdentity.value.email,
          displayName: signedInGuestName.value,
        }
      : {
          email: email.value,
          displayName: name.value,
        };
    const res = await sessionsApi.guestJoin(
      code.value.trim().toUpperCase(),
      joinIdentity.email,
      joinIdentity.displayName,
      anon.value,
    );
    saveGuestToken(res.session_id, res);
    await router.push(`/audience/${res.session_id}`);
    return true;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Couldn't join the session.";
    guestNotice.value = msg;
    return false;
  } finally {
    guestBusy.value = false;
  }
}
</script>

<template>
  <div :style="{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '1fr 1fr', background: 'var(--paper)' }">
    <!-- Left — editorial side -->
    <div
      :style="{
        padding: '56px 64px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        borderRight: '1px solid var(--rule)',
      }"
    >
      <Wordmark :size="18" />
      <div class="slide-up">
        <div class="t-kicker" :style="{ marginBottom: '18px' }">A press for talks worth keeping.</div>
        <div class="t-display" :style="{ fontSize: '64px', marginBottom: '24px' }">
          Write a deck.<br />Run a <em>conversation</em>.<br />Keep the receipts.
        </div>
        <div class="rule" :style="{ marginBottom: '16px' }"></div>
        <p class="t-lede" :style="{ maxWidth: '52ch' }">
          SLAIDES is a presentation tool built for the back-and-forth: live polls, open questions, on-the-fly
          LLM assistants, and a transcript of every interaction your audience leaves behind.
        </p>
      </div>
      <div :style="{ display: 'flex', gap: '28px', color: 'var(--ink-soft)' }">
        <span class="t-meta"><b :style="{ color: 'var(--ink)' }">v 0.1</b> · prototype</span>
        <span class="t-meta">Newsreader · Inter · Plex Mono</span>
      </div>
    </div>

    <!-- Right — auth -->
    <div
      :style="{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '56px 64px',
        background: 'var(--paper-2)',
      }"
    >
      <div :style="{ width: '100%', maxWidth: '380px' }">
        <!-- mode switcher -->
        <div
          :style="{
            display: 'flex',
            gap: 0,
            border: '1px solid var(--rule)',
            borderRadius: 'var(--r-md)',
            padding: '3px',
            background: 'var(--paper)',
            marginBottom: '32px',
          }"
        >
          <button
            v-for="m in (['instructor', 'guest'] as const)"
            :key="m"
            @click="setMode(m)"
            :style="{
              flex: 1,
              padding: '8px 12px',
              border: 'none',
              background: mode === m ? 'var(--ink)' : 'transparent',
              color: mode === m ? 'var(--paper)' : 'var(--ink-soft)',
              borderRadius: '6px',
              fontFamily: 'var(--sans)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all .15s ease',
            }"
          >
            {{ m === "instructor" ? "Sign in" : "Join a session" }}
          </button>
        </div>

        <form v-if="mode === 'instructor'" class="fade-in" @submit="submitInstructor">
          <div :style="{ marginBottom: '6px' }" class="t-kicker">Instructor</div>
          <div class="t-h3" :style="{ marginBottom: '24px' }">
            {{ instructorMode === "signin" ? "Welcome back." : "Request instructor access." }}
          </div>

          <div class="auth-subswitch">
            <button type="button" :class="{ active: instructorMode === 'signin' }" @click="instructorMode = 'signin'">
              Sign in
            </button>
            <button type="button" :class="{ active: instructorMode === 'signup' }" @click="instructorMode = 'signup'">
              Sign up
            </button>
          </div>

          <div :style="{ marginBottom: '14px' }">
            <label class="field-label">Email</label>
            <input
              class="input"
              type="email"
              placeholder="you@studio.press"
              v-model="email"
              required
              autofocus
            />
          </div>
          <div v-if="instructorMode === 'signup'" :style="{ marginBottom: '14px' }">
            <label class="field-label">Display name</label>
            <input class="input" placeholder="Your name" v-model="name" required />
          </div>
          <div :style="{ marginBottom: '18px' }">
            <label class="field-label">Password</label>
            <input class="input" type="password" placeholder="••••••••" v-model="password" required />
          </div>
          <div v-if="instructorMode === 'signup'" :style="{ marginBottom: '18px' }">
            <label class="field-label">Confirm password</label>
            <input class="input" type="password" placeholder="••••••••" v-model="confirmPassword" required />
          </div>

          <div v-if="pendingNotice || auth.approvalStatus === 'pending'" class="approval-note">
            Your instructor account is waiting for approval. You can sign in, but workspace access stays locked until
            an admin approves you.
          </div>

          <div
            v-if="auth.error"
            :style="{
              marginBottom: '14px',
              fontSize: '12px',
              color: 'var(--err)',
            }"
          >
            {{ auth.error }}
          </div>

          <button
            type="submit"
            :disabled="auth.busy"
            class="btn btn-primary"
            :style="{ width: '100%', justifyContent: 'center', padding: '12px' }"
          >
            {{ auth.busy ? "Working…" : instructorMode === "signin" ? "Sign in" : "Sign up" }}
            <Icon name="arrow_right" :size="16" />
          </button>

          <div
            :style="{
              textAlign: 'center',
              marginTop: '16px',
              fontSize: '12px',
              color: 'var(--ink-soft)',
            }"
          >
            {{
              instructorMode === "signin"
                ? "Use your instructor account to continue."
                : "New instructor accounts may require approval before workspace access."
            }}
          </div>
        </form>

        <form v-if="mode === 'guest' && step === 'code'" class="fade-in" @submit="submitGuestCode">
          <div :style="{ marginBottom: '6px' }" class="t-kicker">Audience</div>
          <div class="t-h3" :style="{ marginBottom: '8px' }">Join a session.</div>
          <p class="t-meta" :style="{ marginBottom: '24px' }">
            Enter the code your instructor shared, or paste the link.
          </p>

          <div :style="{ marginBottom: '18px' }">
            <label class="field-label">Session code</label>
            <input
              class="input"
              placeholder="SLD-XXXX-XX"
              v-model="code"
              required
              autofocus
              :style="{
                fontFamily: 'var(--mono)',
                letterSpacing: '.08em',
                textAlign: 'center',
                fontSize: '18px',
              }"
            />
          </div>

          <button
            type="submit"
            class="btn btn-primary"
            :style="{ width: '100%', justifyContent: 'center', padding: '12px' }"
          >
            Continue
            <Icon name="arrow_right" :size="16" />
          </button>
        </form>

        <form
          v-if="mode === 'guest' && step === 'identity'"
          class="fade-in"
          data-testid="guest-identity-form"
          @submit="submitGuestIdentity"
        >
          <div :style="{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }">
            <span class="t-kicker">Audience</span>
            <button type="button" class="btn btn-ghost btn-sm" @click="step = 'code'">
              <Icon name="arrow_left" :size="14" /> Back
            </button>
          </div>
          <div class="t-h3" :style="{ marginBottom: '8px' }">Tell us who's joining.</div>
          <p class="t-meta" :style="{ marginBottom: '24px' }">
            The instructor will see your name. Anonymous mode hides it everywhere but keeps your seat.
          </p>

          <div v-if="signedInGuestIdentity" class="signed-in-guest-identity" data-testid="signed-in-guest-identity">
            <div class="signed-in-guest-avatar">
              {{ signedInGuestName.slice(0, 1).toUpperCase() }}
            </div>
            <div>
              <strong>{{ signedInGuestName }}</strong>
              <small>{{ signedInGuestIdentity.email }}</small>
            </div>
          </div>
          <template v-else>
            <div :style="{ marginBottom: '14px' }">
              <label class="field-label">Email</label>
              <input class="input" type="email" placeholder="you@somewhere.edu" v-model="email" required autofocus />
            </div>
            <div :style="{ marginBottom: '14px' }">
              <label class="field-label">Display name</label>
              <input
                class="input"
                :placeholder="anon ? 'Hidden — joining anonymously' : 'e.g. Sara K.'"
                v-model="name"
                :disabled="anon"
                :required="!anon"
              />
            </div>
          </template>

          <div
            :style="{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              border: '1px solid var(--rule)',
              borderRadius: 'var(--r-md)',
              background: 'var(--paper)',
              marginBottom: '18px',
            }"
          >
            <div>
              <div :style="{ fontSize: '13px', fontWeight: 600 }">Join anonymously</div>
              <div :style="{ fontSize: '11px', color: 'var(--ink-soft)', marginTop: '2px' }">
                Your name and email are stored as a salted hash.
              </div>
            </div>
            <Toggle v-model="anon" />
          </div>

          <button
            type="submit"
            class="btn btn-primary"
            :disabled="guestBusy"
            :style="{ width: '100%', justifyContent: 'center', padding: '12px' }"
          >
            {{ guestBusy ? "Joining…" : "Join session" }} <Icon name="arrow_right" :size="16" />
          </button>

          <div
            v-if="guestNotice"
            :style="{
              marginTop: '14px',
              fontSize: '12px',
              color: 'var(--ink-soft)',
              textAlign: 'center',
            }"
          >
            {{ guestNotice }}
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-subswitch {
  display: flex;
  gap: 4px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 3px;
  background: var(--paper);
  margin-bottom: 18px;
}

.auth-subswitch button {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--ink-soft);
  border-radius: 6px;
  padding: 7px 10px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.auth-subswitch button.active {
  background: var(--ink);
  color: var(--paper);
}

.approval-note {
  margin-bottom: 14px;
  border: 1px solid var(--accent);
  border-radius: var(--r-md);
  padding: 10px 12px;
  background: var(--accent-soft);
  color: var(--ink);
  font-size: 12px;
  line-height: 1.5;
}

.signed-in-guest-identity {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  padding: 12px;
}

.signed-in-guest-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--ink);
  color: var(--paper);
  font-size: 13px;
  font-weight: 800;
}

.signed-in-guest-identity strong,
.signed-in-guest-identity small {
  display: block;
}

.signed-in-guest-identity strong {
  font-size: 13px;
}

.signed-in-guest-identity small {
  margin-top: 2px;
  color: var(--ink-soft);
  font-size: 11px;
}
</style>
