<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { clearGuestToken, loadGuestToken, useSessionStore } from "@/stores/session";
import { maybeReceivePreviewAuth } from "@/preview/handshake";
import { useAuthStore } from "@/stores/auth";
import { useWidgetsStore } from "@/stores/widgets";
import { widgetsApi } from "@/api/widgets";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import AccountMenu from "@/components/AccountMenu.vue";
import SlideStage from "@/components/SlideStage.vue";
import RaiseQuestionSheet from "@/components/RaiseQuestionSheet.vue";
import LivePollSlide from "@/components/LivePollSlide.vue";
import LiveQuestionSlide from "@/components/LiveQuestionSlide.vue";
import LiveRandomAudienceSlide from "@/components/LiveRandomAudienceSlide.vue";
import type { GuestJoinResponse } from "@/api/types";

const props = defineProps<{ sessionId: string }>();
const router = useRouter();
const session = useSessionStore();
const auth = useAuthStore();
const widgetsStore = useWidgetsStore();

const sheetOpen = ref(false);
const toast = ref<string | null>(null);
const previewGuest = ref<GuestJoinResponse | null>(null);
const guest = computed(() => previewGuest.value ?? loadGuestToken(props.sessionId));
const inPreviewIframe = ref(false);
let toastTimer = 0;

// When embedded by the editor's Preview tab, post slide changes up so the
// preview-tab's AI Adjust chat can bind to whatever slide *this* tile is
// currently showing (the audience may have stepped backward independently
// of the presenter).
watch(
  () => session.audienceCurrentSlideId,
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

onMounted(async () => {
  window.addEventListener("keydown", onAudienceKeydown);
  // If we were embedded by the editor's preview harness, accept a token via
  // postMessage instead of redirecting to the join flow. No-op outside iframes.
  const handshake = await maybeReceivePreviewAuth(props.sessionId);
  inPreviewIframe.value = handshake.isPreview;
  previewGuest.value = handshake.guest;
  if (!guest.value) {
    await router.replace(exitDestination());
    return;
  }
  try {
    await session.loadAudience(props.sessionId, guest.value);
    await preloadWidgets();
    session.connect("audience", props.sessionId, guest.value);
  } catch (err) {
    // Snapshot fetch failed (expired/ended session, wrong token, or direct URL
    // without a valid registration for this session).
    clearGuestToken(props.sessionId);
    await router.replace(exitDestination());
    console.warn(err);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onAudienceKeydown);
  session.disconnect();
  window.clearTimeout(toastTimer);
});

watch(
  () => session.ended,
  (isEnded) => {
    if (isEnded) {
      clearGuestToken(props.sessionId);
      router.replace(exitDestination());
    }
  },
);

function exitDestination() {
  return { name: auth.isSignedIn ? "workspace" : "signin" };
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function onAudienceKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
  if (sheetOpen.value || isEditableTarget(event.target)) return;

  if (event.key === "ArrowLeft" && session.canAudienceStepPrev) {
    event.preventDefault();
    session.stepAudienceSlide(-1);
  } else if (event.key === "ArrowRight" && session.canAudienceStepNext) {
    event.preventDefault();
    session.stepAudienceSlide(1);
  }
}

async function preloadWidgets() {
  if (!session.snapshot) return;
  const token = guest.value?.token;
  if (!token) return;
  const ids = new Set<string>();
  for (const s of session.snapshot.slides) {
    for (const w of s.widgets) ids.add(w.widget_id);
  }
  await Promise.all(
    [...ids]
      .filter((id) => !widgetsStore.cache[id])
      .map(async (id) => {
        try {
          const widget = await widgetsApi.getAs(id, token);
          widgetsStore.cache[id] = widget;
        } catch (err) {
          console.warn("widget fetch failed", id, err);
        }
      }),
  );
}

const currentDeckSlide = computed(() => {
  const snap = session.snapshot;
  if (!snap) return null;
  return snap.slides.find((s) => s.id === session.audienceCurrentSlideId) || null;
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
  return snap.session_slides.find((s) => s.id === session.audienceCurrentSlideId) || null;
});

const interpretQuickOptions = computed(() => {
  const snap = session.snapshot;
  return snap && "interpret_quick_options" in snap ? snap.interpret_quick_options || [] : [];
});

const audienceStepPosition = computed(() => (session.audienceStepIndex >= 0 ? session.audienceStepIndex + 1 : 0));
const audienceStepTotal = computed(() => session.audiencePassedSlides.length);
// Audiences can only navigate within the slides the presenter has already
// visited (the "seen" set). When that's a subset of the deck, show both
// counts so "6 / 6" doesn't look like the deck ended — e.g. "6 / 6 · 10".
const deckTotal = computed(() => session.presentationOrder.length);
const showDeckTotal = computed(
  () => deckTotal.value > 0 && audienceStepTotal.value < deckTotal.value,
);

const currentSpecType = computed(() => {
  const slide = currentSessionSlide.value;
  if (!slide) return null;
  const t = (slide.spec as any)?.type;
  return typeof t === "string" ? t : null;
});

const audiencePaginationItems = computed(() => {
  const slides = session.audiencePassedSlides;
  const total = slides.length;
  const active = session.audienceStepIndex;
  if (total <= 7 || active < 0) {
    return slides.map((slide, index) => ({ slide, index }));
  }

  const windowSize = 7;
  const radius = Math.floor(windowSize / 2);
  let start = Math.max(0, active - radius);
  let end = Math.min(total - 1, start + windowSize - 1);
  if (end - start + 1 < windowSize) {
    start = Math.max(0, end - windowSize + 1);
  }

  const items: Array<{ slide: (typeof slides)[number]; index: number }> = [];
  for (let index = start; index <= end; index += 1) {
    items.push({ slide: slides[index], index });
  }
  return items;
});

const audiencePaginationHasHiddenBefore = computed(() => {
  const first = audiencePaginationItems.value[0];
  return !!first && first.index > 0;
});

const audiencePaginationHasHiddenAfter = computed(() => {
  const last = audiencePaginationItems.value[audiencePaginationItems.value.length - 1];
  return !!last && last.index < session.audiencePassedSlides.length - 1;
});

function exitToJoin() {
  clearGuestToken(props.sessionId);
  router.replace(exitDestination());
}

function signOut() {
  clearGuestToken(props.sessionId);
  auth.signOut();
  router.replace({ name: "signin" });
}

function onSubmitQuestion({ text, anonymous }: { text: string; anonymous: boolean }) {
  session.raiseQuestion(text, anonymous);
  sheetOpen.value = false;
  showToast("Question sent to instructor.");
}

function showToast(message: string) {
  toast.value = message;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toast.value = null;
  }, 2200);
}
</script>

<template>
  <div
    class="audience-shell"
    :style="{
      background: currentSessionSlide?.inverted_theme ? 'var(--ink)' : 'var(--paper)',
      color: currentSessionSlide?.inverted_theme ? 'var(--paper)' : 'var(--ink)',
    }"
  >
    <header
      class="audience-header"
    >
      <button
        v-if="!inPreviewIframe"
        class="btn btn-ghost btn-sm"
        @click="exitToJoin"
        title="Leave session"
      >
        <Icon name="x" :size="14" />
      </button>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '8px' }">
        <Wordmark :size="12" />
        <span
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            padding: '1px 8px',
            borderRadius: 'var(--r-xs)',
            background: 'var(--live)',
            color: 'var(--paper)',
            fontSize: '10px',
            fontWeight: 700,
            letterSpacing: '.08em',
          }"
        >
          <span :style="{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--paper)' }" />
          LIVE
        </span>
      </div>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '10px' }">
        <span class="t-meta" :style="{ fontSize: '11px' }">
          {{ session.audienceCount }} <Icon name="users" :size="11" />
        </span>
        <AccountMenu
          v-if="!inPreviewIframe"
          :user-name="auth.user?.display_name || guest?.display_name"
          :user-email="auth.user?.email || (guest?.anon ? 'Anonymous audience' : 'Audience member')"
          @sign-out="signOut"
        />
      </div>
    </header>

    <main class="audience-main">
      <SlideStage
        v-if="currentDeckSlide"
        :slide="currentDeckSlide"
        :kicker="currentKicker"
        role="audience"
        :max-width="1040"
        :interpret-enabled="true"
        :interpret-token="guest?.token"
        :interpret-context="{
          role: 'audience',
          session_id: session.snapshot?.id,
          slide_id: currentDeckSlide.id,
          deck_title: session.snapshot?.deck_title,
        }"
        :interpret-quick-options="interpretQuickOptions"
        :participant="{
          display_name: guest?.display_name ?? null,
          anon: guest?.anon ?? false,
          ref: guest?.participant_ref ?? null,
        }"
        @widget-event="(e) => session.forwardWidgetEvent(e.placement, { type: e.type, payload: e.payload })"
      />
      <LivePollSlide
        v-else-if="currentSessionSlide && currentSpecType === 'poll'"
        :slide="currentSessionSlide"
        role="audience"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <LiveQuestionSlide
        v-else-if="currentSessionSlide && currentSpecType === 'question'"
        :slide="currentSessionSlide"
        role="audience"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <LiveRandomAudienceSlide
        v-else-if="currentSessionSlide && currentSpecType === 'random'"
        :slide="currentSessionSlide"
        role="audience"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <div
        v-else-if="currentSessionSlide"
        class="audience-interaction"
      >
        <div class="t-kicker" :style="{ marginBottom: '14px' }">{{ currentSessionSlide.kind }}</div>
        <div class="audience-interaction-title">
          {{ (currentSessionSlide.spec as any)?.prompt || "Live interaction" }}
        </div>
      </div>
      <div
        v-else
        class="audience-waiting"
      >
        Waiting for the presenter…
      </div>
    </main>

    <button
      v-if="!(currentSessionSlide && currentSpecType === 'question')"
      class="btn btn-primary audience-question-fab"
      data-testid="audience-raise-question-fab"
      aria-label="Raise question"
      title="Raise question"
      @click="sheetOpen = true"
    >
      ?
    </button>

    <footer class="audience-footer audience-footer-sticky" data-testid="audience-stepper">
      <button
        class="btn btn-ghost btn-sm"
        data-testid="audience-step-prev"
        :disabled="!session.canAudienceStepPrev"
        @click="session.stepAudienceSlide(-1)"
      >
        <Icon name="chev_left" :size="16" /> Prev
      </button>

      <div class="audience-step-center" aria-label="Slide history controls">
        <div
          class="audience-step-window"
          data-testid="audience-step-window"
          :class="{
            'has-fade-left': audiencePaginationHasHiddenBefore,
            'has-fade-right': audiencePaginationHasHiddenAfter,
          }"
        >
          <span
            v-if="audiencePaginationHasHiddenBefore"
            class="audience-step-fade audience-step-fade-left"
            data-testid="audience-step-fade-left"
            aria-hidden="true"
          />
          <span
            v-if="audiencePaginationHasHiddenAfter"
            class="audience-step-fade audience-step-fade-right"
            data-testid="audience-step-fade-right"
            aria-hidden="true"
          />
          <div class="audience-step-dots">
            <button
              v-for="item in audiencePaginationItems"
              :key="item.slide.id"
              type="button"
              data-testid="audience-step-dot"
              :title="`Slide ${item.index + 1}`"
              :aria-label="`Go to slide ${item.index + 1}`"
              :class="{ active: item.index === session.audienceStepIndex }"
              @click="session.goToAudienceSlide(item.slide.id)"
            />
          </div>
        </div>
        <span class="audience-step-status" data-testid="audience-step-status">
          {{ audienceStepPosition }} / {{ audienceStepTotal }}<template v-if="showDeckTotal"> · {{ deckTotal }} total</template>
        </span>
      </div>

      <button
        class="btn btn-ghost btn-sm"
        data-testid="audience-step-next"
        :disabled="!session.canAudienceStepNext"
        @click="session.stepAudienceSlide(1)"
      >
        Next <Icon name="chev_right" :size="16" />
      </button>
    </footer>

    <RaiseQuestionSheet
      v-if="sheetOpen"
      :default-anon="guest?.anon ?? false"
      @submit="onSubmitQuestion"
      @close="sheetOpen = false"
    />

    <transition name="fade">
      <div v-if="toast" class="audience-toast" role="status" aria-live="polite">
        {{ toast }}
      </div>
    </transition>
  </div>
</template>

<style scoped>
.audience-shell {
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.audience-header {
  height: 52px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(14px, 3vw, 28px);
  flex-shrink: 0;
}

.audience-main {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.audience-interaction {
  width: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: clamp(64px, 14vh, 132px) clamp(22px, 6vw, 64px);
  text-align: center;
}

.audience-interaction-title {
  font-family: var(--serif);
  font-size: clamp(28px, 5vw, 48px);
  line-height: 1.18;
}

.audience-waiting {
  margin-top: 120px;
  text-align: center;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-style: italic;
}

.audience-footer {
  height: 48px;
  border-top: 1px solid var(--rule);
  background: var(--paper);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  flex-shrink: 0;
}

.audience-footer-sticky {
  position: sticky;
  bottom: 0;
  z-index: 30;
}

.audience-step-center {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.audience-step-window {
  position: relative;
  overflow: hidden;
}

.audience-step-window.has-fade-left .audience-step-dots {
  padding-left: 8px;
}

.audience-step-window.has-fade-right .audience-step-dots {
  padding-right: 8px;
}

.audience-step-fade {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 18px;
  z-index: 1;
  pointer-events: none;
}

.audience-step-fade-left {
  left: 0;
  background: linear-gradient(90deg, var(--paper), transparent);
}

.audience-step-fade-right {
  right: 0;
  background: linear-gradient(270deg, var(--paper), transparent);
}

.audience-step-dots {
  display: flex;
  align-items: center;
  gap: 6px;
}

.audience-step-dots button {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border: none;
  border-radius: 50%;
  padding: 0;
  background: var(--rule-strong);
  cursor: pointer;
  transition: background 0.15s ease, width 0.15s ease, height 0.15s ease;
}

.audience-step-dots button.active {
  width: 9px;
  height: 9px;
  background: var(--ink);
}

.audience-step-status {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 12px;
}

.audience-question-fab {
  position: fixed;
  right: 28px;
  bottom: calc(92px + env(safe-area-inset-bottom));
  z-index: 40;
  width: 56px;
  height: 56px;
  border-radius: 999px;
  padding: 0;
  justify-content: center;
  box-shadow: var(--shadow-3);
  font-family: var(--serif);
  font-size: 26px;
  line-height: 1;
}

.audience-toast {
  position: fixed;
  left: 50%;
  bottom: calc(78px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  z-index: 80;
  max-width: min(360px, calc(100vw - 32px));
  padding: 11px 16px;
  border-radius: var(--r-md);
  background: var(--ink);
  color: var(--paper);
  box-shadow: var(--shadow-3);
  font-family: var(--sans);
  font-size: 13px;
  text-align: center;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 560px) {
  .audience-header {
    height: 48px;
  }

  .audience-footer {
    padding: 0 10px;
  }

  .audience-step-dots {
    max-width: 92px;
    overflow: hidden;
  }

  .audience-question-fab {
    right: 28px;
    bottom: calc(92px + env(safe-area-inset-bottom));
    width: 52px;
    height: 52px;
  }
}
</style>
