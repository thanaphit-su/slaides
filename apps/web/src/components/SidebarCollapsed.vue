<script setup lang="ts">
import Icon from "@/components/Icon.vue";

defineEmits<{
  (e: "expand"): void;
  (e: "select-tab", t: "sections" | "widgets" | "theme"): void;
}>();
</script>

<template>
  <div :style="{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 0', gap: '6px' }">
    <button class="btn btn-ghost btn-sm" @click="$emit('expand')" title="Expand sidebar">
      <Icon name="chev_right" :size="16" />
    </button>
    <button
      class="btn btn-ghost btn-sm"
      @click="$emit('select-tab', 'sections')"
      title="Sections"
      :style="{ marginTop: '8px' }"
    >
      <Icon name="list" :size="16" />
    </button>
    <button class="btn btn-ghost btn-sm" @click="$emit('select-tab', 'widgets')" title="Widgets">
      <Icon name="widget" :size="16" />
    </button>
    <button class="btn btn-ghost btn-sm" @click="$emit('select-tab', 'theme')" title="Theme">
      <Icon name="theme" :size="16" />
    </button>
  </div>
</template>
