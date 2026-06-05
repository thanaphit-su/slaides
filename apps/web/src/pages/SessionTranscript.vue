<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { analyticsApi, type TranscriptEvent, type SlideSummary, type ParticipantSummary } from "@/api/analytics";
import { sessionsApi } from "@/api/sessions";
import { useSessionStore } from "@/stores/session";
import type { SessionSnapshot, SessionSlide, Slide } from "@/api/types";
import Icon from "@/components/Icon.vue";
import Wordmark from "@/components/Wordmark.vue";
import SlideStage from "@/components/SlideStage.vue";
import LivePollSlide from "@/components/LivePollSlide.vue";
import LiveQuestionSlide from "@/components/LiveQuestionSlide.vue";
import LiveRandomAudienceSlide from "@/components/LiveRandomAudienceSlide.vue";

const route = useRoute();
const router = useRouter();
const sessionId = route.params.sessionId as string;

const loading = ref(true);
const error = ref<string | null>(null);
const events = ref<TranscriptEvent[]>([]);
const total = ref(0);
const perSlide = ref<SlideSummary[]>([]);
const perParticipant = ref<ParticipantSummary[]>([]);
const preMigrationWarning = ref<string | null>(null);
const snapshot = ref<SessionSnapshot | null>(null);

const activeTab = ref<"timeline" | "per-slide" | "per-participant">("timeline");
const availableTypes = ref<string[]>([]);
const activeTypes = ref<Set<string>>(new Set());

const PAGE_SIZE = 500;
const offset = ref(0);
const hasMore = ref(false);

// Index of the timeline event whose state the slide pane shows. Null = last event.
const selectedEventIdx = ref<number | null>(null);
// Manual slide override (set by Prev/Next). When non-null, takes priority over the focused event.
const manualSlideId = ref<string | null>(null);

async function fetchTranscript(append = false) {
  loading.value = true;
  error.value = null;
  try {
    const data = await analyticsApi.transcript(sessionId, PAGE_SIZE, offset.value);

    if (append) {
      events.value = [...events.value, ...data.events];
    } else {
      events.value = data.events;
      total.value = data.total;
      perSlide.value = data.per_slide;
      perParticipant.value = data.per_participant;
      preMigrationWarning.value = data.pre_migration_warning || null;
      selectedEventIdx.value = null;
      manualSlideId.value = null;

      const types = Array.from(new Set(data.events.map((e) => e.event_type))).sort();
      availableTypes.value = types;
      activeTypes.value = new Set(types);
    }

    hasMore.value = data.has_more;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to load transcript";
  } finally {
    loading.value = false;
  }
}

const sessionStore = useSessionStore();

async function fetchSnapshot() {
  try {
    snapshot.value = await sessionsApi.get(sessionId);
    // Hydrate the session store so Loud-widget iframes mounted by SlideStage
    // boot with the persisted final state (poll tallies, etc.). We skip the
    // store's `loadHost` because it would also try to open a WebSocket.
    sessionStore.hydratePlacementStates(snapshot.value?.placement_states || []);
  } catch {
    snapshot.value = null;
    sessionStore.hydratePlacementStates([]);
  }
}

function loadMore() {
  if (!hasMore.value) return;
  offset.value += PAGE_SIZE;
  fetchTranscript(true);
}

function downloadCsv() {
  analyticsApi.downloadTranscriptCsv(sessionId);
  exportMenuOpen.value = false;
}

function downloadJson() {
  analyticsApi.downloadTranscriptJson(sessionId);
  exportMenuOpen.value = false;
}

function backToSessions() {
  void router.push({ path: "/workspace", query: { tab: "sessions" } });
}

const exportMenuOpen = ref(false);
const exportMenuEl = ref<HTMLElement | null>(null);

function toggleExportMenu() {
  exportMenuOpen.value = !exportMenuOpen.value;
}

function onDocumentClick(e: MouseEvent) {
  const target = e.target;
  if (!(target instanceof Node)) return;
  if (exportMenuEl.value?.contains(target)) return;
  exportMenuOpen.value = false;
}

const showDeleteConfirm = ref(false);
const deleting = ref(false);

async function deleteTranscript() {
  deleting.value = true;
  try {
    const result = await analyticsApi.deleteTranscript(sessionId);
    offset.value = 0;
    await fetchTranscript();
    showDeleteConfirm.value = false;
    alert(`Deleted ${result.deleted_events} slide/LLM events. Poll votes and questions preserved.`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to delete transcript";
  } finally {
    deleting.value = false;
  }
}

function getEventIcon(eventType: string): string {
  if (eventType === "slide.advance") return "arrow_right";
  if (eventType === "question.raised") return "help";
  if (eventType === "llm.interpret") return "auto_awesome";
  if (eventType.startsWith("interaction.opened")) return "add";
  if (eventType.startsWith("interaction.closed")) return "close";
  if (eventType.startsWith("interaction.")) return "poll";
  return "circle";
}

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function eventSummary(e: TranscriptEvent): string {
  const p = e.payload as Record<string, unknown>;
  if (e.event_type === "slide.advance") {
    const toId = (p.to_id as string | undefined) || "";
    const slide = snapshot.value?.slides.find((s) => s.id === toId);
    if (slide) return `Slide ${slide.position + 1}${slide.kicker ? ` · ${slide.kicker}` : ""}`;
    return toId ? `→ ${toId.slice(0, 8)}` : "Advance";
  }
  if (e.event_type === "question.raised") {
    const text = (p.text as string | undefined) || "";
    return text.length > 80 ? text.slice(0, 80) + "…" : text;
  }
  if (e.event_type === "llm.interpret") {
    const sel = (p.selection as string | undefined) || (p.prompt as string | undefined) || "";
    return sel.length > 80 ? sel.slice(0, 80) + "…" : sel || "Interpret";
  }
  if (e.event_type === "interaction.opened" || e.event_type === "interaction.closed") {
    return (p.kind as string | undefined) || "";
  }
  const ref = (p.participant_ref as string | undefined) || "";
  return ref ? `Participant ${ref.slice(0, 8)}` : "";
}

const visibleEvents = computed(() => {
  return events.value.filter((e) => activeTypes.value.has(e.event_type));
});

const deletableEventCount = computed(() => {
  return events.value.filter((e) => e.source === "session_event").length;
});

const focusedEvent = computed<TranscriptEvent | null>(() => {
  if (selectedEventIdx.value === null) return events.value[events.value.length - 1] || null;
  return events.value[selectedEventIdx.value] || null;
});

/**
 * Mirror of Presenter.vue's presentationOrder (lines 101–124):
 * deck slides interleaved with their child session-slides by parent_slide_id.
 * Orphan session-slides are appended.
 */
const presentationOrder = computed<(Slide | SessionSlide)[]>(() => {
  const snap = snapshot.value;
  if (!snap) return [];
  const byParent = new Map<string, SessionSlide[]>();
  const orphans: SessionSlide[] = [];
  for (const ss of snap.session_slides) {
    if (!ss.parent_slide_id) {
      orphans.push(ss);
      continue;
    }
    const group = byParent.get(ss.parent_slide_id) || [];
    group.push(ss);
    byParent.set(ss.parent_slide_id, group);
  }
  const ordered: (Slide | SessionSlide)[] = [];
  for (const slide of snap.slides) {
    ordered.push(slide);
    const inserted = byParent.get(slide.id) || [];
    ordered.push(...inserted.slice().sort((a, b) => a.position - b.position));
  }
  ordered.push(...orphans.slice().sort((a, b) => a.position - b.position));
  return ordered;
});

function isSessionSlide(item: Slide | SessionSlide): item is SessionSlide {
  return (item as SessionSlide).session_id !== undefined;
}

/**
 * Slide ID resolved from the focused timeline event by walking back to the
 * latest `slide.advance` (deck or session). Returns null if no advance was logged.
 */
const focusedSlideId = computed<string | null>(() => {
  if (!events.value.length) return null;
  const focus = focusedEvent.value;
  if (!focus) return null;
  const idx = events.value.indexOf(focus);
  for (let i = idx; i >= 0; i--) {
    const e = events.value[i];
    if (e.event_type === "slide.advance") {
      const p = e.payload as Record<string, unknown>;
      const toId = p.to_id as string | undefined;
      if (toId) return toId;
    }
  }
  return null;
});

/** Manual override > focused event > first slide. */
const activeSlideId = computed<string | null>(() => {
  if (manualSlideId.value) return manualSlideId.value;
  if (focusedSlideId.value) return focusedSlideId.value;
  const order = presentationOrder.value;
  return order.length > 0 ? order[0].id : null;
});

const activePresentationIndex = computed(() => {
  const id = activeSlideId.value;
  if (!id) return -1;
  return presentationOrder.value.findIndex((s) => s.id === id);
});

const activeItem = computed<Slide | SessionSlide | null>(() => {
  const idx = activePresentationIndex.value;
  if (idx < 0) return null;
  return presentationOrder.value[idx] || null;
});

const currentDeckSlide = computed<Slide | null>(() => {
  const item = activeItem.value;
  if (!item || isSessionSlide(item)) return null;
  return item;
});

const currentSessionSlide = computed<SessionSlide | null>(() => {
  const item = activeItem.value;
  if (!item || !isSessionSlide(item)) return null;
  return item;
});

const currentSpecType = computed(() => {
  const slide = currentSessionSlide.value;
  if (!slide) return null;
  const t = (slide.spec as { type?: unknown } | null | undefined)?.type;
  return typeof t === "string" ? t : null;
});

/** Mirror of Presenter.vue's currentKicker (lines 84–93). */
const currentKicker = computed<string | null>(() => {
  const snap = snapshot.value;
  const slide = currentDeckSlide.value;
  if (!snap || !slide) return null;
  const idx = snap.slides.findIndex((s) => s.id === slide.id);
  const page = String(idx + 1).padStart(2, "0");
  const section = snap.sections.find((sec) => sec.id === slide.section_id);
  const label = section?.title?.trim() || "Unsectioned";
  return `§ ${page} — ${label}`;
});

const canGoPrev = computed(() => activePresentationIndex.value > 0);
const canGoNext = computed(
  () => activePresentationIndex.value >= 0 && activePresentationIndex.value < presentationOrder.value.length - 1,
);

function gotoSlide(id: string) {
  manualSlideId.value = id;
  // Detach from timeline focus while user is browsing manually.
  selectedEventIdx.value = null;
}

function prevSlide() {
  if (!canGoPrev.value) return;
  const item = presentationOrder.value[activePresentationIndex.value - 1];
  if (item) gotoSlide(item.id);
}

function nextSlide() {
  if (!canGoNext.value) return;
  const item = presentationOrder.value[activePresentationIndex.value + 1];
  if (item) gotoSlide(item.id);
}

function selectEvent(originalIdx: number) {
  selectedEventIdx.value = originalIdx;
  // Sidebar event click re-detaches from manual-slide browsing.
  manualSlideId.value = null;
}

// Keep selected idx valid when events change.
watch(events, () => {
  if (selectedEventIdx.value !== null && selectedEventIdx.value >= events.value.length) {
    selectedEventIdx.value = null;
  }
});

function onKeydown(e: KeyboardEvent) {
  // Don't hijack arrows when the user is typing in an input or contenteditable.
  const target = e.target as HTMLElement | null;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
  if (e.key === "ArrowLeft") {
    prevSlide();
  } else if (e.key === "ArrowRight") {
    nextSlide();
  }
}

onMounted(() => {
  fetchTranscript();
  void fetchSnapshot();
  document.addEventListener("click", onDocumentClick);
  window.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="transcript-page">
    <!-- Presenter-style app bar -->
    <header class="app-bar">
      <div class="app-bar-left">
        <button class="btn btn-ghost btn-sm btn-icon" @click="backToSessions" title="Back to sessions">
          <Icon name="arrow_left" :size="16" />
        </button>
        <Wordmark :size="14" />
        <span class="app-bar-sep">·</span>
        <span class="app-bar-deck-title">{{ snapshot?.deck_title || "Session" }}</span>
        <span class="replay-badge">REPLAY</span>
      </div>
      <div class="app-bar-right">
        <span v-if="snapshot?.code" class="app-bar-code">
          <Icon name="copy" :size="12" />
          {{ snapshot.code }}
        </span>
        <div class="export-menu-wrap" ref="exportMenuEl">
          <button
            class="btn btn-sm"
            :class="{ 'is-active': exportMenuOpen }"
            @click.stop="toggleExportMenu"
            :aria-expanded="exportMenuOpen"
            aria-haspopup="menu"
          >
            <Icon name="download" :size="14" />
            Export
            <Icon name="chevron_down" :size="12" />
          </button>
          <div v-if="exportMenuOpen" class="export-menu" role="menu">
            <button class="export-menu-item" role="menuitem" @click="downloadCsv">
              <span class="export-menu-label">CSV</span>
              <span class="export-menu-hint">Spreadsheet-friendly</span>
            </button>
            <button class="export-menu-item" role="menuitem" @click="downloadJson">
              <span class="export-menu-label">JSON</span>
              <span class="export-menu-hint">Full .slaides-session</span>
            </button>
          </div>
        </div>
        <button
          class="btn btn-sm btn-danger-ghost"
          @click="showDeleteConfirm = true"
          :disabled="deletableEventCount === 0"
          title="Delete slide-advance and LLM events"
        >
          <Icon name="clean" :size="14" />
          Clear Slide &amp; LLM
        </button>
      </div>
    </header>

    <div v-if="preMigrationWarning" class="pre-migration-warning">
      <Icon name="info" :size="16" />
      {{ preMigrationWarning }}
    </div>

    <div v-if="loading" class="transcript-loading">
      <p>Loading transcript…</p>
    </div>

    <div v-else-if="error" class="transcript-error">
      <p>{{ error }}</p>
      <button class="btn btn-sm" @click="() => fetchTranscript()">Retry</button>
    </div>

    <div v-else class="transcript-layout">
      <!-- LEFT: full-bleed slide pane -->
      <section class="slide-pane">
        <main
          class="slide-main"
          :class="{ inverted: !!currentSessionSlide?.inverted_theme }"
        >
          <SlideStage
            v-if="currentDeckSlide"
            :slide="currentDeckSlide"
            :kicker="currentKicker"
            role="instructor"
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
          <div v-else class="slide-empty">
            <p>No slide to show.</p>
          </div>
        </main>

        <!-- Presenter-style bottom strip -->
        <footer class="slide-stepper">
          <button class="btn btn-ghost btn-sm" :disabled="!canGoPrev" @click="prevSlide">
            <Icon name="chev_left" :size="16" /> Prev
          </button>

          <div class="stepper-mid">
            <div class="stepper-dots">
              <button
                v-for="(s, i) in presentationOrder"
                :key="s.id"
                type="button"
                @click="gotoSlide(s.id)"
                :title="`Slide ${i + 1}`"
                :aria-label="`Go to slide ${i + 1}`"
                :class="['dot', i === activePresentationIndex && 'active']"
              />
            </div>
            <span class="t-mono stepper-counter">
              {{ activePresentationIndex >= 0 ? activePresentationIndex + 1 : "—" }} / {{ presentationOrder.length }}
            </span>
            <span v-if="focusedEvent" class="stepper-time">· {{ formatTime(focusedEvent.occurred_at) }}</span>
          </div>

          <button class="btn btn-ghost btn-sm" :disabled="!canGoNext" @click="nextSlide">
            Next <Icon name="chev_right" :size="16" />
          </button>
        </footer>
      </section>

      <!-- RIGHT: tabs sidebar -->
      <aside class="sidebar">
        <nav class="sidebar-tabs" role="tablist">
          <button
            role="tab"
            :class="['sidebar-tab', activeTab === 'timeline' && 'active']"
            :aria-selected="activeTab === 'timeline'"
            @click="activeTab = 'timeline'"
          >
            Timeline
            <span class="sidebar-tab-count">{{ events.length }}{{ total > events.length ? ` / ${total}` : "" }}</span>
          </button>
          <button
            role="tab"
            :class="['sidebar-tab', activeTab === 'per-slide' && 'active']"
            :aria-selected="activeTab === 'per-slide'"
            @click="activeTab = 'per-slide'"
          >
            Per-Slide
            <span class="sidebar-tab-count">{{ perSlide.length }}</span>
          </button>
          <button
            role="tab"
            :class="['sidebar-tab', activeTab === 'per-participant' && 'active']"
            :aria-selected="activeTab === 'per-participant'"
            @click="activeTab = 'per-participant'"
          >
            Participants
            <span class="sidebar-tab-count">{{ perParticipant.length }}</span>
          </button>
        </nav>

        <!-- Timeline -->
        <div v-if="activeTab === 'timeline'" class="sidebar-body">
          <div v-if="availableTypes.length > 0" class="sidebar-filters">
            <button
              v-for="type in availableTypes"
              :key="type"
              :class="['filter-chip', activeTypes.has(type) && 'active']"
              @click="activeTypes.has(type) ? activeTypes.delete(type) : activeTypes.add(type)"
            >
              <Icon :name="getEventIcon(type)" :size="11" />
              {{ type }}
            </button>
          </div>

          <div class="event-list">
            <template v-if="events.length === 0">
              <div class="sidebar-empty">No events recorded.</div>
            </template>
            <template v-else-if="visibleEvents.length === 0">
              <div class="sidebar-empty">No events match current filters.</div>
            </template>
            <button
              v-for="event in visibleEvents"
              :key="`${event.occurred_at}-${event.event_type}`"
              :class="['event-row', focusedEvent === event && 'selected']"
              @click="selectEvent(events.indexOf(event))"
            >
              <span class="event-row-time">{{ formatTime(event.occurred_at) }}</span>
              <Icon class="event-row-icon" :name="getEventIcon(event.event_type)" :size="12" />
              <span class="event-row-content">
                <span class="event-row-type">{{ event.event_type }}</span>
                <span v-if="eventSummary(event)" class="event-row-summary">{{ eventSummary(event) }}</span>
              </span>
            </button>
          </div>

          <button v-if="hasMore" class="sidebar-load-more" @click="loadMore">
            Load {{ Math.min(PAGE_SIZE, total - events.length) }} more
          </button>
        </div>

        <!-- Per-Slide -->
        <div v-else-if="activeTab === 'per-slide'" class="sidebar-body">
          <div v-if="perSlide.length === 0" class="sidebar-empty">No slide interactions recorded.</div>
          <div v-else class="summary-list">
            <div v-for="slide in perSlide" :key="slide.slide_id" class="summary-row">
              <div class="summary-row-head">
                <span class="summary-row-kind">{{ slide.kind }}</span>
                <code class="summary-row-id">{{ slide.slide_id.slice(0, 8) }}</code>
                <span class="summary-row-count">{{ slide.interaction_count }}</span>
              </div>
              <div v-if="Object.keys(slide.by_kind).length > 0" class="summary-row-breakdown">
                <span v-for="(count, kind) in slide.by_kind" :key="kind" class="breakdown-pill">
                  {{ kind }} · {{ count }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Per-Participant -->
        <div v-else class="sidebar-body">
          <div v-if="perParticipant.length === 0" class="sidebar-empty">No participants recorded.</div>
          <div v-else class="summary-list">
            <div v-for="p in perParticipant" :key="p.participant_ref" class="summary-row">
              <div class="summary-row-head">
                <span class="summary-row-name">
                  {{ p.display_name }}
                  <span v-if="p.anon" class="anon-badge">anon</span>
                </span>
                <span class="summary-row-count">{{ p.total_interactions }}</span>
              </div>
              <div v-if="Object.keys(p.by_kind).length > 0" class="summary-row-breakdown">
                <span v-for="(count, kind) in p.by_kind" :key="kind" class="breakdown-pill">
                  {{ kind }} · {{ count }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- Delete Confirm Modal -->
    <div v-if="showDeleteConfirm" class="delete-confirm-modal" @click.self="showDeleteConfirm = false">
      <div class="delete-confirm-content">
        <h2 class="delete-confirm-title">Clear Slide &amp; LLM History?</h2>
        <p class="delete-confirm-message">
          This will permanently delete slide advance events and LLM Interpret calls from the transcript.
          <br><br>
          <strong>Preserved:</strong> Poll votes, open answers, questions, and audience interactions remain.
          <br>
          <strong>This action cannot be undone.</strong>
        </p>
        <div class="delete-confirm-actions">
          <button class="btn btn-ghost" @click="showDeleteConfirm = false" :disabled="deleting">Cancel</button>
          <button class="btn btn-danger" @click="deleteTranscript" :disabled="deleting || deletableEventCount === 0">
            <Icon v-if="deleting" name="loader" :size="14" />
            {{ deleting ? "Deleting…" : `Delete ${deletableEventCount} Events` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.transcript-page {
  height: 100vh;
  background: var(--paper);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Presenter-style app bar --------------------------------- */
.app-bar {
  height: 52px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  flex-shrink: 0;
  background: var(--paper);
}
.app-bar-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.app-bar-sep {
  color: var(--ink-soft);
  font-size: 12px;
}
.app-bar-deck-title {
  font-family: var(--serif);
  font-size: 15px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.replay-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 9px;
  border-radius: var(--r-xs, 4px);
  background: var(--paper-2);
  color: var(--ink-soft);
  border: 1px solid var(--rule);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.app-bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.app-bar-code {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid var(--rule);
  border-radius: 999px;
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 11.5px;
  color: var(--ink-soft);
}
.btn.btn-icon {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
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

/* Export menu --------------------------------------------- */
.export-menu-wrap { position: relative; }
.export-menu-wrap .btn.is-active {
  background: var(--paper-2);
  border-color: var(--ink);
}
.export-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 200px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  padding: 4px;
  z-index: 50;
  display: flex;
  flex-direction: column;
}
.export-menu-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  background: transparent;
  border: none;
  text-align: left;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  cursor: pointer;
  font-family: var(--sans);
  color: var(--ink);
}
.export-menu-item:hover { background: var(--paper-2); }
.export-menu-label { font-size: 13px; font-weight: 600; }
.export-menu-hint { font-size: 11px; color: var(--ink-soft); }

/* Banners + states ---------------------------------------- */
.pre-migration-warning {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 18px 0;
  padding: 10px 14px;
  background: var(--paper-2);
  border: 1px solid var(--rule);
  border-left: 3px solid var(--accent);
  border-radius: var(--r-sm);
  color: var(--ink);
  font-size: 12.5px;
}
.transcript-loading,
.transcript-error {
  text-align: center;
  padding: 80px 24px;
  color: var(--ink-soft);
}

/* Two-column layout --------------------------------------- */
.transcript-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 380px;
  min-height: 0;
}

/* Slide pane (left) — full-bleed paper, matches Presenter -- */
.slide-pane {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--rule);
  min-width: 0;
  min-height: 0;
}
.slide-main {
  flex: 1;
  overflow-y: auto;
  background: var(--paper);
  color: var(--ink);
  min-height: 0;
}
.slide-main.inverted {
  background: var(--ink);
  color: var(--paper);
}
.slide-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--ink-soft);
  font-size: 13px;
}

/* Bottom stepper (left pane) ------------------------------ */
.slide-stepper {
  height: 48px;
  border-top: 1px solid var(--rule);
  background: var(--paper);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  flex-shrink: 0;
}
.stepper-mid {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stepper-dots {
  display: flex;
  gap: 6px;
  align-items: center;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: none;
  padding: 0;
  cursor: pointer;
  background: var(--rule-strong, var(--rule));
  transition: background 0.15s ease;
}
.dot.active { background: var(--ink); }
.stepper-counter {
  color: var(--ink-soft);
  font-size: 12px;
  font-family: var(--mono, ui-monospace, monospace);
}
.stepper-time {
  color: var(--ink-soft);
  font-size: 11.5px;
  font-family: var(--mono, ui-monospace, monospace);
}

/* Sidebar (right) ----------------------------------------- */
.sidebar {
  display: flex;
  flex-direction: column;
  background: var(--paper);
  min-width: 0;
  min-height: 0;
}
.sidebar-tabs {
  display: flex;
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}
.sidebar-tab {
  flex: 1;
  background: transparent;
  border: none;
  padding: 12px 8px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-bottom: 2px solid transparent;
}
.sidebar-tab:hover { color: var(--ink); }
.sidebar-tab.active {
  color: var(--ink);
  border-bottom-color: var(--ink);
}
.sidebar-tab-count {
  font-size: 11px;
  font-weight: 500;
  color: var(--ink-soft);
}
.sidebar-tab.active .sidebar-tab-count { color: var(--ink); }

.sidebar-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.sidebar-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 12.5px;
  color: var(--ink-soft);
}

/* Filter chips */
.sidebar-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: 999px;
  padding: 3px 8px;
  font-family: var(--sans);
  font-size: 10.5px;
  color: var(--ink-soft);
  cursor: pointer;
}
.filter-chip:hover { border-color: var(--ink-soft); }
.filter-chip.active {
  background: var(--ink);
  color: var(--paper);
  border-color: var(--ink);
}

/* Event list */
.event-list {
  flex: 1;
  overflow: auto;
}
.event-row {
  display: grid;
  grid-template-columns: 60px 16px 1fr;
  align-items: start;
  gap: 8px;
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--rule);
  padding: 8px 12px;
  text-align: left;
  cursor: pointer;
  font-family: var(--sans);
}
.event-row:hover { background: var(--paper-2); }
.event-row.selected {
  background: var(--paper-2);
  box-shadow: inset 2px 0 0 var(--ink);
}
.event-row-time {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 10.5px;
  color: var(--ink-soft);
  padding-top: 2px;
}
.event-row-icon {
  color: var(--ink-soft);
  margin-top: 3px;
}
.event-row-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.event-row-type {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event-row-summary {
  font-size: 11.5px;
  color: var(--ink-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-load-more {
  background: var(--paper);
  border: none;
  border-top: 1px solid var(--rule);
  padding: 10px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
  cursor: pointer;
  flex-shrink: 0;
}
.sidebar-load-more:hover { background: var(--paper-2); }

/* Summary lists (per-slide / per-participant) */
.summary-list {
  flex: 1;
  overflow: auto;
}
.summary-row {
  border-bottom: 1px solid var(--rule);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.summary-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.summary-row-name {
  flex: 1;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-row-kind {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-soft);
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  padding: 1px 5px;
}
.summary-row-id {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 11px;
  color: var(--ink-soft);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.summary-row-count {
  margin-left: auto;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.summary-row-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.breakdown-pill {
  font-size: 10.5px;
  color: var(--ink-soft);
  background: var(--paper-2);
  border-radius: 999px;
  padding: 2px 8px;
}
.anon-badge {
  display: inline-block;
  margin-left: 6px;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-soft);
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  padding: 0 4px;
}

/* Delete modal -------------------------------------------- */
.delete-confirm-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.delete-confirm-content {
  background: var(--paper);
  padding: 24px;
  border-radius: var(--r-md);
  max-width: 420px;
  width: 90%;
}
.delete-confirm-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--ink);
}
.delete-confirm-message {
  font-size: 13.5px;
  color: var(--ink-soft);
  margin: 0 0 20px;
  line-height: 1.55;
}
.delete-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Responsive ---------------------------------------------- */
@media (max-width: 900px) {
  .transcript-layout {
    grid-template-columns: 1fr;
  }
  .slide-pane { border-right: none; border-bottom: 1px solid var(--rule); }
  .sidebar { max-height: 60vh; }
}
</style>
