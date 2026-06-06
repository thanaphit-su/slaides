<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";
import { sessionsApi } from "@/api/sessions";
import { saveGuestToken } from "@/stores/session";
import { normalizeJoinCode } from "@/utils/joinCode";
import type { SessionListItem } from "@/api/types";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import Toggle from "@/components/Toggle.vue";
import DeckCard from "@/components/DeckCard.vue";
import DeckList from "@/components/DeckList.vue";
import NewDeckCard from "@/components/NewDeckCard.vue";
import AccountMenu from "@/components/AccountMenu.vue";

const auth = useAuthStore();
const ws = useWorkspaceStore();
const router = useRouter();
const route = useRoute();

type WorkspaceTab = "decks" | "sessions";
function asTab(v: unknown): WorkspaceTab | null {
  return v === "decks" || v === "sessions" ? v : null;
}

const tab = ref<WorkspaceTab>(asTab(route.query.tab) ?? (auth.isApproved ? "decks" : "sessions"));

watch(tab, (next) => {
  if (route.query.tab !== next) {
    void router.replace({ query: { ...route.query, tab: next } });
  }
});

watch(
  () => route.query.tab,
  (next) => {
    const v = asTab(next);
    if (v && v !== tab.value) tab.value = v;
  },
);
const fileInput = ref<HTMLInputElement | null>(null);
const dragging = ref(false);
const joinMenuOpen = ref(false);
const joinMenuEl = ref<HTMLElement | null>(null);
const joinCode = ref("");
const joinAnon = ref(false);
const joinBusy = ref(false);
const joinNotice = ref<string | null>(null);
const confirmDelete = ref<{ id: string; title: string; slideCount: number } | null>(null);
const deleting = ref(false);
const confirmSessionDelete = ref<{ id: string; deckTitle: string; code: string } | null>(null);
const deletingSession = ref(false);
const toast = ref<string | null>(null);
const liveDeckIds = ref<Set<string>>(new Set());
const sessions = ref<SessionListItem[]>([]);
let toastTimer = 0;

function showToast(msg: string) {
  toast.value = msg;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.value = null), 1800);
}

function askDelete(id: string) {
  const deck = ws.decks.find((d) => d.id === id);
  if (!deck) return;
  confirmDelete.value = { id, title: deck.title, slideCount: deck.slide_count };
}

async function doDelete() {
  if (!confirmDelete.value) return;
  deleting.value = true;
  try {
    await ws.remove(confirmDelete.value.id);
    showToast("Deck deleted");
    confirmDelete.value = null;
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not delete deck.");
  } finally {
    deleting.value = false;
  }
}

function askSessionDelete(s: SessionListItem) {
  if (!s.ended_at) return;
  confirmSessionDelete.value = {
    id: s.id,
    deckTitle: s.deck_title || "Untitled deck",
    code: s.code,
  };
}

async function doSessionDelete() {
  if (!confirmSessionDelete.value) return;
  const id = confirmSessionDelete.value.id;
  deletingSession.value = true;
  try {
    await sessionsApi.remove(id);
    sessions.value = sessions.value.filter((x) => x.id !== id);
    showToast("Session deleted");
    confirmSessionDelete.value = null;
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not delete session.");
  } finally {
    deletingSession.value = false;
  }
}

onMounted(() => {
  if (auth.isApproved) {
    void ws.fetch();
    void fetchSessions();
  }
  if (!asTab(route.query.tab)) {
    void router.replace({ query: { ...route.query, tab: tab.value } });
  }
  document.addEventListener("click", onDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
});

async function createDeck() {
  const deck = await ws.create();
  router.push(`/editor/${deck.id}`);
}

async function fetchSessions() {
  try {
    const allSessions = await sessionsApi.list();
    sessions.value = allSessions;
    liveDeckIds.value = new Set(
      allSessions.filter((session) => !session.ended_at).map((session) => session.deck_id),
    );
  } catch {
    liveDeckIds.value = new Set();
    sessions.value = [];
  }
}

function isDeckLive(deckId: string): boolean {
  return liveDeckIds.value.has(deckId);
}

function openDeck(id: string) {
  if (!auth.isApproved) return;
  router.push(`/editor/${id}`);
}

function toggleJoinMenu() {
  joinMenuOpen.value = !joinMenuOpen.value;
  joinNotice.value = null;
}

function onJoinCodePaste(event: ClipboardEvent) {
  const pasted = event.clipboardData?.getData("text");
  if (!pasted) return;
  const normalized = normalizeJoinCode(pasted);
  if (normalized === pasted) return;
  event.preventDefault();
  joinCode.value = normalized;
}

async function submitJoinSession(e: Event) {
  e.preventDefault();
  const user = auth.user;
  if (!user?.email) {
    joinNotice.value = "Sign in before joining a session.";
    return;
  }
  joinBusy.value = true;
  joinNotice.value = null;
  joinCode.value = normalizeJoinCode(joinCode.value);
  try {
    const res = await sessionsApi.guestJoin(
      joinCode.value,
      user.email,
      user.display_name || user.email,
      joinAnon.value,
    );
    saveGuestToken(res.session_id, res);
    joinMenuOpen.value = false;
    joinCode.value = "";
    await router.push(`/audience/${res.session_id}`);
  } catch (err) {
    joinNotice.value = err instanceof Error ? err.message : "Couldn't join the session.";
  } finally {
    joinBusy.value = false;
  }
}

async function onImportPick(e: Event) {
  if (!auth.isApproved) return;
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  try {
    const deck = await ws.importDeck(file);
    router.push(`/editor/${deck.id}`);
  } finally {
    target.value = "";
  }
}

async function onDrop(e: DragEvent) {
  e.preventDefault();
  dragging.value = false;
  if (!auth.isApproved) return;
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  const deck = await ws.importDeck(file);
  router.push(`/editor/${deck.id}`);
}

function signOut() {
  auth.signOut();
  router.push("/signin");
}

function onDocumentClick(e: MouseEvent) {
  const target = e.target;
  if (!(target instanceof Node)) return;
  if (joinMenuEl.value?.contains(target)) return;
  joinMenuOpen.value = false;
}

function approvalTitle(space: "Decks") {
  return `${space} require admin approval`;
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sessionDurationMs(s: SessionListItem): number {
  if (!s.ended_at) return Date.now() - new Date(s.started_at).getTime();
  return new Date(s.ended_at).getTime() - new Date(s.started_at).getTime();
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.round(totalSeconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  return remMin === 0 ? `${hours}h` : `${hours}h ${remMin}m`;
}

// Sessions where start == end (within a few seconds) are abandoned/instant-ended.
// Hide by default; user can opt in.
const ZERO_DURATION_THRESHOLD_MS = 5_000;
const showZeroLength = ref(false);

function isMeaningfulSession(s: SessionListItem): boolean {
  if (!s.ended_at) return true;
  return sessionDurationMs(s) > ZERO_DURATION_THRESHOLD_MS;
}

const filteredSessions = computed(() =>
  showZeroLength.value ? sessions.value : sessions.value.filter(isMeaningfulSession),
);

// How many would be hidden when the toggle is off, regardless of current state.
const hideableSessionCount = computed(
  () => sessions.value.filter((s) => !isMeaningfulSession(s)).length,
);

const hiddenSessionCount = computed(
  () => sessions.value.length - filteredSessions.value.length,
);

const heroKicker = computed(() => {
  if (!auth.isApproved) return "Instructor access";
  return tab.value === "sessions" ? "Sessions" : "Library";
});
</script>

<template>
  <div
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop="onDrop"
    :style="{
      minHeight: '100vh',
      background: 'var(--paper)',
      display: 'flex',
      flexDirection: 'column',
      outline: dragging ? '2px dashed var(--accent)' : 'none',
      outlineOffset: '-12px',
    }"
  >
    <header
      :style="{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        background: 'var(--paper)',
        borderBottom: '1px solid var(--rule)',
        padding: '14px 32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }"
    >
      <div :style="{ display: 'flex', alignItems: 'center', gap: '24px' }">
        <Wordmark :size="16" />
        <nav :style="{ display: 'flex', gap: '4px' }">
          <button
            v-for="[k, label] in [
              ['decks', 'Decks'],
              ['sessions', 'Sessions'],
            ] as const"
            :key="k"
            :data-testid="`workspace-tab-${k}`"
            @click="tab = k"
            :style="{
              background: tab === k ? 'var(--paper-2)' : 'transparent',
              border: 'none',
              color: tab === k ? 'var(--ink)' : 'var(--ink-soft)',
              fontFamily: 'var(--sans)',
              fontWeight: tab === k ? 600 : 500,
              fontSize: '13px',
              padding: '6px 12px',
              borderRadius: 'var(--r-sm)',
              cursor: 'pointer',
            }"
          >
            {{ label }}
          </button>
        </nav>
      </div>
      <div
        data-testid="workspace-header-actions"
        :style="{ display: 'flex', alignItems: 'center', gap: '12px' }"
      >
        <div ref="joinMenuEl" class="workspace-join-wrap">
          <button
            type="button"
            class="workspace-join-session"
            data-testid="workspace-join-session-button"
            :aria-expanded="joinMenuOpen"
            aria-haspopup="menu"
            @click.stop="toggleJoinMenu"
          >
            <Icon name="users" :size="14" />
            Join session
          </button>
          <div
            v-if="joinMenuOpen"
            class="workspace-join-menu"
            data-testid="workspace-join-menu"
            @click.stop
          >
            <form data-testid="workspace-join-form" @submit="submitJoinSession">
              <label class="field-label">Session code</label>
              <input
                class="input workspace-join-code"
                data-testid="workspace-join-code-input"
                placeholder="SLD-XXXX-XX"
                v-model="joinCode"
                @paste="onJoinCodePaste"
                required
                autofocus
              />
              <div class="workspace-join-anon">
                <div>
                  <strong>Join anonymously</strong>
                  <small>Hide your account identity in this session.</small>
                </div>
                <Toggle v-model="joinAnon" />
              </div>
              <button class="btn btn-primary" type="submit" :disabled="joinBusy">
                {{ joinBusy ? "Joining..." : "Join" }}
                <Icon name="arrow_right" :size="14" />
              </button>
              <p v-if="joinNotice" class="workspace-join-notice">{{ joinNotice }}</p>
            </form>
          </div>
        </div>
        <div v-if="auth.isApproved" :style="{ position: 'relative' }">
          <span :style="{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-mute)' }">
            <Icon name="search" :size="14" />
          </span>
          <input
            class="input"
            placeholder="Search…"
            v-model="ws.query"
            :style="{
              width: '260px',
              paddingLeft: '32px',
              paddingTop: '7px',
              paddingBottom: '7px',
              fontSize: '13px',
              background: 'var(--paper-2)',
              border: '1px solid var(--rule)',
            }"
          />
        </div>
        <AccountMenu
          :user-name="auth.user?.display_name || 'Instructor'"
          :user-email="auth.user?.email"
          @sign-out="signOut"
        />
      </div>
    </header>

    <section :style="{ padding: '56px 32px 24px', maxWidth: '1240px', width: '100%', margin: '0 auto' }">
      <div class="t-kicker" :style="{ marginBottom: '14px' }">
        {{ heroKicker }} · {{ auth.user?.display_name || "You" }}
      </div>
      <div class="t-h1" :style="{ marginBottom: '14px' }">
        <template v-if="auth.isApproved && tab === 'decks'">The decks you've been <em>writing</em>.</template>
        <template v-else-if="auth.isApproved && tab === 'sessions'">The sessions you've <em>run</em>.</template>
        <template v-else>Session history.</template>
      </div>
      <p class="t-lede" :style="{ maxWidth: '62ch', marginBottom: '32px' }">
        <template v-if="auth.isApproved && tab === 'decks'">
          Open one to keep editing. Import a deck from another project at any time. Workspace-level views for
          widgets and past sessions are coming.
        </template>
        <template v-else-if="auth.isApproved && tab === 'sessions'">
          Every session you've started shows up here — open one for the timeline, audience interactions, and exportable transcript.
        </template>
        <template v-else>
          Your instructor account is waiting for admin approval. Until then, only session history is available.
        </template>
      </p>

      <div
        v-if="auth.isApproved && tab === 'decks'"
        :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }"
      >
        <div :style="{ display: 'flex', alignItems: 'center', gap: '8px' }">
          <button class="btn btn-primary" @click="createDeck">
            <Icon name="plus" :size="14" /> New deck
          </button>
          <button class="btn" @click="fileInput?.click()">
            <Icon name="upload" :size="14" /> Import…
          </button>
          <input ref="fileInput" type="file" accept=".slaides,application/zip" hidden @change="onImportPick" />
        </div>
        <div :style="{ display: 'flex', alignItems: 'center', gap: '10px' }">
          <span class="t-meta">{{ ws.filtered.length }} {{ ws.filtered.length === 1 ? "deck" : "decks" }}</span>
          <div :style="{ display: 'inline-flex', border: '1px solid var(--rule)', borderRadius: 'var(--r-sm)', overflow: 'hidden' }">
            <button
              v-for="v in (['grid', 'list'] as const)"
              :key="v"
              @click="ws.setView(v)"
              :style="{
                background: ws.view === v ? 'var(--paper-2)' : 'var(--paper)',
                border: 'none',
                color: ws.view === v ? 'var(--ink)' : 'var(--ink-mute)',
                padding: '6px 8px',
                cursor: 'pointer',
              }"
            >
              <Icon :name="v" :size="14" />
            </button>
          </div>
        </div>
      </div>
    </section>

    <section :style="{ padding: '0 32px 96px', maxWidth: '1240px', width: '100%', margin: '0 auto' }">
      <template v-if="!auth.isApproved && tab === 'decks'">
        <div class="approval-block">
          <div class="approval-block-icon">
            <Icon name="lock" :size="18" />
          </div>
          <h2>{{ approvalTitle("Decks") }}</h2>
          <p>
            An admin must approve your instructor account before you can create or edit decks. Widgets live inside
            decks now and are managed from the editor's right sidebar.
          </p>
        </div>
      </template>

      <template v-else-if="tab === 'decks'">
        <template v-if="ws.view === 'grid'">
          <div :style="{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '24px' }">
            <DeckCard
              v-for="d in ws.filtered"
              :key="d.id"
              :deck="d"
              :live="isDeckLive(d.id)"
              @open="openDeck(d.id)"
              @delete="askDelete(d.id)"
            />
            <NewDeckCard @create="createDeck" />
          </div>
        </template>
        <template v-else>
          <DeckList :decks="ws.filtered" :live-deck-ids="liveDeckIds" @open="openDeck" @delete="askDelete" />
        </template>
      </template>

      <template v-else-if="tab === 'sessions'">
        <div v-if="sessions.length === 0" class="sessions-empty">
          <h2>No sessions yet</h2>
          <p>Sessions you start or join will appear here.</p>
        </div>
        <template v-else>
          <div
            v-if="filteredSessions.length === 0"
            class="sessions-empty"
          >
            <h2>Nothing to show</h2>
            <p>
              {{ hiddenSessionCount }} short / empty
              {{ hiddenSessionCount === 1 ? "session is" : "sessions are" }}
              hidden.
              <button class="link-btn" @click="showZeroLength = true">Show them</button>
            </p>
          </div>
          <div v-else class="sessions-list">
            <div
              v-for="s in filteredSessions"
              :key="s.id"
              class="session-card"
              @click="router.push(`/sessions/${s.id}/transcript`)"
            >
              <div class="session-info">
                <h3 :title="s.deck_title || 'Untitled deck'">
                  {{ s.deck_title || "Untitled deck" }}
                  <span v-if="!s.ended_at" class="live-badge">LIVE</span>
                </h3>
                <p class="session-meta">
                  <span>{{ formatDate(s.started_at) }}</span>
                  <span class="meta-sep">·</span>
                  <span>{{ formatDuration(sessionDurationMs(s)) }}</span>
                  <span class="meta-sep">·</span>
                  <span>{{ s.participant_count }} {{ s.participant_count === 1 ? "participant" : "participants" }}</span>
                  <span class="meta-sep">·</span>
                  <span>{{ s.interaction_count }} {{ s.interaction_count === 1 ? "interaction" : "interactions" }}</span>
                  <span class="meta-sep">·</span>
                  <code class="session-code">{{ s.code }}</code>
                </p>
              </div>
              <button
                class="btn btn-sm btn-icon btn-danger-ghost"
                :title="s.ended_at ? 'Delete session permanently' : 'End the session first'"
                :disabled="!s.ended_at"
                @click.stop="askSessionDelete(s)"
              >
                <Icon name="trash" :size="14" />
              </button>
            </div>
            <div v-if="hideableSessionCount > 0" class="sessions-hidden-row">
              <button
                v-if="!showZeroLength"
                class="link-btn"
                @click="showZeroLength = true"
              >
                Show {{ hideableSessionCount }} short / empty
                {{ hideableSessionCount === 1 ? "session" : "sessions" }}
              </button>
              <button
                v-else
                class="link-btn"
                @click="showZeroLength = false"
              >
                Hide short / empty sessions
              </button>
            </div>
          </div>
        </template>
      </template>
    </section>

    <footer :style="{ borderTop: '1px solid var(--rule)', padding: '24px 32px', maxWidth: '1240px', width: '100%', margin: '0 auto' }">
      <div :style="{ display: 'flex', justifyContent: 'space-between', color: 'var(--ink-soft)' }">
        <span class="t-meta">© SLAIDES · v 0.1</span>
        <span class="t-meta">Drag a .slaides file anywhere on this page to import</span>
      </div>
    </footer>

    <div
      v-if="confirmDelete"
      class="delete-backdrop"
      @click.self="confirmDelete = null"
    >
      <div class="delete-modal scale-in">
        <h3>Delete deck?</h3>
        <p>
          <strong>{{ confirmDelete.title }}</strong> and its
          {{ confirmDelete.slideCount }} {{ confirmDelete.slideCount === 1 ? "slide" : "slides" }}
          will be permanently removed.
        </p>
        <div class="delete-actions">
          <button class="btn btn-sm" :disabled="deleting" @click="confirmDelete = null">Cancel</button>
          <button class="btn btn-sm btn-danger" :disabled="deleting" @click="doDelete">
            {{ deleting ? "Deleting…" : "Delete deck" }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="confirmSessionDelete"
      class="delete-backdrop"
      @click.self="confirmSessionDelete = null"
    >
      <div class="delete-modal scale-in">
        <h3>Delete session?</h3>
        <p>
          The session <strong>{{ confirmSessionDelete.deckTitle }}</strong>
          (<code>{{ confirmSessionDelete.code }}</code>) and all of its participants,
          poll votes, questions, and transcript will be permanently removed.
          <br><br>
          The deck itself is not affected. This action cannot be undone.
        </p>
        <div class="delete-actions">
          <button class="btn btn-sm" :disabled="deletingSession" @click="confirmSessionDelete = null">Cancel</button>
          <button class="btn btn-sm btn-danger" :disabled="deletingSession" @click="doSessionDelete">
            {{ deletingSession ? "Deleting…" : "Delete session" }}
          </button>
        </div>
      </div>
    </div>

    <transition name="fade">
      <div
        v-if="toast"
        :style="{
          position: 'fixed',
          bottom: '32px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--ink)',
          color: 'var(--paper)',
          padding: '10px 18px',
          borderRadius: 'var(--r-md)',
          fontSize: '12px',
          fontFamily: 'var(--sans)',
          zIndex: 100,
          boxShadow: 'var(--shadow-3)',
        }"
      >
        {{ toast }}
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.workspace-join-wrap {
  position: relative;
}
.workspace-join-session {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper);
  color: var(--ink);
  padding: 6px 10px;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.workspace-join-session:hover {
  background: var(--paper-2);
}
.workspace-join-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 50;
  width: 280px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  padding: 14px;
  box-shadow: var(--shadow-3);
}
.workspace-join-code {
  margin-bottom: 12px;
  font-family: var(--mono);
  font-size: 15px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.workspace-join-anon {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  padding: 10px;
  margin-bottom: 12px;
}
.workspace-join-anon strong,
.workspace-join-anon small {
  display: block;
}
.workspace-join-anon strong {
  font-size: 12px;
}
.workspace-join-anon small {
  margin-top: 2px;
  color: var(--ink-soft);
  font-size: 11px;
  line-height: 1.4;
}
.workspace-join-menu .btn {
  width: 100%;
  justify-content: center;
}
.workspace-join-notice {
  margin: 10px 0 0;
  color: var(--err);
  font-size: 12px;
  line-height: 1.4;
}
.approval-block,
.sessions-placeholder {
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper-2);
  padding: 28px;
  max-width: 620px;
}
.approval-block {
  border-style: dashed;
}
.sessions-empty {
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper-2);
  padding: 28px;
  text-align: center;
}
.sessions-empty h2 {
  margin: 0 0 8px;
  font-family: var(--serif);
  color: var(--ink);
  font-size: 22px;
  font-weight: 600;
}
.sessions-empty p {
  margin: 0;
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.55;
}
.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.session-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  padding: 14px 18px;
  cursor: pointer;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.session-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-2);
}
.session-info {
  flex: 1;
  min-width: 0;
}
.session-info h3 {
  margin: 0 0 6px;
  font-family: var(--serif);
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  margin: 0;
  font-size: 12px;
  color: var(--ink-soft);
  font-family: var(--sans);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.session-meta .meta-sep {
  color: var(--rule);
}
.session-code {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 11px;
  background: var(--paper-2);
  padding: 1px 6px;
  border-radius: var(--r-sm);
  color: var(--ink-mute, var(--ink-soft));
}
.sessions-hidden-row {
  text-align: center;
  padding: 4px 0;
}
.link-btn {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--accent);
  font-family: var(--sans);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
}
.link-btn:hover {
  color: var(--ink);
}
.live-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 6px;
  background: var(--accent);
  color: var(--paper);
  border-radius: var(--r-sm);
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}
.approval-block-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--paper);
  color: var(--ink-soft);
  border: 1px solid var(--rule);
  margin-bottom: 14px;
}
.approval-block h2,
.sessions-placeholder h2 {
  margin: 0 0 8px;
  font-family: var(--serif);
  color: var(--ink);
  font-size: 22px;
  font-weight: 600;
}
.approval-block p,
.sessions-placeholder p {
  margin: 0;
  max-width: 56ch;
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.55;
}
.delete-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  background: rgba(11, 13, 16, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.delete-modal {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 20px;
  width: 400px;
  box-shadow: var(--shadow-3);
}
.delete-modal h3 {
  margin: 0 0 10px;
  font-family: var(--serif);
  font-size: 18px;
  color: var(--ink);
}
.delete-modal p {
  margin: 0 0 18px;
  font-size: 13.5px;
  color: var(--ink-soft);
  font-family: var(--sans);
  line-height: 1.55;
}
.delete-modal strong {
  color: var(--ink);
  font-weight: 600;
}
.delete-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn-danger {
  background: var(--err);
  color: var(--paper);
  border: 1px solid var(--err);
}
.btn-danger:hover:not(:disabled) {
  filter: brightness(0.95);
}
.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  flex-shrink: 0;
}
.btn-danger-ghost {
  background: transparent;
  color: var(--ink-soft);
  border: 1px solid var(--rule);
}
.btn-danger-ghost:hover:not(:disabled) {
  color: var(--err);
  border-color: var(--err);
  background: var(--paper-2);
}
.btn-danger-ghost:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
