<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { maybeReceivePreviewAuth } from "@/preview/handshake";
import { useRouter } from "vue-router";
import { sessionsApi } from "@/api/sessions";
import { useAuthStore } from "@/stores/auth";
import { useSessionStore } from "@/stores/session";
import { useWidgetsStore } from "@/stores/widgets";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import AccountMenu from "@/components/AccountMenu.vue";
import SlideStage from "@/components/SlideStage.vue";
import PresenterRail from "@/components/PresenterRail.vue";
import OpenInteractionFab from "@/components/OpenInteractionFab.vue";
import LiveInteractionSheet from "@/components/LiveInteractionSheet.vue";
import LivePollSlide from "@/components/LivePollSlide.vue";
import LiveQuestionSlide from "@/components/LiveQuestionSlide.vue";
import LiveRandomAudienceSlide from "@/components/LiveRandomAudienceSlide.vue";
import AnswerModerationRail from "@/components/AnswerModerationRail.vue";
import type { SessionSnapshot } from "@/api/types";

const props = defineProps<{ sessionId: string }>();
const router = useRouter();
const auth = useAuthStore();
const session = useSessionStore();
const widgetsStore = useWidgetsStore();

// Questions rail starts collapsed so the presenter has full slide focus by
// default; they can pop it open from the toolbar button when they want to
// triage incoming questions.
const railOpen = ref(false);
const copied = ref(false);
const mirrorCopied = ref(false);
const mirrorBusy = ref(false);
const endConfirmOpen = ref(false);
const endingBusy = ref(false);

const inPreviewIframe = ref(false);

// Wall-clock tick driving the elapsed-time counter. Updated once a second; the
// formatting (00:00:00) is derived in the `elapsed` computed from the session's
// started_at so a reconnect/snapshot reload keeps the count correct.
const now = ref(Date.now());
let clockTimer: number | undefined;

const elapsed = computed(() => {
  const startedAt = session.snapshot?.started_at;
  const start = startedAt ? new Date(startedAt).getTime() : NaN;
  if (!Number.isFinite(start)) return "00:00:00";
  const totalSec = Math.max(0, Math.floor((now.value - start) / 1000));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(totalSec / 3600))}:${pad(Math.floor((totalSec % 3600) / 60))}:${pad(totalSec % 60)}`;
});

onMounted(async () => {
  window.addEventListener("keydown", onPresenterKeydown);
  clockTimer = window.setInterval(() => (now.value = Date.now()), 1000);
  // Preview-iframe handshake: when embedded by the editor's preview tab the
  // parent posts inspector state; we also use this to know that we should
  // forward slide changes back up so the chat panel stays in sync.
  const handshake = await maybeReceivePreviewAuth(props.sessionId);
  inPreviewIframe.value = handshake.isPreview;
  await session.loadHost(props.sessionId);
  await preloadWidgets();
  session.connect("host", props.sessionId);
});

// When running inside the preview tab, post the current slide id up so
// Preview.vue can rebind the AI Adjust chat to that slide's widget. Fires
// whether the change came from this iframe (keyboard nav) or from a WS
// broadcast triggered by another tile.
watch(
  () => session.snapshot?.current_slide_id,
  (id) => {
    if (!inPreviewIframe.value || !id || window.parent === window) return;
    try {
      window.parent.postMessage(
        { slaides: true, type: "preview.slide-changed", sessionId: props.sessionId, slideId: id },
        "*",
      );
    } catch {
      // Same-origin in preview; defensive.
    }
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onPresenterKeydown);
  if (clockTimer) window.clearInterval(clockTimer);
  session.disconnect();
});

async function preloadWidgets() {
  if (!session.snapshot) return;
  const ids = new Set<string>();
  for (const s of session.snapshot.slides) {
    for (const w of s.widgets) ids.add(w.widget_id);
  }
  if (ids.size) await widgetsStore.ensureLoaded([...ids]);
}

const currentDeckSlide = computed(() => {
  const snap = session.snapshot;
  if (!snap) return null;
  return snap.slides.find((s) => s.id === snap.current_slide_id) || null;
});

const currentKicker = computed(() => {
  const snap = session.snapshot;
  const slide = currentDeckSlide.value;
  if (!snap || !slide) return null;
  const idx = snap.slides.findIndex((s) => s.id === slide.id);
  const page = String(idx + 1).padStart(2, "0");
  const section = snap.sections.find((sec) => sec.id === slide.section_id);
  const label = section?.title?.trim() || "Unsectioned";
  return `§ ${page} — ${label}`;
});

const currentSessionSlide = computed(() => {
  const snap = session.snapshot;
  if (!snap) return null;
  return snap.session_slides.find((s) => s.id === snap.current_slide_id) || null;
});

const fullSnapshot = computed<SessionSnapshot | null>(() => {
  const snap = session.snapshot;
  return snap && "questions" in snap ? snap : null;
});

const presenterNotes = computed<string | null>(() => {
  const slide = currentDeckSlide.value;
  const notes = slide && "presenter_notes" in slide ? slide.presenter_notes : null;
  return typeof notes === "string" ? notes : null;
});

const presentationOrder = computed(() => {
  const snap = session.snapshot;
  if (!snap) return [];
  const byParent = new Map<string, typeof snap.session_slides>();
  const orphans: typeof snap.session_slides = [];
  for (const sessionSlide of snap.session_slides) {
    if (!sessionSlide.parent_slide_id) {
      orphans.push(sessionSlide);
      continue;
    }
    const group = byParent.get(sessionSlide.parent_slide_id) || [];
    group.push(sessionSlide);
    byParent.set(sessionSlide.parent_slide_id, group);
  }

  const ordered = [];
  for (const slide of snap.slides) {
    ordered.push(slide);
    const inserted = byParent.get(slide.id) || [];
    ordered.push(...inserted.slice().sort((a, b) => a.position - b.position));
  }
  ordered.push(...orphans.slice().sort((a, b) => a.position - b.position));
  return ordered;
});

const activePresentationIndex = computed(() => {
  const snap = session.snapshot;
  if (!snap) return -1;
  return presentationOrder.value.findIndex((s) => s.id === snap.current_slide_id);
});

const canGoPrev = computed(() => activePresentationIndex.value > 0);
const canGoNext = computed(
  () => activePresentationIndex.value >= 0 && activePresentationIndex.value < presentationOrder.value.length - 1,
);

const unanswered = computed(
  () => fullSnapshot.value?.questions.filter((q) => !q.answered_at).length ?? 0,
);

async function copyCode() {
  const code = fullSnapshot.value?.code;
  if (!code) return;
  try {
    await navigator.clipboard.writeText(`${window.location.origin}/j/${code}`);
    copied.value = true;
    window.setTimeout(() => (copied.value = false), 1500);
  } catch {
    // ignore
  }
}

async function copyMirrorLink(event?: MouseEvent) {
  if (!session.snapshot) return;
  const openInNewTab = !!event?.ctrlKey || !!event?.metaKey;
  const tab = openInNewTab ? window.open("about:blank", "_blank") : null;
  mirrorBusy.value = true;
  try {
    const link = await sessionsApi.mirrorLink(session.snapshot.id);
    const absolute = new URL(link.url, window.location.origin).toString();
    if (openInNewTab) {
      if (tab) {
        tab.opener = null;
        tab.location.href = absolute;
      } else {
        window.open(absolute, "_blank", "noopener,noreferrer");
      }
      return;
    }
    await navigator.clipboard.writeText(absolute);
    mirrorCopied.value = true;
    window.setTimeout(() => (mirrorCopied.value = false), 1500);
  } finally {
    mirrorBusy.value = false;
  }
}

function nextSlide() {
  const snap = session.snapshot;
  if (!snap) return;
  const order = presentationOrder.value;
  const idx = order.findIndex((s) => s.id === snap.current_slide_id);
  if (idx === -1) {
    if (order[0]) session.advanceTo(order[0].id, !!snap.session_slides.find((s) => s.id === order[0].id));
    return;
  }
  const next = order[idx + 1];
  if (next) session.advanceTo(next.id, !!snap.session_slides.find((s) => s.id === next.id));
}

function prevSlide() {
  const snap = session.snapshot;
  if (!snap) return;
  const order = presentationOrder.value;
  const idx = order.findIndex((s) => s.id === snap.current_slide_id);
  if (idx > 0) {
    const prev = order[idx - 1];
    session.advanceTo(prev.id, !!snap.session_slides.find((s) => s.id === prev.id));
  }
}

function isSessionSlideId(id: string) {
  return !!session.snapshot?.session_slides.find((s) => s.id === id);
}

function selectPresentationSlide(id: string) {
  session.advanceTo(id, isSessionSlideId(id));
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function onPresenterKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
  if (sheetKind.value || endConfirmOpen.value || isEditableTarget(event.target)) return;
  if (event.key === "ArrowRight") {
    event.preventDefault();
    nextSlide();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    prevSlide();
  }
}

const sheetKind = ref<"poll" | "question" | "random" | null>(null);

function openSheet(kind: "poll" | "question" | "random") {
  sheetKind.value = kind;
}

async function launchFromSheet(payload: {
  kind: "poll" | "question" | "random";
  spec: Record<string, unknown>;
}) {
  const parentSlideId = currentSessionSlide.value?.parent_slide_id ?? session.snapshot?.current_slide_id ?? null;
  await session.openInteraction({
    kind: payload.kind,
    parent_slide_id: parentSlideId,
    spec: payload.spec,
    inverted_theme: false,
  });
  sheetKind.value = null;
}

const currentSpecType = computed(() => {
  const slide = currentSessionSlide.value;
  if (!slide) return null;
  const t = (slide.spec as any)?.type;
  return typeof t === "string" ? t : null;
});

function confirmEnd() {
  endConfirmOpen.value = true;
}

function presenterExitDestination() {
  // Send the presenter back to the editor for THIS deck so they can keep
  // iterating on the same content. Falls back to the workspace if the
  // snapshot is somehow missing (e.g. end fired before loadHost finished).
  const deckId = session.snapshot?.deck_id;
  return deckId ? `/editor/${deckId}` : "/workspace";
}

async function endNow() {
  endingBusy.value = true;
  const destination = presenterExitDestination();
  try {
    await session.endSession();
  } catch (err) {
    console.warn("end session failed", err);
  } finally {
    endingBusy.value = false;
    endConfirmOpen.value = false;
    await router.push(destination);
  }
}

function signOut() {
  auth.signOut();
  router.push("/signin");
}

watch(
  () => session.ended,
  (isEnded) => {
    if (isEnded && session.role === "host") {
      router.push(presenterExitDestination());
    }
  },
);
</script>

<template>
  <div :style="{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--paper)' }">
    <!-- Top bar -->
    <header
      :style="{
        height: '52px',
        borderBottom: '1px solid var(--rule)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 18px',
        flexShrink: 0,
      }"
    >
      <div :style="{ display: 'flex', alignItems: 'center', gap: '14px' }">
        <button
          v-if="!inPreviewIframe"
          class="btn btn-ghost btn-sm"
          @click="confirmEnd"
          title="End session"
        >
          <Icon name="x" :size="16" />
        </button>
        <Wordmark :size="14" />
        <span class="t-meta">·</span>
        <span :style="{ fontFamily: 'var(--serif)', fontSize: '15px' }">
          {{ session.snapshot?.deck_title || "Session" }}
        </span>
        <span
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '2px 9px',
            borderRadius: 'var(--r-xs)',
            background: 'var(--live)',
            color: 'var(--paper)',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '.08em',
          }"
        >
          <span :style="{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--paper)' }" />
          LIVE
        </span>
      </div>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '10px' }">
        <span
          class="t-mono"
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            padding: '4px 10px',
            border: '1px solid var(--rule)',
            borderRadius: '999px',
            fontSize: '12px',
            fontVariantNumeric: 'tabular-nums',
          }"
          title="Elapsed time"
        >
          <Icon name="clock" :size="14" />
          {{ elapsed }}
        </span>
        <span
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            padding: '4px 10px',
            border: '1px solid var(--rule)',
            borderRadius: '999px',
            fontSize: '12px',
          }"
        >
          <Icon name="users" :size="14" />
          {{ session.audienceCount }}
        </span>
        <button class="btn btn-sm" @click="railOpen = !railOpen" :title="railOpen ? 'Hide questions' : 'Show questions'">
          ? <span v-if="unanswered" :style="{ color: 'var(--err)' }">·{{ unanswered }}</span>
        </button>
        <button class="btn btn-sm" @click="copyCode">
          <Icon name="copy" :size="14" />
          {{ copied ? "Copied" : fullSnapshot?.code || "…" }}
        </button>
        <button
          v-if="!inPreviewIframe"
          class="btn btn-sm"
          :disabled="mirrorBusy"
          @click="copyMirrorLink"
          title="Copy mirror link"
        >
          <Icon name="copy" :size="14" />
          {{ mirrorCopied ? "Mirror copied" : "Mirror" }}
        </button>
        <AccountMenu
          v-if="!inPreviewIframe"
          :user-name="auth.user?.display_name"
          :user-email="auth.user?.email"
          @sign-out="signOut"
        />
      </div>
    </header>

    <div :style="{ flex: 1, display: 'flex', minHeight: 0 }">
      <main
        :style="{
          flex: 1,
          overflowY: 'auto',
          background: currentSessionSlide?.inverted_theme ? 'var(--ink)' : 'var(--paper)',
          color: currentSessionSlide?.inverted_theme ? 'var(--paper)' : 'var(--ink)',
        }"
      >
        <SlideStage
          v-if="currentDeckSlide"
          :slide="currentDeckSlide"
          :kicker="currentKicker"
          role="instructor"
          :interpret-enabled="true"
          :interpret-context="{
            role: 'presenter',
            session_id: session.snapshot?.id,
            slide_id: currentDeckSlide.id,
            deck_title: session.snapshot?.deck_title,
          }"
          :interpret-quick-options="fullSnapshot?.interpret_quick_options || []"
          @widget-event="(e) => session.forwardWidgetEvent(e.placement, { type: e.type, payload: e.payload })"
        />
        <LivePollSlide
          v-else-if="currentSessionSlide && currentSpecType === 'poll'"
          :slide="currentSessionSlide"
          role="presenter"
          :inverted="!!currentSessionSlide.inverted_theme"
        />
        <LiveQuestionSlide
          v-else-if="currentSessionSlide && currentSpecType === 'question'"
          :slide="currentSessionSlide"
          role="presenter"
          :inverted="!!currentSessionSlide.inverted_theme"
        />
        <LiveRandomAudienceSlide
          v-else-if="currentSessionSlide && currentSpecType === 'random'"
          :slide="currentSessionSlide"
          role="presenter"
          :inverted="!!currentSessionSlide.inverted_theme"
        />
        <div
          v-else-if="currentSessionSlide"
          :style="{
            maxWidth: '900px',
            margin: '0 auto',
            padding: '120px 64px',
            textAlign: 'center',
          }"
        >
          <div class="t-kicker" :style="{ marginBottom: '20px' }">Interaction · {{ currentSessionSlide.kind }}</div>
          <div :style="{ fontFamily: 'var(--serif)', fontSize: '40px', lineHeight: 1.2 }">
            {{ (currentSessionSlide.spec as any)?.prompt || "Live interaction" }}
          </div>
        </div>
        <div
          v-else
          :style="{
            marginTop: '120px',
            textAlign: 'center',
            color: 'var(--ink-soft)',
            fontFamily: 'var(--serif)',
            fontStyle: 'italic',
          }"
        >
          Loading session…
        </div>
      </main>

      <AnswerModerationRail
        v-if="currentSessionSlide && currentSpecType === 'question'"
        :slide="currentSessionSlide"
      />
      <PresenterRail
        v-else-if="railOpen"
        :notes="presenterNotes"
        :questions="fullSnapshot?.questions || []"
        @answer="(id) => session.markAnswered(id)"
      />
    </div>

    <!-- Bottom stepper -->
    <footer
      :style="{
        height: '48px',
        borderTop: '1px solid var(--rule)',
        background: 'var(--paper)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 18px',
        flexShrink: 0,
      }"
    >
      <button class="btn btn-ghost btn-sm" :disabled="!canGoPrev" @click="prevSlide">
        <Icon name="chev_left" :size="16" /> Prev
      </button>

      <div :style="{ display: 'flex', alignItems: 'center', gap: '14px' }">
        <div :style="{ display: 'flex', gap: '6px', alignItems: 'center' }">
          <button
            v-for="(s, i) in presentationOrder"
            :key="s.id"
            type="button"
            @click="selectPresentationSlide(s.id)"
            :title="`Slide ${i + 1}`"
            :aria-label="`Go to slide ${i + 1}`"
            :style="{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              background: i === activePresentationIndex ? 'var(--ink)' : 'var(--rule-strong)',
              transition: 'background .15s ease',
            }"
          />
        </div>
        <span class="t-mono" :style="{ color: 'var(--ink-soft)' }">
          {{ activePresentationIndex >= 0 ? activePresentationIndex + 1 : "—" }} / {{ presentationOrder.length }}
        </span>
      </div>

      <button class="btn btn-ghost btn-sm" :disabled="!canGoNext" @click="nextSlide">
        Next <Icon name="chev_right" :size="16" />
      </button>
    </footer>

    <OpenInteractionFab v-if="!sheetKind" @pick="openSheet" />

    <LiveInteractionSheet
      v-if="sheetKind"
      :kind="sheetKind"
      @close="sheetKind = null"
      @launch="launchFromSheet"
    />

    <div
      v-if="endConfirmOpen"
      class="fade-in"
      :style="{
        position: 'fixed',
        inset: 0,
        background: 'rgba(11,13,16,0.42)',
        zIndex: 80,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }"
      @click.self="endConfirmOpen = false"
    >
      <div
        class="scale-in"
        :style="{
          background: 'var(--paper)',
          color: 'var(--ink)',
          borderRadius: 'var(--r-lg)',
          padding: '24px',
          width: '340px',
          boxShadow: 'var(--shadow-4)',
        }"
      >
        <div class="t-h3" :style="{ marginBottom: '8px' }">End this session?</div>
        <p class="t-meta" :style="{ marginBottom: '20px' }">
          The audience will be disconnected. The transcript will be available on the workspace.
        </p>
        <div :style="{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }">
          <button class="btn btn-ghost btn-sm" @click="endConfirmOpen = false" :disabled="endingBusy">
            Cancel
          </button>
          <button class="btn btn-primary btn-sm" @click="endNow" :disabled="endingBusy">
            {{ endingBusy ? "Ending…" : "End session" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
