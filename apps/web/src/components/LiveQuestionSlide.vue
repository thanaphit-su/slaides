<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { sessionsApi } from "@/api/sessions";
import { useSessionStore } from "@/stores/session";
import Icon from "@/components/Icon.vue";
import type { PromotedAnswer, QuestionResults, QuestionSpec, SessionSlide } from "@/api/types";

const props = defineProps<{
  slide: SessionSlide;
  role: "presenter" | "audience" | "mirror";
  inverted: boolean;
}>();

const session = useSessionStore();

const spec = computed<QuestionSpec>(
  () =>
    (props.slide.spec as unknown as QuestionSpec) || {
      type: "question",
      prompt: "",
      config: { anonymous: true },
    },
);
const results = computed<QuestionResults>(() => {
  const r = (props.slide.results as unknown as QuestionResults) || ({} as QuestionResults);
  return { promoted: r.promoted || [], total_answers: r.total_answers || 0 };
});

// ---- Audience submission ----
const draft = ref("");
const submitted = ref(false);
const submitCount = ref(0);

function submit() {
  const t = draft.value.trim();
  if (!t || props.role !== "audience") return;
  session.submitOpenAnswer(props.slide.id, t);
  draft.value = "";
  submitted.value = true;
  submitCount.value += 1;
  window.setTimeout(() => (submitted.value = false), 1500);
}

// ---- Presenter prompt editing + save-to-library ----
const editing = ref(false);
const draftPrompt = ref(spec.value.prompt || "");
const busy = ref<string | null>(null);
const savedFlag = ref(false);
const lastError = ref<string | null>(null);

async function savePrompt() {
  const v = draftPrompt.value.trim();
  if (!v || busy.value) return;
  busy.value = "prompt";
  lastError.value = null;
  try {
    await sessionsApi.patchInteraction(props.slide.session_id, props.slide.id, { prompt: v });
    editing.value = false;
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : "Could not save.";
  } finally {
    busy.value = null;
  }
}

async function saveToLibrary() {
  if (busy.value) return;
  busy.value = "save";
  lastError.value = null;
  try {
    await sessionsApi.saveInteractionAsWidget(props.slide.id);
    savedFlag.value = true;
    window.setTimeout(() => (savedFlag.value = false), 2000);
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : "Could not save.";
  } finally {
    busy.value = null;
  }
}

// ---- Featured cycling (audience-facing) ----
const featuredIndex = ref(0);
const promoted = computed<PromotedAnswer[]>(() => results.value.promoted);

let cycleTimer = 0;
function startCycle() {
  if (cycleTimer) window.clearInterval(cycleTimer);
  if (promoted.value.length > 2) {
    cycleTimer = window.setInterval(() => {
      featuredIndex.value = (featuredIndex.value + 1) % promoted.value.length;
    }, 10_000);
  }
}
onBeforeUnmount(() => {
  if (cycleTimer) window.clearInterval(cycleTimer);
});
// Re-arm whenever the promoted list size changes (initial render too).
watch(
  () => promoted.value.length,
  () => {
    featuredIndex.value = 0;
    startCycle();
  },
  { immediate: true },
);

const visibleFeatured = computed<PromotedAnswer[]>(() => {
  const list = promoted.value;
  if (list.length === 0) return [];
  if (list.length <= 2) return list;
  // Show 2-at-a-time window starting at featuredIndex.
  return [list[featuredIndex.value], list[(featuredIndex.value + 1) % list.length]];
});
</script>

<template>
  <div class="question-slide" :class="{ inverted: inverted }">
    <div class="question-inner">
      <div class="kicker">QUESTION</div>

      <div v-if="role === 'presenter' && editing" class="edit-row">
        <input v-model="draftPrompt" class="input edit-input" maxlength="500" />
        <button class="btn btn-sm" type="button" @click="editing = false">Cancel</button>
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="busy === 'prompt'"
          @click="savePrompt"
        >
          Save
        </button>
      </div>
      <h2 v-else class="prompt">
        {{ spec.prompt || "Untitled question" }}
        <button
          v-if="role === 'presenter'"
          class="btn btn-ghost btn-sm edit-pencil"
          type="button"
          @click="() => { draftPrompt = spec.prompt; editing = true; }"
          title="Edit prompt"
        >
          <Icon name="edit" :size="13" />
        </button>
      </h2>

      <!-- Audience input -->
      <section v-if="role === 'audience'" class="answer-form">
        <textarea
          v-model="draft"
          class="input"
          rows="3"
          maxlength="2000"
          placeholder="Your answer…"
          @keydown.enter.exact.prevent="submit"
        />
        <div class="answer-form-row">
          <span class="meta">
            {{
              submitted
                ? "Sent. Waiting for the presenter."
                : submitCount
                  ? "Send another answer, or wait for promoted responses."
                  : "Enter to send · Shift+Enter for a new line"
            }}
          </span>
          <button class="btn btn-primary btn-sm send-btn" type="button" :disabled="!draft.trim()" @click="submit">
            <Icon name="arrow_right" :size="13" />
            Send
          </button>
        </div>
      </section>

      <!-- Featured promoted answers (visible to both) -->
      <section v-if="visibleFeatured.length" class="featured">
        <div class="featured-label">Featured</div>
        <div
          v-for="answer in visibleFeatured"
          :key="answer.id"
          class="featured-card scale-in"
        >
          <p class="featured-text">"{{ answer.text }}"</p>
          <p class="featured-attr">
            — {{ answer.anon ? "Anonymous" : answer.display_name || "Audience" }}
          </p>
        </div>
      </section>

      <p v-else-if="role === 'audience'" class="meta">
        Answers will appear here when the presenter promotes them.
      </p>

      <footer v-if="role === 'presenter'" class="presenter-controls">
        <span class="meta">{{ results.total_answers }} answer{{ results.total_answers === 1 ? "" : "s" }} · {{ promoted.length }} promoted</span>
        <button class="btn btn-sm" type="button" :disabled="!!busy" @click="saveToLibrary">
          <Icon name="copy" :size="13" />
          {{ savedFlag ? "Saved" : "Save to library" }}
        </button>
        <p v-if="lastError" class="error-text">{{ lastError }}</p>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.question-slide {
  width: 100%;
  min-height: 100%;
  padding: clamp(48px, 8vh, 92px) 24px;
}
.question-inner {
  width: min(720px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.kicker {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: var(--accent);
  text-transform: uppercase;
}
.question-slide.inverted .kicker {
  color: var(--paper);
  opacity: 0.7;
}
.prompt {
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
  margin-top: 5px;
  border-color: rgba(255, 255, 255, 0.18);
  opacity: 0.85;
}
.question-slide:not(.inverted) .edit-pencil {
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
.answer-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.answer-form .input {
  resize: vertical;
  min-height: 82px;
  font-family: var(--sans);
  font-size: 14px;
  border-color: rgba(31, 58, 138, 0.45);
}
.answer-form-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--ink-soft);
}
.question-slide.inverted .answer-form-row {
  color: var(--paper);
  opacity: 0.7;
}
.send-btn {
  min-width: 82px;
  justify-content: center;
}
.send-btn:disabled {
  background: transparent;
  color: var(--ink-mute);
}
.question-slide.inverted .send-btn:disabled {
  color: rgba(255, 255, 255, 0.45);
  border-color: rgba(255, 255, 255, 0.18);
}
.featured {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.featured-label {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-soft);
}
.question-slide.inverted .featured-label {
  color: var(--paper);
  opacity: 0.7;
}
.featured-card {
  background: var(--paper-2);
  border-left: 3px solid var(--accent);
  padding: 16px 18px;
  border-radius: var(--r-md);
}
.question-slide.inverted .featured-card {
  background: rgba(255, 255, 255, 0.08);
  border-left-color: var(--paper);
}
.featured-text {
  margin: 0 0 6px;
  font-family: var(--serif);
  font-size: 20px;
  line-height: 1.4;
  color: var(--ink);
}
.question-slide.inverted .featured-text {
  color: var(--paper);
}
.featured-attr {
  margin: 0;
  font-size: 12px;
  color: var(--ink-soft);
}
.question-slide.inverted .featured-attr {
  color: var(--paper);
  opacity: 0.7;
}
.meta {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-soft);
}
.question-slide.inverted .meta {
  color: var(--paper);
  opacity: 0.7;
}
.presenter-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: var(--shadow-1);
}
.question-slide.inverted .presenter-controls {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
}
.error-text {
  margin: 0;
  flex: 0 0 100%;
  color: var(--err);
  font-size: 12px;
}

@media (max-width: 640px) {
  .question-slide {
    padding: 36px 16px;
  }
  .prompt {
    font-size: 30px;
  }
  .answer-form-row,
  .presenter-controls {
    align-items: stretch;
    flex-direction: column;
  }
  .send-btn,
  .presenter-controls .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
