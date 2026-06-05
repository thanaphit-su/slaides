<script setup lang="ts">
import { computed, ref } from "vue";
import QuestionsRail from "@/components/QuestionsRail.vue";
import type { SessionQuestion } from "@/api/types";

const props = defineProps<{
  notes: string | null | undefined;
  questions: SessionQuestion[];
}>();
const emit = defineEmits<{ (e: "answer", id: string): void }>();

const tab = ref<"notes" | "questions">("notes");
const unansweredCount = computed(() => props.questions.filter((q) => !q.answered_at).length);
const noteText = computed(() => props.notes?.trim() || "");
</script>

<template>
  <aside class="presenter-rail">
    <nav class="presenter-rail-tabs" aria-label="Presenter sidebar">
      <button
        type="button"
        class="presenter-rail-tab"
        :class="{ active: tab === 'notes' }"
        data-testid="presenter-rail-tab-notes"
        @click="tab = 'notes'"
      >
        Notes
      </button>
      <button
        type="button"
        class="presenter-rail-tab"
        :class="{ active: tab === 'questions' }"
        data-testid="presenter-rail-tab-questions"
        @click="tab = 'questions'"
      >
        Questions
        <span v-if="unansweredCount" class="presenter-rail-count">{{ unansweredCount }}</span>
      </button>
    </nav>

    <section v-if="tab === 'notes'" class="presenter-notes-pane">
      <div class="t-kicker">Presenter note</div>
      <div v-if="noteText" class="presenter-note-copy">
        {{ noteText }}
      </div>
      <div v-else class="presenter-note-empty">
        No notes for this slide.
      </div>
    </section>

    <QuestionsRail
      v-else
      class="presenter-questions-pane"
      :questions="questions"
      :embedded="true"
      @answer="emit('answer', $event)"
    />
  </aside>
</template>

<style scoped>
.presenter-rail {
  width: 360px;
  border-left: 1px solid var(--rule);
  background: var(--paper-2);
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.presenter-rail-tabs {
  display: flex;
  gap: 2px;
  padding: 12px 14px 8px;
  border-bottom: 1px solid var(--rule-soft);
  background: var(--paper);
}

.presenter-rail-tab {
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink-mute);
  padding: 5px 10px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.presenter-rail-tab.active {
  color: var(--ink);
  background: var(--paper-2);
}

.presenter-rail-count {
  min-width: 17px;
  height: 17px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--err);
  color: var(--paper);
  font-size: 10px;
}

.presenter-notes-pane {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 16px;
}

.presenter-note-copy {
  margin-top: 16px;
  white-space: pre-wrap;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
}

.presenter-note-empty {
  margin-top: 40px;
  text-align: center;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-style: italic;
  font-size: 14px;
}

.presenter-questions-pane {
  flex: 1;
  min-height: 0;
}
</style>
