<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; label?: string }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();
</script>

<template>
  <button
    type="button"
    @click="emit('update:modelValue', !props.modelValue)"
    :style="{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '10px',
      background: 'transparent',
      border: 'none',
      padding: 0,
      color: 'var(--ink)',
      cursor: 'pointer',
    }"
  >
    <span
      :style="{
        width: '34px',
        height: '20px',
        borderRadius: '999px',
        background: props.modelValue ? 'var(--accent)' : 'var(--rule-strong)',
        position: 'relative',
        transition: 'background .15s ease',
        display: 'inline-block',
        flexShrink: 0,
      }"
    >
      <span
        :style="{
          position: 'absolute',
          top: '2px',
          left: props.modelValue ? '16px' : '2px',
          width: '16px',
          height: '16px',
          borderRadius: '50%',
          background: 'var(--paper)',
          transition: 'left .15s ease',
          boxShadow: 'var(--shadow-1)',
        }"
      />
    </span>
    <span v-if="props.label" :style="{ fontSize: '13px', color: 'var(--ink)' }">{{ props.label }}</span>
  </button>
</template>
