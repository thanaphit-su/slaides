<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { sessionsApi } from "@/api/sessions";
import { useSessionStore } from "@/stores/session";
import Icon from "@/components/Icon.vue";
import type { OpenAnswer, SessionSlide } from "@/api/types";

const props = defineProps<{ slide: SessionSlide }>();

const session = useSessionStore();
const answers = ref<OpenAnswer[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const filter = ref("");
const busy = ref<number | null>(null);

const promotedIds = computed(() => {
  const arr = (props.slide.results as any)?.promoted as { id: string }[] | undefined;
  return new Set((arr || []).map((p) => p.id));
});

const grouped = computed(() => {
  const lower = filter.value.trim().toLowerCase();
  const filtered = lower
    ? answers.value.filter((a) => a.text.toLowerCase().includes(lower))
    : answers.value;
  // Collapse exact duplicates so "yes · ×6" shows once.
  const groups = new Map<string, { sample: OpenAnswer; count: number; ids: number[] }>();
  for (const a of filtered) {
    const key = a.text.trim().toLowerCase();
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
      existing.ids.push(a.id);
    } else {
      groups.set(key, { sample: a, count: 1, ids: [a.id] });
    }
  }
  return Array.from(groups.values()).sort(
    (a, b) => Date.parse(b.sample.occurred_at) - Date.parse(a.sample.occurred_at),
  );
});

const promotedCount = computed(() => promotedIds.value.size);
const hasAnswers = computed(() => answers.value.length > 0);
const displayError = computed(() => {
  if (!error.value) return null;
  if (/internal server error/i.test(error.value)) {
    return "Answers could not be loaded. Check the session connection and try again.";
  }
  return error.value;
});

async function refresh() {
  if (loading.value) return;
  loading.value = true;
  error.value = null;
  try {
    answers.value = await sessionsApi.listAnswers(props.slide.session_id, props.slide.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load answers.";
  } finally {
    loading.value = false;
  }
}

function drainIncoming() {
  // Pull WS-buffered new-answer events and merge.
  const fresh = session.takeIncomingAnswers(props.slide.id);
  if (!fresh.length) return;
  const seen = new Set(answers.value.map((a) => a.id));
  const merged = [...fresh.filter((a) => !seen.has(a.id)), ...answers.value];
  answers.value = merged;
}

let drainTimer = 0;
onMounted(() => {
  refresh();
  drainTimer = window.setInterval(drainIncoming, 500);
});
onBeforeUnmount(() => {
  if (drainTimer) window.clearInterval(drainTimer);
});

watch(
  () => props.slide.id,
  () => {
    answers.value = [];
    refresh();
  },
);

async function promote(logId: number) {
  if (busy.value) return;
  busy.value = logId;
  try {
    await sessionsApi.promoteAnswer(props.slide.session_id, props.slide.id, logId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not promote.";
  } finally {
    busy.value = null;
  }
}

async function unpromote(logId: number) {
  if (busy.value) return;
  busy.value = logId;
  try {
    await sessionsApi.unpromoteAnswer(props.slide.session_id, props.slide.id, logId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not unpromote.";
  } finally {
    busy.value = null;
  }
}

async function hide(logId: number) {
  if (busy.value) return;
  busy.value = logId;
  try {
    await sessionsApi.hideAnswer(props.slide.session_id, props.slide.id, logId);
    answers.value = answers.value.filter((a) => a.id !== logId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not hide.";
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <aside class="rail">
    <header class="rail-header">
      <div>
        <div class="t-kicker">Answers</div>
        <div class="counter">
          {{ answers.length }} answer{{ answers.length === 1 ? "" : "s" }} ·
          <strong>{{ promotedCount }} shown</strong>
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" title="Refresh" @click="refresh">
        <Icon name="arrow_right" :size="14" />
      </button>
    </header>

    <div v-if="hasAnswers || filter" class="filter-row">
      <input v-model="filter" class="input filter-input" placeholder="Search answers…" />
    </div>

    <div v-if="displayError" class="error-state">
      <div>
        <strong>Could not load answers</strong>
        <p>{{ displayError }}</p>
      </div>
      <button class="btn btn-sm" type="button" :disabled="loading" @click="refresh">
        Retry
      </button>
    </div>

    <ul v-if="grouped.length" class="answer-list">
      <li
        v-for="group in grouped"
        :key="group.sample.id"
        class="answer-row"
        :class="{ promoted: promotedIds.has(String(group.sample.id)) }"
      >
        <div class="answer-body">
          <p class="answer-text">{{ group.sample.text }}</p>
          <div class="answer-meta">
            <span>{{ group.sample.anon ? "Anonymous" : group.sample.display_name || group.sample.participant_ref.slice(0, 6) }}</span>
            <span v-if="group.count > 1" class="dup-tag">×{{ group.count }}</span>
          </div>
        </div>
        <div class="answer-actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :title="promotedIds.has(String(group.sample.id)) ? 'Unpromote' : 'Show on screen'"
            :disabled="busy === group.sample.id"
            @click="promotedIds.has(String(group.sample.id)) ? unpromote(group.sample.id) : promote(group.sample.id)"
          >
            <Icon :name="promotedIds.has(String(group.sample.id)) ? 'check' : 'eye'" :size="13" />
          </button>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            title="Hide"
            :disabled="busy === group.sample.id"
            @click="hide(group.sample.id)"
          >
            <Icon name="trash" :size="13" />
          </button>
        </div>
      </li>
    </ul>
    <p v-else-if="loading" class="empty-state">Loading answers…</p>
    <p v-else-if="filter" class="empty-state">
      No answers match “{{ filter }}”.
    </p>
    <p v-else class="empty-state">
      No answers yet. The first response will appear here.
    </p>
  </aside>
</template>

<style scoped>
.rail {
  width: clamp(320px, 22vw, 380px);
  min-width: 320px;
  border-left: 1px solid var(--rule);
  background: var(--paper);
  color: var(--ink);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}
.rail-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.counter {
  font-size: 12px;
  color: var(--ink-soft);
}
.filter-row {
  padding: 10px 14px;
}
.filter-input {
  width: 100%;
  font-size: 13px;
}
.answer-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.answer-row {
  padding: 10px 14px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.answer-row.promoted {
  background: var(--accent-soft);
}
.answer-body {
  flex: 1;
  min-width: 0;
}
.answer-text {
  margin: 0 0 6px;
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.4;
  color: var(--ink);
  word-break: break-word;
}
.answer-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ink-soft);
}
.dup-tag {
  font-family: var(--mono);
  background: var(--paper-2);
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
}
.answer-actions {
  display: flex;
  gap: 2px;
}
.empty-state {
  padding: 22px 18px;
  margin: 0;
  font-style: italic;
  color: var(--ink-soft);
  font-size: 12px;
}
.error-state {
  margin: 10px 14px;
  padding: 12px;
  border: 1px solid rgba(190, 29, 74, 0.22);
  border-radius: var(--r-md);
  background: rgba(190, 29, 74, 0.06);
  color: var(--ink);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}
.error-state strong {
  display: block;
  margin-bottom: 3px;
}
.error-state p {
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.4;
}

@media (max-width: 900px) {
  .rail {
    position: fixed;
    inset: auto 0 0 0;
    width: 100%;
    min-width: 0;
    max-height: 42vh;
    border-left: 0;
    border-top: 1px solid var(--rule);
    z-index: 20;
  }
}
</style>
