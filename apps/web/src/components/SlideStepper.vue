<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/Icon.vue";
import type { Slide } from "@/api/types";

const props = defineProps<{ slides: Slide[]; activeSlideId: string | null }>();
const emit = defineEmits<{ (e: "select", id: string): void }>();

const idx = computed(() => props.slides.findIndex((s) => s.id === props.activeSlideId));

function prev() {
  if (idx.value > 0) emit("select", props.slides[idx.value - 1].id);
}
function next() {
  if (idx.value < props.slides.length - 1) emit("select", props.slides[idx.value + 1].id);
}
</script>

<template>
  <div
    :style="{
      height: '48px',
      borderTop: '1px solid var(--rule)',
      background: 'var(--paper)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 18px',
      flexShrink: 0,
    }"
  >
    <button class="btn btn-ghost btn-sm" :disabled="idx <= 0" @click="prev">
      <Icon name="chev_left" :size="16" /> Prev
    </button>

    <div :style="{ display: 'flex', alignItems: 'center', gap: '14px' }">
      <div :style="{ display: 'flex', gap: '6px', alignItems: 'center' }">
        <button
          v-for="(s, i) in props.slides"
          :key="s.id"
          @click="emit('select', s.id)"
          :title="`Slide ${i + 1}`"
          :style="{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            background: i === idx ? 'var(--ink)' : 'var(--rule-strong)',
            transition: 'background .15s ease',
          }"
        />
      </div>
      <span class="t-mono" :style="{ color: 'var(--ink-soft)' }">
        {{ idx + 1 }} / {{ props.slides.length }}
      </span>
    </div>

    <button class="btn btn-ghost btn-sm" :disabled="idx >= props.slides.length - 1" @click="next">
      Next <Icon name="chev_right" :size="16" />
    </button>
  </div>
</template>
