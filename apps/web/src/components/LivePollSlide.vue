<script setup lang="ts">
import { computed, ref } from "vue";
import { sessionsApi } from "@/api/sessions";
import { useSessionStore } from "@/stores/session";
import Icon from "@/components/Icon.vue";
import type { PollResults, PollSpec, SessionSlide } from "@/api/types";

const props = defineProps<{
  slide: SessionSlide;
  role: "presenter" | "audience";
  inverted: boolean;
}>();

const session = useSessionStore();

const spec = computed<PollSpec>(
  () =>
    (props.slide.spec as unknown as PollSpec) || {
      type: "poll",
      question: "",
      choices: [],
      config: { allow_other: false, show_results_live: true, anonymous: true },
      state: { voting_closed: false, choices_locked: false },
    },
);

const results = computed<PollResults>(() => {
  const r = (props.slide.results as unknown as PollResults) || ({} as PollResults);
  return {
    tally: r.tally || {},
    voters: r.voters || 0,
    other_responses: r.other_responses || [],
  };
});

const votingClosed = computed(() => !!spec.value.state?.voting_closed);
const showResults = computed(
  () => spec.value.config?.show_results_live ?? true,
);
const total = computed(() =>
  Object.values(results.value.tally || {}).reduce((sum, n) => sum + (n || 0), 0),
);

const pickedChoice = ref<string | null>(null);
const otherText = ref("");
const otherSent = ref(false);

// Presenter-side ephemeral UI
const editingQuestion = ref(false);
const draftQuestion = ref(spec.value.question || "");
const resetOpen = ref(false);
const busy = ref<string | null>(null);
const savedWidget = ref(false);
const lastError = ref<string | null>(null);

function widthPct(count: number): string {
  if (!total.value) return "0%";
  return `${Math.round((count / total.value) * 100)}%`;
}

function pctLabel(count: number): string {
  if (!total.value) return "0%";
  return `${Math.round((count / total.value) * 100)}%`;
}

async function vote(choiceId: string) {
  if (props.role !== "audience" || votingClosed.value) return;
  pickedChoice.value = choiceId;
  session.submitPollVote(props.slide.id, choiceId);
}

function submitOther() {
  const t = otherText.value.trim();
  if (!t || props.role !== "audience" || votingClosed.value) return;
  session.submitPollOther(props.slide.id, t);
  otherSent.value = true;
}

async function presenterAction(name: string, fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = name;
  lastError.value = null;
  try {
    await fn();
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : "Action failed.";
  } finally {
    busy.value = null;
  }
}

async function toggleVoting() {
  const close = !votingClosed.value;
  await presenterAction(close ? "close" : "open", async () => {
    if (close) await sessionsApi.closeVoting(props.slide.session_id, props.slide.id);
    else await sessionsApi.reopenVoting(props.slide.session_id, props.slide.id);
  });
}

async function reset() {
  await presenterAction("reset", async () => {
    await sessionsApi.resetPoll(props.slide.session_id, props.slide.id);
    resetOpen.value = false;
    pickedChoice.value = null;
  });
}

async function saveQuestion() {
  const q = draftQuestion.value.trim();
  if (!q) return;
  await presenterAction("question", async () => {
    await sessionsApi.patchInteraction(props.slide.session_id, props.slide.id, {
      question: q,
    });
    editingQuestion.value = false;
  });
}

async function saveToLibrary() {
  await presenterAction("save", async () => {
    await sessionsApi.saveInteractionAsWidget(props.slide.id);
    savedWidget.value = true;
    window.setTimeout(() => (savedWidget.value = false), 2000);
  });
}
</script>

<template>
  <div class="poll-slide" :class="{ inverted: inverted }">
    <div class="poll-inner">
      <div class="kicker">POLL</div>
      <div v-if="role === 'presenter' && editingQuestion" class="edit-row">
        <input v-model="draftQuestion" class="input edit-input" maxlength="500" />
        <button class="btn btn-sm" type="button" @click="editingQuestion = false">Cancel</button>
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="busy === 'question'"
          @click="saveQuestion"
        >
          Save
        </button>
      </div>
      <h2 v-else class="question">
        {{ spec.question || "Untitled poll" }}
        <button
          v-if="role === 'presenter'"
          class="btn btn-ghost btn-sm edit-pencil"
          type="button"
          @click="() => { draftQuestion = spec.question; editingQuestion = true; }"
          title="Edit question"
        >
          <Icon name="edit" :size="13" />
        </button>
      </h2>

      <div v-if="role === 'presenter' && spec.state?.choices_locked" class="lock-chip">
        <Icon name="x" :size="11" />
        Choices locked · {{ results.voters }} vote{{ results.voters === 1 ? "" : "s" }} in
      </div>

      <ul class="choices">
        <li v-for="choice in spec.choices" :key="choice.id">
          <button
            v-if="role === 'audience'"
            type="button"
            class="choice-btn"
            :class="{ picked: pickedChoice === choice.id }"
            :disabled="votingClosed"
            @click="vote(choice.id)"
          >
            <span class="choice-label">{{ choice.label }}</span>
            <template v-if="showResults || pickedChoice">
              <span class="bar">
                <span class="fill" :style="{ width: widthPct(results.tally[choice.id] || 0) }" />
              </span>
              <span class="count">
                {{ results.tally[choice.id] || 0 }}
                <span class="pct">· {{ pctLabel(results.tally[choice.id] || 0) }}</span>
              </span>
            </template>
          </button>
          <div v-else class="choice-readout" :class="{ empty: !total }">
            <span class="choice-label">{{ choice.label }}</span>
            <span class="bar"><span class="fill" :style="{ width: widthPct(results.tally[choice.id] || 0) }" /></span>
            <span class="count">
              {{ results.tally[choice.id] || 0 }}
              <span class="pct">· {{ pctLabel(results.tally[choice.id] || 0) }}</span>
            </span>
          </div>
        </li>
      </ul>

      <p v-if="role === 'presenter' && !total" class="no-votes">
        No votes yet. Results will fill in as the audience responds.
      </p>

      <div v-if="spec.config?.allow_other && role === 'audience' && !otherSent" class="other-row">
        <input
          v-model="otherText"
          class="input"
          placeholder="Other…"
          maxlength="200"
          :disabled="votingClosed"
          @keydown.enter.prevent="submitOther"
        />
        <button class="btn btn-sm" type="button" :disabled="!otherText.trim() || votingClosed" @click="submitOther">
          Send
        </button>
      </div>
      <p v-else-if="spec.config?.allow_other && role === 'audience' && otherSent" class="other-sent">
        “Other” sent. Thanks.
      </p>

      <ul v-if="role === 'presenter' && results.other_responses?.length" class="other-list">
        <li class="other-list-header">Other ({{ results.other_responses.length }})</li>
        <li v-for="entry in results.other_responses" :key="entry.id">{{ entry.text }}</li>
      </ul>

      <footer class="footer-row">
        <span class="meta">{{ results.voters }} voter{{ results.voters === 1 ? "" : "s" }} · {{ total }} vote{{ total === 1 ? "" : "s" }}</span>
        <span v-if="votingClosed" class="closed-pill">Voting closed</span>
      </footer>

      <div v-if="role === 'presenter'" class="presenter-controls" aria-label="Presenter controls">
        <span class="control-label">Presenter controls</span>
        <button class="btn btn-sm" type="button" :disabled="busy === 'close' || busy === 'open'" @click="toggleVoting">
          <Icon name="x" :size="13" v-if="!votingClosed" />
          {{ votingClosed ? "Reopen voting" : "Pause voting" }}
        </button>
        <button class="btn btn-sm" type="button" :disabled="!!busy" @click="resetOpen = true">
          Reset votes
        </button>
        <button class="btn btn-sm" type="button" :disabled="!!busy" @click="saveToLibrary">
          <Icon name="copy" :size="13" />
          {{ savedWidget ? "Saved" : "Save to library" }}
        </button>
        <p v-if="lastError" class="error-text">{{ lastError }}</p>
      </div>

      <div v-if="resetOpen" class="modal-backdrop" @click.self="resetOpen = false">
        <div class="modal scale-in">
          <div class="t-h3" style="margin-bottom: 8px">Reset votes?</div>
          <p class="t-meta" style="margin-bottom: 18px">
            This deletes every vote on this poll and unlocks the choice list. The tally restarts at zero on every screen.
          </p>
          <div style="display: flex; gap: 8px; justify-content: flex-end">
            <button class="btn btn-sm" type="button" @click="resetOpen = false">Cancel</button>
            <button class="btn btn-primary btn-sm" type="button" :disabled="busy === 'reset'" @click="reset">
              {{ busy === "reset" ? "Resetting…" : "Reset" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.poll-slide {
  width: 100%;
  min-height: 100%;
  padding: clamp(48px, 8vh, 96px) 24px;
}
.poll-inner {
  width: min(720px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.kicker {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: var(--accent);
  text-transform: uppercase;
}
.poll-slide.inverted .kicker {
  color: var(--paper);
  opacity: 0.7;
}
.question {
  font-family: var(--serif);
  font-size: 36px;
  line-height: 1.2;
  letter-spacing: -0.015em;
  margin: 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.edit-pencil {
  margin-top: 4px;
  border-color: rgba(255, 255, 255, 0.18);
  opacity: 0.85;
}
.poll-slide:not(.inverted) .edit-pencil {
  border-color: var(--rule);
  color: var(--ink-soft);
}
.edit-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.edit-input {
  flex: 1;
  font-family: var(--serif);
  font-size: 22px;
}
.lock-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--paper-2);
  color: var(--ink-soft);
  font-size: 11px;
  font-family: var(--sans);
  align-self: flex-start;
}
.poll-slide.inverted .lock-chip {
  background: rgba(255, 255, 255, 0.1);
  color: var(--paper);
}
.choices {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.choice-btn,
.choice-readout {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--rule);
  background: var(--paper);
  color: var(--ink);
  border-radius: var(--r-md);
  font-family: var(--sans);
  font-size: 15px;
  cursor: pointer;
  text-align: left;
}
.poll-slide.inverted .choice-btn,
.poll-slide.inverted .choice-readout {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--paper);
}
.choice-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.choice-btn.picked {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.poll-slide.inverted .choice-btn.picked {
  background: rgba(255, 255, 255, 0.15);
  border-color: var(--paper);
}
.choice-label {
  flex: 0 0 auto;
  font-weight: 500;
}
.bar {
  flex: 1;
  height: 8px;
  background: var(--paper-3);
  border-radius: 4px;
  overflow: hidden;
}
.poll-slide.inverted .bar {
  background: rgba(255, 255, 255, 0.15);
}
.fill {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.4s ease;
  min-width: 0;
}
.poll-slide.inverted .fill {
  background: var(--paper);
}
.count {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-soft);
  min-width: 72px;
  text-align: right;
}
.pct {
  color: var(--ink-mute);
}
.poll-slide.inverted .count {
  color: var(--paper);
  opacity: 0.85;
}
.poll-slide.inverted .pct {
  color: var(--paper);
  opacity: 0.62;
}
.choice-readout.empty .bar {
  opacity: 0.55;
}
.other-row {
  display: flex;
  gap: 8px;
}
.other-row .input {
  flex: 1;
}
.other-sent {
  margin: 0;
  font-size: 12px;
  color: var(--ink-soft);
}
.other-list {
  list-style: none;
  padding: 12px 14px;
  margin: 0;
  background: var(--paper-2);
  border-radius: var(--r-md);
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink-soft);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.other-list-header {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 11px;
  color: var(--ink);
  margin-bottom: 4px;
}
.no-votes {
  margin: -2px 0 0;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-soft);
  font-style: italic;
}
.poll-slide.inverted .no-votes {
  color: var(--paper);
  opacity: 0.7;
}
.footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-soft);
}
.poll-slide.inverted .footer-row {
  color: var(--paper);
  opacity: 0.75;
}
.closed-pill {
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--err);
  color: var(--paper);
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.06em;
}
.presenter-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: var(--shadow-1);
}
.poll-slide.inverted .presenter-controls {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
}
.control-label {
  flex: 1 0 100%;
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
.poll-slide.inverted .control-label {
  color: var(--paper);
  opacity: 0.6;
}
.error-text {
  margin: 0;
  color: var(--err);
  font-size: 12px;
  flex: 0 0 100%;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(11, 13, 16, 0.42);
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: 360px;
  background: var(--paper);
  color: var(--ink);
  border-radius: var(--r-lg);
  padding: 22px;
  box-shadow: var(--shadow-4);
}

@media (max-width: 640px) {
  .poll-slide {
    padding: 36px 16px;
  }
  .question {
    font-size: 30px;
  }
  .choice-btn,
  .choice-readout {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
  }
  .choice-label,
  .bar,
  .count {
    width: 100%;
  }
  .count {
    min-width: 0;
    text-align: left;
  }
  .presenter-controls .btn {
    flex: 1 1 150px;
    justify-content: center;
  }
}
</style>
