<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { analyticsApi, type TranscriptEvent, type SlideSummary, type ParticipantSummary } from "@/api/analytics";
import Icon from "@/components/Icon.vue";

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

const activeTab = ref<"timeline" | "per-slide" | "per-participant">("timeline");
const availableTypes = ref<string[]>([]);
const activeTypes = ref<Set<string>>(new Set());

const PAGE_SIZE = 500;
const offset = ref(0);
const hasMore = ref(false);

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
      
      // Extract unique event types for filter (from all events)
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

function loadMore() {
  if (!hasMore.value) return;
  offset.value += PAGE_SIZE;
  fetchTranscript(true);
}

function downloadCsv() {
  analyticsApi.downloadTranscriptCsv(sessionId);
}

function downloadJson() {
  analyticsApi.downloadTranscriptJson(sessionId);
}

const showDeleteConfirm = ref(false);
const deleting = ref(false);

async function deleteTranscript() {
  deleting.value = true;
  try {
    await analyticsApi.deleteTranscript(sessionId);
    // Reload transcript to show empty state
    offset.value = 0;
    await fetchTranscript();
    showDeleteConfirm.value = false;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Failed to delete transcript";
  } finally {
    deleting.value = false;
  }
}

function getEventIcon(eventType: string): string {
  if (eventType === "slide.advance") return "arrow_right";
  if (eventType.startsWith("interaction.")) return "poll";
  if (eventType === "question.raised") return "help";
  if (eventType.startsWith("interaction.opened")) return "add";
  if (eventType.startsWith("interaction.closed")) return "close";
  if (eventType === "llm.interpret") return "auto_awesome";
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

function getParticipantLabel(payload: Record<string, unknown>): string {
  const ref = payload.participant_ref as string | undefined;
  if (!ref) return "";
  return ref.slice(0, 8);
}

const visibleEvents = computed(() => {
  return events.value.filter((e) => activeTypes.value.has(e.event_type));
});

onMounted(() => {
  fetchTranscript();
});
</script>

<template>
  <div class="transcript-page">
    <header class="transcript-header">
      <div class="header-left">
        <button class="btn btn-ghost" @click="router.back()" title="Back">
          <Icon name="arrow_left" :size="18" />
        </button>
        <h1>Session Transcript</h1>
      </div>
      <div class="header-actions">
        <button class="btn btn-sm" @click="downloadCsv">
          <Icon name="download" :size="14" />
          CSV
        </button>
        <button class="btn btn-sm" @click="downloadJson">
          <Icon name="download" :size="14" />
          JSON
        </button>
        <button class="btn btn-sm btn-danger" @click="showDeleteConfirm = true" :disabled="events.length === 0">
          <Icon name="delete" :size="14" />
          Delete History
        </button>
      </div>
    </header>

    <div v-if="preMigrationWarning" class="pre-migration-warning">
      <Icon name="info" :size="16" />
      {{ preMigrationWarning }}
    </div>

    <div v-if="loading" class="transcript-loading">
      <p>Loading transcript...</p>
    </div>

    <div v-else-if="error" class="transcript-error">
      <p>{{ error }}</p>
      <button class="btn btn-sm" @click="fetchTranscript">Retry</button>
    </div>

    <template v-else>
      <div class="transcript-tabs">
        <button
          :class="['tab', activeTab === 'timeline' ? 'active' : '']"
          @click="activeTab = 'timeline'"
        >
          Timeline ({{ events.length }} / {{ total }})
        </button>
        <button
          :class="['tab', activeTab === 'per-slide' ? 'active' : '']"
          @click="activeTab = 'per-slide'"
        >
          Per-Slide ({{ perSlide.length }})
        </button>
        <button
          :class="['tab', activeTab === 'per-participant' ? 'active' : '']"
          @click="activeTab = 'per-participant'"
        >
          Per-Participant ({{ perParticipant.length }})
        </button>
      </div>

      <div v-if="activeTab === 'timeline'" class="timeline-view">
        <div class="timeline-filters">
          <label class="filter-label">
            <Icon name="filter_list" :size="14" />
            Filter by event type:
          </label>
          <div class="filter-chips">
            <button
              v-for="type in availableTypes"
              :key="type"
              :class="['chip', activeTypes.has(type) ? 'active' : '']"
              @click="activeTypes.has(type) ? activeTypes.delete(type) : activeTypes.add(type)"
            >
              {{ type }}
            </button>
          </div>
        </div>

        <div class="timeline-list">
          <template v-if="visibleEvents.length === 0 && events.length > 0">
            <div class="timeline-empty">
              <p>No events match current filters.</p>
            </div>
          </template>
          <template v-else-if="events.length === 0">
            <div class="timeline-empty">
              <p>No events recorded for this session.</p>
            </div>
          </template>
          <div
            v-for="(event, i) in visibleEvents"
            :key="i"
            class="timeline-event"
          >
            <div class="event-time">{{ formatTime(event.occurred_at) }}</div>
            <div class="event-icon">
              <Icon :name="getEventIcon(event.event_type)" :size="16" />
            </div>
            <div class="event-content">
              <div class="event-type">{{ event.event_type }}</div>
              <div class="event-payload">
                <code>{{ JSON.stringify(event.payload, null, 2) }}</code>
              </div>
              <div v-if="event.payload.participant_ref" class="event-participant">
                Participant: {{ getParticipantLabel(event.payload) }}
              </div>
            </div>
          </div>
        </div>
        
        <div v-if="hasMore" class="timeline-load-more">
          <button class="btn" @click="loadMore">
            Load more ({{ total - events.length }} remaining)
          </button>
        </div>
      </div>

      <div v-if="activeTab === 'per-slide'" class="per-slide-view">
        <div v-if="perSlide.length === 0" class="empty-state">
          <p>No slide interactions recorded.</p>
        </div>
        <div v-else class="slide-list">
          <div v-for="slide in perSlide" :key="slide.slide_id" class="slide-card">
            <div class="slide-header">
              <span class="slide-kind">{{ slide.kind }}</span>
              <span class="slide-id">{{ slide.slide_id.slice(0, 8) }}...</span>
            </div>
            <div class="slide-stats">
              <div class="stat">
                <span class="stat-value">{{ slide.interaction_count }}</span>
                <span class="stat-label">interactions</span>
              </div>
            </div>
            <div v-if="Object.keys(slide.by_kind).length > 0" class="slide-breakdown">
              <div v-for="(count, kind) in slide.by_kind" :key="kind" class="breakdown-item">
                <span class="breakdown-kind">{{ kind }}</span>
                <span class="breakdown-count">{{ count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'per-participant'" class="per-participant-view">
        <div v-if="perParticipant.length === 0" class="empty-state">
          <p>No participants recorded.</p>
        </div>
        <div v-else class="participant-list">
          <div v-for="p in perParticipant" :key="p.participant_ref" class="participant-card">
            <div class="participant-header">
              <span class="participant-name">
                {{ p.display_name }}
                <span v-if="p.anon" class="anon-badge">anonymous</span>
              </span>
              <span class="participant-joined">Joined: {{ new Date(p.joined_at).toLocaleString() }}</span>
            </div>
            <div class="participant-stats">
              <div class="stat">
                <span class="stat-value">{{ p.total_interactions }}</span>
                <span class="stat-label">total interactions</span>
              </div>
            </div>
            <div v-if="Object.keys(p.by_kind).length > 0" class="participant-breakdown">
              <div v-for="(count, kind) in p.by_kind" :key="kind" class="breakdown-item">
                <span class="breakdown-kind">{{ kind }}</span>
                <span class="breakdown-count">{{ count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
    
    <!-- Delete Confirm Modal -->
    <div v-if="showDeleteConfirm" class="delete-confirm-modal" @click.self="showDeleteConfirm = false">
      <div class="delete-confirm-content">
        <h2 class="delete-confirm-title">Delete Session History?</h2>
        <p class="delete-confirm-message">
          This will permanently delete all transcript events (slide advances, LLM interpretations) for this session.
          The session itself will be preserved, but the transcript will be empty.
          <br><br>
          <strong>This action cannot be undone.</strong>
        </p>
        <div class="delete-confirm-actions">
          <button class="btn btn-ghost" @click="showDeleteConfirm = false" :disabled="deleting">
            Cancel
          </button>
          <button class="btn btn-danger" @click="deleteTranscript" :disabled="deleting">
            <Icon v-if="deleting" name="loader" :size="14" />
            {{ deleting ? 'Deleting...' : 'Delete History' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.transcript-page {
  min-height: 100vh;
  background: var(--paper);
  padding: 24px 32px;
}

.transcript-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--rule);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-left h1 {
  margin: 0;
  font-family: var(--serif);
  font-size: 24px;
  color: var(--ink);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.pre-migration-warning {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--accent-soft, #fef3c7);
  border: 1px solid var(--accent, #f59e0b);
  border-radius: var(--r-sm);
  color: var(--ink);
  font-size: 13px;
  margin-bottom: 20px;
}

.transcript-loading,
.transcript-error {
  text-align: center;
  padding: 48px;
  color: var(--ink-soft);
}

.transcript-error {
  color: var(--err);
}

.transcript-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 8px;
}

.tab {
  background: transparent;
  border: none;
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 14px;
  padding: 8px 16px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.tab:hover {
  background: var(--paper-2);
}

.tab.active {
  background: var(--ink);
  color: var(--paper);
}

.timeline-filters {
  margin-bottom: 20px;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-soft);
  margin-bottom: 8px;
}

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  background: var(--paper-2);
  border: 1px solid var(--rule);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all 0.2s;
}

.chip:hover {
  border-color: var(--accent);
}

.chip.active {
  background: var(--accent);
  color: var(--paper);
  border-color: var(--accent);
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-event {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
}

.event-time {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  min-width: 80px;
}

.event-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 50%;
  color: var(--ink);
  flex-shrink: 0;
}

.event-content {
  flex: 1;
  min-width: 0;
}

.event-type {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 6px;
}

.event-payload {
  margin-bottom: 6px;
}

.event-payload code {
  display: block;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  padding: 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.event-participant {
  font-size: 11px;
  color: var(--ink-soft);
}

.timeline-empty {
  text-align: center;
  padding: 48px;
  color: var(--ink-soft);
}

.empty-state {
  text-align: center;
  padding: 48px;
  color: var(--ink-soft);
}

.slide-list,
.participant-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.slide-card,
.participant-card {
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 16px;
  background: var(--paper-2);
}

.slide-header,
.participant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.slide-kind,
.slide-id {
  font-size: 11px;
  font-family: var(--mono);
  color: var(--ink-soft);
}

.slide-breakdown,
.participant-breakdown {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  padding: 4px 8px;
}

.breakdown-kind {
  color: var(--ink-soft);
}

.breakdown-count {
  font-weight: 600;
  color: var(--ink);
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 12px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--ink);
  font-family: var(--serif);
}

.stat-label {
  font-size: 11px;
  color: var(--ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.participant-name {
  font-weight: 600;
  color: var(--ink);
  font-size: 14px;
}

.anon-badge {
  margin-left: 6px;
  font-size: 10px;
  background: var(--ink-soft);
  color: var(--paper);
  padding: 2px 6px;
  border-radius: var(--r-sm);
  text-transform: uppercase;
}

.participant-joined {
  font-size: 11px;
  color: var(--ink-soft);
}

.delete-confirm-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.delete-confirm-content {
  background: var(--paper);
  padding: 24px;
  border-radius: var(--r-md);
  max-width: 400px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.delete-confirm-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--ink);
}

.delete-confirm-message {
  font-size: 14px;
  color: var(--ink-soft);
  margin-bottom: 20px;
  line-height: 1.5;
}

.delete-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
