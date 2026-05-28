<script setup lang="ts">
defineEmits<{ (e: "close"): void }>();
</script>

<template>
  <div
    class="fade-in"
    @click="$emit('close')"
    style="
      position: fixed;
      inset: 0;
      background: rgba(11, 13, 16, 0.42);
      z-index: 50;
      display: flex;
      align-items: center;
      justify-content: center;
    "
  >
    <slot />
  </div>
</template>
