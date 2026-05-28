<script setup lang="ts">
import { ref } from "vue";
import Icon from "@/components/Icon.vue";

defineEmits<{ (e: "create"): void }>();

const hover = ref(false);
</script>

<template>
  <button
    @click="$emit('create')"
    @mouseenter="hover = true"
    @mouseleave="hover = false"
    :style="{
      background: 'transparent',
      border: '1.5px dashed ' + (hover ? 'var(--accent)' : 'var(--rule-strong)'),
      borderRadius: 'var(--r-lg)',
      minHeight: '280px',
      color: hover ? 'var(--accent)' : 'var(--ink-soft)',
      cursor: 'pointer',
      fontFamily: 'var(--sans)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '14px',
      transition: 'all .15s ease',
    }"
  >
    <Icon name="plus" :size="22" />
    <span :style="{ fontWeight: 600, fontSize: '14px' }">New deck</span>
    <span :style="{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: '13px' }">
      or drop a .slaides file to import
    </span>
  </button>
</template>
