<script setup lang="ts">
import type { SessionQuestion } from "@/api/types";

defineProps<{ questions: SessionQuestion[] }>();
const emit = defineEmits<{ (e: "answer", id: string): void }>();

function relTime(ts: string): string {
  const ms = Date.now() - new Date(ts).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / 3_600_000)}h ago`;
}
</script>

<template>
  <aside
    :style="{
      width: '360px',
      borderLeft: '1px solid var(--rule)',
      background: 'var(--paper-2)',
      overflowY: 'auto',
      padding: '20px 16px',
      flexShrink: 0,
    }"
  >
    <div class="t-kicker" :style="{ marginBottom: '12px' }">
      Questions · {{ questions.length }}
    </div>
    <div
      v-if="!questions.length"
      :style="{
        marginTop: '40px',
        textAlign: 'center',
        color: 'var(--ink-soft)',
        fontFamily: 'var(--serif)',
        fontStyle: 'italic',
        fontSize: '14px',
      }"
    >
      No questions yet. The room is reading.
    </div>
    <div
      v-for="q in questions"
      :key="q.id"
      :style="{
        marginBottom: '14px',
        padding: '12px 14px',
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 'var(--r-md)',
        opacity: q.answered_at ? 0.55 : 1,
      }"
    >
      <div
        :style="{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '11px',
          color: 'var(--ink-soft)',
          marginBottom: '6px',
        }"
      >
        <span>{{ q.anon ? "Anonymous" : q.participant_ref.slice(0, 6) }}</span>
        <span>{{ relTime(q.raised_at) }}</span>
      </div>
      <div
        :style="{
          fontFamily: 'var(--serif)',
          fontSize: '15px',
          lineHeight: 1.5,
          marginBottom: '8px',
        }"
      >
        {{ q.text }}
      </div>
      <button
        v-if="!q.answered_at"
        class="btn btn-sm btn-ghost"
        @click="emit('answer', q.id)"
      >
        Mark answered
      </button>
      <span
        v-else
        :style="{ fontSize: '11px', color: 'var(--ink-soft)', fontStyle: 'italic' }"
      >
        Answered
      </span>
    </div>
  </aside>
</template>
