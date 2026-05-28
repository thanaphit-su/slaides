<script setup lang="ts">
import { ref } from "vue";
import Toggle from "@/components/Toggle.vue";

const props = defineProps<{ defaultAnon: boolean }>();
const emit = defineEmits<{
  (e: "submit", payload: { text: string; anonymous: boolean }): void;
  (e: "close"): void;
}>();

const text = ref("");
const anon = ref(props.defaultAnon);

function submit() {
  const trimmed = text.value.trim();
  if (!trimmed) return;
  emit("submit", { text: trimmed, anonymous: anon.value });
  text.value = "";
}
</script>

<template>
  <div
    class="fade-in"
    :style="{
      position: 'fixed',
      inset: 0,
      background: 'rgba(11,13,16,0.42)',
      zIndex: 60,
      display: 'flex',
      alignItems: 'flex-end',
      justifyContent: 'center',
    }"
    @click.self="emit('close')"
  >
    <div
      class="slide-up"
      :style="{
        width: '100%',
        maxWidth: '420px',
        background: 'var(--paper)',
        borderTopLeftRadius: '20px',
        borderTopRightRadius: '20px',
        padding: '24px',
      }"
    >
      <form @submit.prevent="submit">
        <div class="t-kicker" :style="{ marginBottom: '6px' }">Audience</div>
        <div class="t-h3" :style="{ marginBottom: '14px' }">Raise a question.</div>
        <textarea
          v-model="text"
          rows="4"
          class="input"
          placeholder="What's on your mind?"
          :style="{ width: '100%', fontFamily: 'var(--serif)', fontSize: '15px' }"
          @keydown.enter.exact.prevent="submit"
        />
        <p class="t-meta" :style="{ margin: '8px 0 0' }">Enter to send · Shift+Enter for a new line</p>
        <div
          :style="{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 12px',
            border: '1px solid var(--rule)',
            borderRadius: 'var(--r-md)',
            margin: '12px 0',
          }"
        >
          <div :style="{ fontSize: '13px' }">Send anonymously</div>
          <Toggle v-model="anon" />
        </div>
        <button
          class="btn btn-primary"
          type="submit"
          :disabled="!text.trim()"
          :style="{ width: '100%', justifyContent: 'center', padding: '12px' }"
        >
          Send to instructor
        </button>
      </form>
    </div>
  </div>
</template>
