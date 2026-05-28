<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    message?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    tone?: "danger" | "default";
    busy?: boolean;
  }>(),
  {
    message: "",
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
    tone: "default",
    busy: false,
  },
);
const emit = defineEmits<{
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();

function onBackdrop() {
  if (!props.busy) emit("cancel");
}

function onKey(e: KeyboardEvent) {
  if (!props.open) return;
  if (e.key === "Escape" && !props.busy) emit("cancel");
  if (e.key === "Enter" && !props.busy) emit("confirm");
}

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));

// Prevent body scroll while the modal is open.
watch(
  () => props.open,
  (isOpen) => {
    document.body.style.overflow = isOpen ? "hidden" : "";
  },
);
</script>

<template>
  <div v-if="open" class="confirm-backdrop" @click.self="onBackdrop">
    <div class="confirm-modal scale-in" role="alertdialog" aria-modal="true">
      <h3>{{ title }}</h3>
      <p v-if="message">
        <slot>{{ message }}</slot>
      </p>
      <p v-else>
        <slot />
      </p>
      <div class="confirm-actions">
        <button class="btn btn-sm" :disabled="busy" @click="emit('cancel')">
          {{ cancelLabel }}
        </button>
        <button
          :class="['btn', 'btn-sm', tone === 'danger' ? 'btn-danger' : 'btn-primary']"
          :disabled="busy"
          @click="emit('confirm')"
        >
          {{ busy ? "Working…" : confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 120;
  background: rgba(11, 13, 16, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.confirm-modal {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 20px;
  width: 400px;
  max-width: 100%;
  box-shadow: var(--shadow-3);
}
.confirm-modal h3 {
  margin: 0 0 10px;
  font-family: var(--serif);
  font-size: 18px;
  color: var(--ink);
}
.confirm-modal p {
  margin: 0 0 18px;
  font-size: 13.5px;
  color: var(--ink-soft);
  font-family: var(--sans);
  line-height: 1.55;
  white-space: pre-line;
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn-danger {
  background: var(--err, #c2410c);
  color: var(--paper);
  border: 1px solid var(--err, #c2410c);
}
.btn-danger:hover:not(:disabled) {
  filter: brightness(0.95);
}
</style>
