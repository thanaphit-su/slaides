<script setup lang="ts">
import Icon from "@/components/Icon.vue";

defineProps<{ visible: boolean }>();
defineEmits<{
  (e: "pick-library"): void;
  (e: "generate"): void;
}>();
</script>

<template>
  <div
    :style="{
      marginTop: '32px',
      padding: '22px 24px',
      borderRadius: 'var(--r-lg)',
      border: '1.5px dashed ' + (visible ? 'var(--accent)' : 'var(--rule-strong)'),
      background: visible ? 'var(--accent-soft)' : 'transparent',
      transition: 'border-color .2s ease, background .2s ease',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '12px',
      color: 'var(--ink-soft)',
      fontFamily: 'var(--sans)',
    }"
  >
    <Icon name="widget" :size="20" />
    <div :style="{ fontFamily: 'var(--serif)', fontSize: '17px', color: 'var(--ink)' }">
      Add a widget to this slide.
    </div>
    <div :style="{ fontSize: '12px', color: 'var(--ink-soft)' }">
      One widget per slide — pick from your library or generate one with AI.
    </div>
    <div :style="{ display: 'flex', gap: '8px' }">
      <button class="btn btn-sm" @click="$emit('pick-library')">
        <Icon name="widget" :size="14" /> From collection
      </button>
      <button class="btn btn-primary btn-sm" @click="$emit('generate')">
        Generate with AI
      </button>
    </div>
  </div>
</template>
