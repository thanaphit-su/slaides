<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import Icon from "@/components/Icon.vue";
import type { PollChoice } from "@/api/types";

type InteractionKind = "poll" | "question" | "random";

const props = defineProps<{ kind: InteractionKind }>();

const emit = defineEmits<{
  (e: "close"): void;
  (
    e: "launch",
    payload: {
      kind: InteractionKind;
      spec: Record<string, unknown>;
    },
  ): void;
}>();

const question = ref("");
const prompt = ref("");
const choices = ref<PollChoice[]>([
  { id: "c1", label: "" },
  { id: "c2", label: "" },
]);
const config = ref({ allow_other: false, show_results_live: true, anonymous: true });
const randomCount = ref(1);
const submitting = ref(false);
const error = ref<string | null>(null);
const firstInput = ref<HTMLInputElement | HTMLTextAreaElement | null>(null);

onMounted(() => {
  nextTick(() => firstInput.value?.focus());
});

function nextChoiceId(): string {
  const seen = new Set(choices.value.map((c) => c.id));
  let i = choices.value.length + 1;
  while (seen.has(`c${i}`)) i += 1;
  return `c${i}`;
}

function addChoice() {
  if (choices.value.length >= 8) return;
  choices.value = [...choices.value, { id: nextChoiceId(), label: "" }];
}

function removeChoice(id: string) {
  if (choices.value.length <= 2) return;
  choices.value = choices.value.filter((c) => c.id !== id);
}

function applyTemplate(name: "yesno" | "rating15" | "truefalse") {
  if (name === "yesno") {
    choices.value = [
      { id: "c1", label: "Yes" },
      { id: "c2", label: "No" },
    ];
  } else if (name === "rating15") {
    choices.value = Array.from({ length: 5 }, (_, i) => ({
      id: `c${i + 1}`,
      label: String(i + 1),
    }));
  } else if (name === "truefalse") {
    choices.value = [
      { id: "c1", label: "True" },
      { id: "c2", label: "False" },
    ];
  }
}

const validPoll = computed(
  () =>
    question.value.trim().length > 0 &&
    choices.value.filter((c) => c.label.trim().length > 0).length >= 2,
);
const validQuestion = computed(() => prompt.value.trim().length > 0);
const validRandom = computed(() => Number.isFinite(randomCount.value) && randomCount.value >= 1 && randomCount.value <= 50);
const canLaunch = computed(() =>
  props.kind === "poll" ? validPoll.value : props.kind === "question" ? validQuestion.value : validRandom.value,
);
const launchHint = computed(() => {
  if (canLaunch.value) {
    if (props.kind === "poll") return "poll ready to launch";
    if (props.kind === "question") return "question ready to launch";
    return "random picker ready to launch";
  }
  if (props.kind === "random") return "Choose at least one audience member.";
  if (props.kind === "question") return "Add a prompt before launching.";
  if (!question.value.trim()) return "Add a question before launching.";
  return "Add at least two choices before launching.";
});

async function launch() {
  if (!canLaunch.value || submitting.value) return;
  error.value = null;
  submitting.value = true;
  try {
    if (props.kind === "poll") {
      emit("launch", {
        kind: "poll",
        spec: {
          type: "poll",
          question: question.value.trim(),
          choices: choices.value
            .filter((c) => c.label.trim().length > 0)
            .map((c) => ({ id: c.id, label: c.label.trim() })),
          config: { ...config.value },
          state: { voting_closed: false, choices_locked: false },
        },
      });
    } else if (props.kind === "question") {
      emit("launch", {
        kind: "question",
        spec: {
          type: "question",
          prompt: prompt.value.trim(),
          config: { anonymous: config.value.anonymous },
        },
      });
    } else {
      emit("launch", {
        kind: "random",
        spec: {
          type: "random",
          count: Math.max(1, Math.min(50, Math.round(randomCount.value))),
        },
      });
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not launch interaction.";
  } finally {
    submitting.value = false;
  }
}

watch(
  () => props.kind,
  () => {
    error.value = null;
  },
);
</script>

<template>
  <div class="sheet-backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
    <div class="sheet scale-in" role="dialog" aria-modal="true">
      <header class="sheet-header">
        <div>
          <div class="t-kicker">
            {{ kind === "poll" ? "New poll" : kind === "question" ? "New open question" : "Random audience" }}
          </div>
          <div class="sheet-title">
            {{ kind === "poll" ? "What do you want to ask?" : kind === "question" ? "Prompt the room." : "Pick audience members." }}
          </div>
          <p class="sheet-subtitle">
            {{
              kind === "poll"
                ? "Create a voting slide for the live room."
                : kind === "question"
                  ? "Collect audience answers for presenter moderation."
                  : "Randomly select active audience members for presenter use."
            }}
          </p>
        </div>
        <button class="btn btn-ghost btn-sm" @click="emit('close')" title="Cancel">
          <Icon name="x" :size="14" />
        </button>
      </header>

      <!-- Poll body -->
      <section v-if="kind === 'poll'" class="sheet-body">
        <label class="field">
          <span class="field-label">Question</span>
          <input
            ref="firstInput"
            v-model="question"
            class="input"
            placeholder="e.g. Which approach fits this problem?"
            maxlength="500"
          />
        </label>

        <section class="field">
          <span class="field-label">Templates</span>
          <div class="templates-row">
            <button class="template-pill" type="button" @click="applyTemplate('yesno')">Yes / No</button>
            <button class="template-pill" type="button" @click="applyTemplate('rating15')">1–5</button>
            <button class="template-pill" type="button" @click="applyTemplate('truefalse')">True / False</button>
          </div>
        </section>

        <div class="field">
          <span class="field-label">Choices</span>
          <ul class="choices">
            <li v-for="(c, i) in choices" :key="c.id" class="choice-row">
              <span class="choice-tag">{{ i + 1 }}</span>
              <input
                v-model="c.label"
                class="input"
                :placeholder="`Choice ${i + 1}`"
                maxlength="200"
                @keydown.enter.prevent="i === choices.length - 1 ? addChoice() : null"
              />
              <button
                class="btn btn-ghost btn-sm remove-choice"
                type="button"
                :disabled="choices.length <= 2"
                title="Remove"
                @click="removeChoice(c.id)"
              >
                <Icon name="trash" :size="13" />
              </button>
            </li>
          </ul>
          <button
            class="btn btn-sm add-choice"
            type="button"
            :disabled="choices.length >= 8"
            @click="addChoice"
          >
            <Icon name="plus" :size="13" />
            Add choice
          </button>
        </div>

        <div class="option-stack">
          <label class="option-row">
            <input v-model="config.allow_other" type="checkbox" />
            <span>
              <strong>Allow “Other…” responses</strong>
              <small>Audience can submit a custom answer outside the fixed choices.</small>
            </span>
          </label>
          <label class="option-row">
            <input v-model="config.show_results_live" type="checkbox" />
            <span>
              <strong>Show results live</strong>
              <small>Audience and presenter see the tally update as votes arrive.</small>
            </span>
          </label>
          <label class="option-row">
            <input v-model="config.anonymous" type="checkbox" />
            <span>
              <strong>Anonymous voting</strong>
              <small>Votes are counted without showing participant names.</small>
            </span>
          </label>
        </div>
      </section>

      <!-- Question body -->
      <section v-else-if="kind === 'question'" class="sheet-body">
        <label class="field">
          <span class="field-label">Prompt</span>
          <textarea
            ref="firstInput"
            v-model="prompt"
            class="input"
            rows="3"
            placeholder="e.g. What still feels unclear?"
            maxlength="500"
          />
        </label>
        <div class="option-stack">
          <label class="option-row">
            <input v-model="config.anonymous" type="checkbox" />
            <span>
              <strong>Allow anonymous answers</strong>
              <small>Presenter moderation shows anonymous labels instead of names.</small>
            </span>
          </label>
        </div>
        <p class="helper-copy">
          Audience answers stream into your moderation rail. Click an answer to promote it to the room.
        </p>
      </section>

      <!-- Random audience body -->
      <section v-else class="sheet-body">
        <label class="field">
          <span class="field-label">How many people?</span>
          <input
            ref="firstInput"
            v-model.number="randomCount"
            class="input"
            type="number"
            min="1"
            max="50"
            step="1"
          />
        </label>
        <div class="option-stack">
          <div class="option-row">
            <Icon name="users" :size="16" />
            <span>
              <strong>Pick from active audience</strong>
              <small>Only the presenter sees the selected people in this version.</small>
            </span>
          </div>
        </div>
        <p class="helper-copy">
          If fewer people are connected than requested, SLAIDES will pick everyone available.
        </p>
      </section>

      <footer class="sheet-footer">
        <p :class="error ? 'error-text' : 'hint-text'">{{ error || launchHint }}</p>
        <div class="actions">
          <button class="btn btn-sm" type="button" @click="emit('close')">Cancel</button>
          <button
            class="btn btn-primary btn-sm"
            type="button"
            :disabled="!canLaunch || submitting"
            @click="launch"
          >
            {{ submitting ? "Launching…" : "Launch" }}
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.sheet-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(11, 13, 16, 0.18);
  z-index: 80;
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
}
.sheet {
  width: min(460px, 100vw);
  max-height: 100vh;
  height: 100vh;
  height: 100dvh;
  background: var(--paper);
  border-left: 1px solid var(--rule);
  box-shadow: var(--shadow-4);
  display: flex;
  flex-direction: column;
  position: relative;
}
.sheet-header {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
.sheet-title {
  font-family: var(--serif);
  font-size: 22px;
  letter-spacing: 0;
}
.sheet-subtitle {
  margin: 4px 0 0;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.4;
}
.sheet-body {
  flex: 1;
  padding: 18px 22px 84px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-soft);
}
.templates-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.template-pill {
  border: 1px solid var(--accent-tint);
  border-radius: 999px;
  background: var(--paper);
  color: var(--accent);
  padding: 6px 11px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.template-pill:hover {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.choices {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.choice-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.choice-row .input {
  flex: 1;
}
.choice-tag {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  width: 18px;
  text-align: right;
}
.add-choice {
  align-self: flex-start;
  margin-top: 8px;
}
.remove-choice {
  color: var(--ink-soft);
}
.remove-choice:not(:disabled):hover {
  color: var(--err);
  border-color: rgba(190, 29, 74, 0.25);
}
.option-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.option-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 12px;
  background: var(--paper);
  cursor: pointer;
}
.option-row:hover {
  background: var(--paper-2);
}
.option-row input {
  margin-top: 2px;
}
.option-row span {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.option-row strong {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
}
.option-row small,
.helper-copy {
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.45;
}
.helper-copy {
  margin: 0;
  font-family: var(--serif);
  font-size: 14px;
}
.sheet-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 12px 22px;
  border-top: 1px solid var(--rule);
  background: var(--paper);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}
.error-text {
  margin: 0;
  color: var(--err);
  font-size: 12px;
}
.hint-text {
  margin: 0;
  color: var(--ink-soft);
  font-size: 12px;
  font-family: var(--mono);
  letter-spacing: 0.04em;
}

@media (max-width: 640px) {
  .sheet-backdrop {
    align-items: flex-end;
  }
  .sheet {
    width: 100vw;
    height: min(88vh, 680px);
    border-left: 0;
    border-top: 1px solid var(--rule);
    border-top-left-radius: var(--r-lg);
    border-top-right-radius: var(--r-lg);
  }
  .sheet-footer {
    align-items: stretch;
    flex-direction: column;
  }
  .actions {
    width: 100%;
  }
  .actions .btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
