<script setup lang="ts">
/**
 * Live-render iframe wrapper for the preview tab's meeting-app layout.
 *
 * No chrome here on purpose — the rail thumb labels and the stage chrome
 * strip both live in Preview.vue. Sizing is also external: the parent
 * positions this tile via inline styles (fixed-position, width/height/transform)
 * and we just render the iframe at 100% of whatever box we get.
 *
 * Critical: the iframe's parent DOM node must stay stable for the lifetime of
 * the component — browsers reload iframes on reparenting. Preview.vue keeps
 * all tiles in a single `.preview-floats` container and only mutates inline
 * styles to swap them between the rail and the stage.
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { GuestJoinResponse } from "@/api/types";

const props = defineProps<{
  sessionId: string;
  // "audience" tiles get a fake guest token threaded through the handshake.
  // The "presenter" tile inherits the user's existing localStorage-backed
  // auth (same-origin iframes share localStorage) so it gets a null guest.
  role: "audience" | "presenter";
  guest?: GuestJoinResponse | null;
  inspect?: boolean;
  label?: string;
}>();

const emit = defineEmits<{
  (e: "pick", payload: { selector: string; tag: string; classes: string[]; text: string }): void;
  (e: "slide-changed", slideId: string): void;
}>();

const iframeEl = ref<HTMLIFrameElement | null>(null);
const ready = ref(false);

const iframeSrc = () => {
  if (props.role === "presenter") return `/present/${props.sessionId}`;
  return `/audience/${props.sessionId}`;
};

function postAuth() {
  const w = iframeEl.value?.contentWindow;
  if (!w) return;
  w.postMessage(
    {
      slaides: true,
      type: "preview.auth",
      sessionId: props.sessionId,
      role: props.role,
      inspect: !!props.inspect,
      guest: props.guest ?? null,
    },
    window.location.origin,
  );
}

function onMessage(event: MessageEvent) {
  const data = event.data;
  if (!data || data.slaides !== true) return;
  if (event.source !== iframeEl.value?.contentWindow) return;
  if (data.type === "preview.ready" && data.sessionId === props.sessionId) {
    ready.value = true;
    postAuth();
    return;
  }
  if (data.type === "preview.pick" && data.payload) {
    emit("pick", data.payload);
    return;
  }
  if (data.type === "preview.slide-changed" && data.sessionId === props.sessionId && data.slideId) {
    emit("slide-changed", String(data.slideId));
  }
}

watch(
  () => props.inspect,
  () => {
    const w = iframeEl.value?.contentWindow;
    if (!w || !ready.value) return;
    w.postMessage(
      { slaides: true, type: "preview.inspect", on: !!props.inspect },
      window.location.origin,
    );
  },
);

onMounted(() => {
  window.addEventListener("message", onMessage);
});

onBeforeUnmount(() => {
  window.removeEventListener("message", onMessage);
});
</script>

<template>
  <div class="preview-tile">
    <iframe
      ref="iframeEl"
      :src="iframeSrc()"
      class="preview-tile-frame"
      :title="label || role"
    />
  </div>
</template>

<style scoped>
.preview-tile {
  width: 100%;
  height: 100%;
  background: var(--paper);
  overflow: hidden;
}

.preview-tile-frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
</style>
