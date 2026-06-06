<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useSessionStore } from "@/stores/session";
import { useWidgetsStore } from "@/stores/widgets";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import SlideStage from "@/components/SlideStage.vue";
import LivePollSlide from "@/components/LivePollSlide.vue";
import LiveQuestionSlide from "@/components/LiveQuestionSlide.vue";
import LiveRandomAudienceSlide from "@/components/LiveRandomAudienceSlide.vue";

const props = defineProps<{ sessionId: string }>();
const router = useRouter();
const auth = useAuthStore();
const session = useSessionStore();
const widgetsStore = useWidgetsStore();

const loading = ref(true);
const denied = ref(false);
const endedState = ref(false);
const loadError = ref<string | null>(null);

const routeToken = computed(() => {
  const raw = router.currentRoute.value.query.token;
  return typeof raw === "string" ? raw : null;
});

onMounted(async () => {
  try {
    await session.loadMirror(props.sessionId, routeToken.value);
    if (session.snapshot?.ended_at) {
      endedState.value = true;
      return;
    }
    await preloadWidgets();
    session.connect("mirror", props.sessionId, null, routeToken.value);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      if (!auth.isSignedIn) {
        await router.replace({ name: "signin", query: { next: router.currentRoute.value.fullPath } });
        return;
      }
      denied.value = true;
      return;
    }
    if (err instanceof ApiError && err.status === 410) {
      endedState.value = true;
      return;
    }
    loadError.value = err instanceof Error ? err.message : "Could not load mirror.";
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(() => {
  session.disconnect();
});

async function preloadWidgets() {
  if (!session.snapshot) return;
  const ids = new Set<string>();
  for (const slide of session.snapshot.slides) {
    for (const widget of slide.widgets) {
      if (!widget.revision) ids.add(widget.widget_id);
    }
  }
  if (!ids.size) return;

  if (routeToken.value) {
    return;
  }

  await widgetsStore.ensureLoaded([...ids]);
}

const currentDeckSlide = computed(() => {
  const snap = session.snapshot;
  if (!snap) return null;
  return snap.slides.find((s) => s.id === session.currentSlideId) || null;
});

const currentSessionSlide = computed(() => {
  const snap = session.snapshot;
  if (!snap) return null;
  return snap.session_slides.find((s) => s.id === session.currentSlideId) || null;
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

const currentSpecType = computed(() => {
  const slide = currentSessionSlide.value;
  if (!slide) return null;
  const t = (slide.spec as { type?: unknown })?.type;
  return typeof t === "string" ? t : null;
});

const statusLabel = computed(() => {
  if (loading.value) return "Connecting";
  if (denied.value) return "Denied";
  if (endedState.value || session.ended) return "Ended";
  return session.connected ? "Live" : "Reconnecting";
});
</script>

<template>
  <div
    class="mirror-shell"
    :style="{
      background: currentSessionSlide?.inverted_theme ? 'var(--ink)' : 'var(--paper)',
      color: currentSessionSlide?.inverted_theme ? 'var(--paper)' : 'var(--ink)',
    }"
  >
    <header class="mirror-header">
      <div class="mirror-brand">
        <Wordmark :size="12" />
        <span class="t-meta">·</span>
        <span class="mirror-title">{{ session.snapshot?.deck_title || "Mirror" }}</span>
      </div>
      <span class="mirror-status" :class="{ live: session.connected && !endedState && !denied }">
        <Icon name="eye" :size="13" />
        {{ statusLabel }}
      </span>
    </header>

    <main class="mirror-main">
      <div v-if="loading" class="mirror-state">Loading mirror…</div>
      <div v-else-if="denied" class="mirror-state">Mirror access denied.</div>
      <div v-else-if="endedState || session.ended" class="mirror-state">This session has ended.</div>
      <div v-else-if="loadError" class="mirror-state">{{ loadError }}</div>
      <SlideStage
        v-else-if="currentDeckSlide"
        :slide="currentDeckSlide"
        :kicker="currentKicker"
        role="preview"
        :max-width="1100"
        :interpret-enabled="false"
      />
      <LivePollSlide
        v-else-if="currentSessionSlide && currentSpecType === 'poll'"
        :slide="currentSessionSlide"
        role="mirror"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <LiveQuestionSlide
        v-else-if="currentSessionSlide && currentSpecType === 'question'"
        :slide="currentSessionSlide"
        role="mirror"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <LiveRandomAudienceSlide
        v-else-if="currentSessionSlide && currentSpecType === 'random'"
        :slide="currentSessionSlide"
        role="mirror"
        :inverted="!!currentSessionSlide.inverted_theme"
      />
      <div v-else class="mirror-state">Waiting for the presenter…</div>
    </main>
  </div>
</template>

<style scoped>
.mirror-shell {
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.mirror-header {
  height: 48px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 0 clamp(14px, 3vw, 28px);
  flex-shrink: 0;
}

.mirror-brand,
.mirror-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mirror-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--serif);
  font-size: 15px;
}

.mirror-status {
  border: 1px solid var(--rule);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--ink-soft);
  font-size: 12px;
  flex-shrink: 0;
}

.mirror-status.live {
  border-color: var(--live);
  color: var(--live);
}

.mirror-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.mirror-state {
  margin-top: clamp(80px, 18vh, 160px);
  text-align: center;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-style: italic;
}

@media (max-width: 560px) {
  .mirror-header {
    height: 46px;
  }
}
</style>
