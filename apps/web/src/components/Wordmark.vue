<script setup lang="ts">
const props = withDefaults(defineProps<{ size?: number; withMark?: boolean }>(), {
  size: 18,
  withMark: true,
});
</script>

<template>
  <span style="display: inline-flex; align-items: center; gap: 8px">
    <svg
      v-if="props.withMark"
      :width="props.size + 4"
      :height="props.size + 4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
    >
      <rect x="3" y="6" width="18" height="13" rx="2" />
      <path d="M3 10h18" />
      <circle cx="6.5" cy="8" r=".7" fill="currentColor" stroke="none" />
    </svg>
    <span
      :style="{
        fontFamily: 'var(--serif)',
        fontWeight: 500,
        fontSize: `${props.size}px`,
        letterSpacing: '0.22em',
      }"
      >SLAIDES</span
    >
  </span>
</template>
