<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { llmApi } from "@/api/llm";
import Icon from "@/components/Icon.vue";

const props = defineProps<{
  x: number;
  y: number;
  text: string;
  initialInstruction?: string;
  allowInsert?: boolean;
  authToken?: string | null;
  context?: Record<string, unknown>;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "insert", text: string): void;
}>();

const instruction = ref(props.initialInstruction || "in plain English");
const response = ref("");
const loading = ref(false);
const error = ref<string | null>(null);
const copied = ref(false);
let currentAbort: AbortController | null = null;

const popStyle = computed(() => {
  const width = Math.min(380, Math.max(280, window.innerWidth - 16));
  const left = Math.min(Math.max(8, props.x + 8), window.innerWidth - width - 8);
  const top = Math.min(Math.max(8, props.y + 8), window.innerHeight - 260);
  return { left: `${left}px`, top: `${top}px`, width: `${width}px` };
});

async function run() {
  if (!props.text.trim()) return;
  // Abort any in-flight call before kicking off a new one (the popover re-runs
  // on prop changes), so the dropped reply never overwrites the new one.
  currentAbort?.abort();
  const controller = new AbortController();
  currentAbort = controller;
  loading.value = true;
  response.value = "";
  error.value = null;
  try {
    response.value = await llmApi.completeText({
      purpose: "interpret",
      prompt: instruction.value.trim() || "in plain English",
      context: { ...(props.context || {}), selection: props.text },
    }, {
      token: props.authToken,
      signal: controller.signal,
    });
  } catch (err) {
    if (controller.signal.aborted) return;
    error.value = err instanceof Error ? err.message : "Could not interpret the selection.";
  } finally {
    if (currentAbort === controller) {
      currentAbort = null;
      loading.value = false;
    }
  }
}

function cancelRun() {
  currentAbort?.abort();
  loading.value = false;
}

async function copyResponse() {
  if (!response.value) return;
  try {
    await navigator.clipboard.writeText(response.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    error.value = "Could not copy — clipboard access blocked.";
  }
}

onMounted(run);
onBeforeUnmount(() => {
  currentAbort?.abort();
  currentAbort = null;
});
watch(
  () => props.text,
  () => void run(),
);
watch(
  () => props.initialInstruction,
  (next) => {
    instruction.value = next || "in plain English";
    void run();
  },
);
</script>

<template>
  <div class="interpret-popover scale-in" :style="popStyle" @click.stop>
    <header class="interpret-header">
      <span>
        <Icon name="widget" :size="14" />
        Interpret
      </span>
      <button class="btn btn-ghost btn-sm" @click="emit('close')" title="Close">
        <Icon name="x" :size="14" />
      </button>
    </header>

    <div class="selection-box">"{{ props.text }}"</div>
    <div class="instruction-row">
      <input
        v-model="instruction"
        class="input instruction-input"
        @keydown.enter.prevent="run"
      />
      <button
        v-if="loading"
        class="btn btn-sm icon-button cancel-button"
        type="button"
        title="Cancel"
        @click="cancelRun"
      >
        <Icon name="x" :size="14" />
      </button>
      <button
        v-else
        class="btn btn-primary btn-sm icon-button"
        type="button"
        title="Send"
        :disabled="!instruction.trim()"
        @click="run"
      >
        <Icon name="arrow_right" :size="14" />
      </button>
    </div>

    <div v-if="loading" class="loading-lines">
      <span class="pulse" style="width: 92%" />
      <span class="pulse" style="width: 78%" />
      <span class="pulse" style="width: 60%" />
    </div>
    <div v-else-if="response" class="response-text">{{ response }}</div>
    <div v-else-if="error" class="error-text">{{ error }}</div>

    <footer class="interpret-actions">
      <button class="btn btn-sm" :disabled="!response" @click="copyResponse">{{ copied ? "Copied" : "Copy" }}</button>
      <button v-if="props.allowInsert !== false" class="btn btn-primary btn-sm" :disabled="!response" @click="emit('insert', response)">
        Insert below
      </button>
    </footer>
  </div>
</template>

<style scoped>
.interpret-popover {
  position: fixed;
  z-index: 90;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-3);
  padding: 16px;
}

.interpret-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.interpret-header span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.selection-box {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-soft);
  padding: 8px 10px;
  background: var(--paper-2);
  border-radius: var(--r-sm);
  margin-bottom: 10px;
  max-height: 96px;
  overflow: auto;
}

.instruction-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.instruction-input {
  flex: 1;
}

.icon-button {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cancel-button {
  color: var(--err);
  border-color: var(--err);
}

.loading-lines {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.loading-lines span {
  height: 8px;
  border-radius: 4px;
  background: var(--accent-tint);
}

.response-text {
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre-wrap;
}

.error-text {
  color: var(--err);
  font-size: 12px;
}

.interpret-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
