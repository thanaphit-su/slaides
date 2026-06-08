<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/Icon.vue";
import type { Slide } from "@/api/types";

const props = defineProps<{ slides: Slide[]; activeSlideId: string | null }>();
const emit = defineEmits<{ (e: "select", id: string): void }>();

const WINDOW_SIZE = 7;

const idx = computed(() => props.slides.findIndex((s) => s.id === props.activeSlideId));

const paginationItems = computed(() => {
  const total = props.slides.length;
  const active = idx.value;
  if (total <= WINDOW_SIZE || active < 0) {
    return props.slides.map((slide, index) => ({ slide, index }));
  }

  const radius = Math.floor(WINDOW_SIZE / 2);
  let start = Math.max(0, active - radius);
  let end = Math.min(total - 1, start + WINDOW_SIZE - 1);
  if (end - start + 1 < WINDOW_SIZE) {
    start = Math.max(0, end - WINDOW_SIZE + 1);
  }

  const items: Array<{ slide: Slide; index: number }> = [];
  for (let index = start; index <= end; index += 1) {
    items.push({ slide: props.slides[index], index });
  }
  return items;
});

const hasHiddenBefore = computed(() => {
  const first = paginationItems.value[0];
  return !!first && first.index > 0;
});

const hasHiddenAfter = computed(() => {
  const last = paginationItems.value[paginationItems.value.length - 1];
  return !!last && last.index < props.slides.length - 1;
});

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
      <div
        data-testid="editor-slide-stepper-window"
        :style="{
          position: 'relative',
          overflow: 'hidden',
        }"
      >
        <span
          v-if="hasHiddenBefore"
          data-testid="editor-slide-stepper-fade-left"
          aria-hidden="true"
          :style="{
            position: 'absolute',
            inset: '0 auto 0 0',
            width: '18px',
            zIndex: 1,
            pointerEvents: 'none',
            background: 'linear-gradient(90deg, var(--paper), transparent)',
          }"
        />
        <span
          v-if="hasHiddenAfter"
          data-testid="editor-slide-stepper-fade-right"
          aria-hidden="true"
          :style="{
            position: 'absolute',
            inset: '0 0 0 auto',
            width: '18px',
            zIndex: 1,
            pointerEvents: 'none',
            background: 'linear-gradient(270deg, var(--paper), transparent)',
          }"
        />
        <div
          :style="{
            display: 'flex',
            gap: '6px',
            alignItems: 'center',
            paddingLeft: hasHiddenBefore ? '8px' : '0',
            paddingRight: hasHiddenAfter ? '8px' : '0',
          }"
        >
          <button
            v-for="item in paginationItems"
            :key="item.slide.id"
            type="button"
            data-testid="editor-slide-stepper-dot"
            @click="emit('select', item.slide.id)"
            :title="`Slide ${item.index + 1}`"
            :aria-label="`Go to slide ${item.index + 1}`"
            :style="{
              width: item.index === idx ? '9px' : '7px',
              height: item.index === idx ? '9px' : '7px',
              flex: '0 0 auto',
              borderRadius: '50%',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              background: item.index === idx ? 'var(--ink)' : 'var(--rule-strong)',
              transition: 'background .15s ease, width .15s ease, height .15s ease',
            }"
          />
        </div>
      </div>
      <span class="t-mono" :style="{ color: 'var(--ink-soft)' }">
        {{ idx >= 0 ? idx + 1 : "—" }} / {{ props.slides.length }}
      </span>
    </div>

    <button class="btn btn-ghost btn-sm" :disabled="idx >= props.slides.length - 1" @click="next">
      Next <Icon name="chev_right" :size="16" />
    </button>
  </div>
</template>
