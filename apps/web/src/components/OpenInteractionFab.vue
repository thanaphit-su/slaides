<script setup lang="ts">
import { ref } from "vue";
import Icon from "@/components/Icon.vue";

type InteractionKind = "poll" | "question" | "random";

const emit = defineEmits<{ (e: "pick", kind: InteractionKind): void }>();

const open = ref(false);

function pick(kind: InteractionKind) {
  open.value = false;
  emit("pick", kind);
}
</script>

<template>
  <div
    :style="{
      position: 'fixed',
      bottom: 'calc(92px + env(safe-area-inset-bottom))',
      right: '28px',
      zIndex: 30,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-end',
      gap: '10px',
    }"
  >
    <div
      v-if="open"
      class="scale-in"
      :style="{
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-3)',
        padding: '6px',
        display: 'flex',
        flexDirection: 'column',
        minWidth: '220px',
      }"
    >
      <button class="btn btn-ghost" :style="{ justifyContent: 'flex-start' }" @click="pick('poll')">
        Open poll as new slide
      </button>
      <button class="btn btn-ghost" :style="{ justifyContent: 'flex-start' }" @click="pick('question')">
        Open question as new slide
      </button>
      <button class="btn btn-ghost" :style="{ justifyContent: 'flex-start' }" @click="pick('random')">
        Random audience as new slide
      </button>
    </div>

    <button
      :title="open ? 'Close interaction menu' : 'Open interaction'"
      @click="open = !open"
      :style="{
        width: '56px',
        height: '56px',
        borderRadius: '50%',
        background: 'var(--accent)',
        color: 'var(--paper)',
        border: 'none',
        cursor: 'pointer',
        boxShadow: 'var(--shadow-3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transform: open ? 'rotate(45deg)' : 'none',
        transition: 'transform .2s ease',
      }"
    >
      <Icon name="plus" :size="24" />
    </button>
  </div>
</template>
