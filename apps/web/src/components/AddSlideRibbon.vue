<script setup lang="ts">
import Icon from "@/components/Icon.vue";

withDefaults(defineProps<{ visible: boolean; placement?: "top" | "bottom"; label?: string }>(), {
  placement: "top",
  label: "Add slide above",
});
defineEmits<{ (e: "insert"): void }>();
</script>

<template>
  <div
    :style="{
      position: 'absolute',
      top: placement === 'top' ? '12px' : 'auto',
      bottom: placement === 'bottom' ? '20px' : 'auto',
      left: '50%',
      transform: 'translateX(-50%)',
      pointerEvents: visible ? 'auto' : 'none',
      opacity: visible ? 1 : 0,
      transition: 'opacity .2s ease',
      zIndex: 5,
    }"
  >
    <button
      class="btn btn-sm"
      @click="$emit('insert')"
      :style="{
        background: 'var(--paper)',
        boxShadow: 'var(--shadow-2)',
        borderColor: 'var(--rule-strong)',
      }"
    >
      <Icon name="plus" :size="14" /> {{ label }}
    </button>
  </div>
</template>
