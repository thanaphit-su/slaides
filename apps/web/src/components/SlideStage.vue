<script setup lang="ts">
import { computed, defineComponent, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { renderMarkdown } from "@/markdown/render";
import WidgetFrame from "@/widgets/WidgetFrame.vue";
import { useWidgetsStore } from "@/stores/widgets";
import Icon from "@/components/Icon.vue";
import InterpretPopover from "@/components/InterpretPopover.vue";
import type { Slide, SlideWidgetEmbed, Widget } from "@/api/types";

const props = withDefaults(
  defineProps<{
    slide: Slide | null;
    slim?: boolean;
    role?: "instructor" | "audience" | "preview";
    maxWidth?: number;
    /** Optional override for the kicker line. When omitted, falls back to `slide.kicker`. */
    kicker?: string | null;
    interpretEnabled?: boolean;
    interpretToken?: string | null;
    interpretContext?: Record<string, unknown>;
    /** Audience identity to bake into the widget iframe boot so quiz/poll
     * widgets can score by name without re-asking. Omit for presenter. */
    participant?: { display_name?: string | null; anon?: boolean };
  }>(),
  {
    slim: false,
    role: "audience",
    maxWidth: 1100,
    kicker: undefined,
    interpretEnabled: false,
    interpretToken: null,
    interpretContext: undefined,
    participant: undefined,
  },
);

const resolvedKicker = computed(() => (props.kicker !== undefined ? props.kicker : props.slide?.kicker ?? null));
const stageRoot = ref<HTMLElement | null>(null);
const interpretToolbar = ref<{ x: number; y: number; text: string } | null>(null);
const interpretPopover = ref<{ x: number; y: number; text: string; instruction: string } | null>(null);

const liveInterpretShortcuts = [
  { label: "AI", title: "Interpret with AI", instruction: "in plain English", icon: "widget" },
  { label: "Simple definition", title: "Show a simple definition", instruction: "show a simple definition", icon: "search" },
  { label: "Why it matters", title: "Explain why this matters", instruction: "explain why this matters for this slide", icon: "list" },
];

const emit = defineEmits<{
  (
    e: "widget-event",
    payload: { placement: SlideWidgetEmbed; type: string; payload: Record<string, unknown> },
  ): void;
}>();

const widgetsStore = useWidgetsStore();

onMounted(() => {
  document.addEventListener("selectionchange", onSelectionChange);
});

onBeforeUnmount(() => {
  document.removeEventListener("selectionchange", onSelectionChange);
});

watch(
  () => [props.slide?.id, props.interpretEnabled],
  () => {
    interpretToolbar.value = null;
    interpretPopover.value = null;
  },
);

function getWidget(id: string): Widget | null {
  return widgetsStore.cache[id] || null;
}

const Rendered = defineComponent({
  name: "RenderedSlide",
  setup() {
    return () => {
      if (!props.slide) return null;
      return renderMarkdown(props.slide.markdown, {
        slim: props.slim,
        widgets: props.slide.widgets,
        usePlacementRevision: true,
        getWidget,
        WidgetFrameComp: WidgetFrame as unknown as never,
        widgetRole: props.role,
        widgetParticipant: props.participant,
        onWidgetEvent: (placement, event) =>
          emit("widget-event", {
            placement,
            type: event.type,
            payload: event.payload,
          }),
      });
    };
  },
});

const containerStyle = computed(() => ({
  maxWidth: props.maxWidth + "px",
  margin: "0 auto",
  padding: props.slim
    ? "clamp(24px, 5vw, 56px) clamp(18px, 6vw, 64px) 88px"
    : "64px 64px 96px",
  width: "100%",
}));

function selectionWithinStage(range: Range): boolean {
  if (!stageRoot.value) return false;
  const container = range.commonAncestorContainer;
  return stageRoot.value === container || stageRoot.value.contains(container);
}

function onSelectionChange() {
  if (!props.interpretEnabled) {
    interpretToolbar.value = null;
    return;
  }
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
    interpretToolbar.value = null;
    return;
  }
  const range = sel.getRangeAt(0);
  if (!selectionWithinStage(range)) {
    interpretToolbar.value = null;
    return;
  }
  const text = sel.toString().trim();
  if (!text) {
    interpretToolbar.value = null;
    return;
  }
  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) {
    interpretToolbar.value = null;
    return;
  }
  interpretToolbar.value = {
    x: rect.left + rect.width / 2,
    y: rect.top,
    text,
  };
}

function openInterpret(instruction: string) {
  const current = interpretToolbar.value;
  if (!current) return;
  interpretPopover.value = {
    x: current.x - 190,
    y: current.y + 34,
    text: current.text,
    instruction,
  };
  interpretToolbar.value = null;
  document.getSelection()?.removeAllRanges();
}
</script>

<template>
  <div ref="stageRoot" :style="containerStyle">
    <template v-if="slide">
      <div v-if="resolvedKicker" class="t-kicker" :style="{ marginBottom: '14px' }">
        {{ resolvedKicker }}
      </div>
      <Rendered />
    </template>
    <div
      v-else
      :style="{
        textAlign: 'center',
        marginTop: '120px',
        color: 'var(--ink-soft)',
        fontFamily: 'var(--serif)',
        fontStyle: 'italic',
      }"
    >
      Waiting for the presenter…
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="interpretToolbar"
      class="live-interpret-toolbar scale-in"
      :style="{ left: interpretToolbar.x + 'px', top: Math.max(8, interpretToolbar.y - 48) + 'px' }"
      @mousedown.prevent
      @click.stop
    >
      <button
        v-for="shortcut in liveInterpretShortcuts"
        :key="shortcut.instruction"
        type="button"
        :title="shortcut.title"
        @click="openInterpret(shortcut.instruction)"
      >
        <Icon :name="shortcut.icon" :size="13" />
        {{ shortcut.label }}
      </button>
    </div>

    <InterpretPopover
      v-if="interpretPopover"
      :x="interpretPopover.x"
      :y="interpretPopover.y"
      :text="interpretPopover.text"
      :initial-instruction="interpretPopover.instruction"
      :allow-insert="false"
      :auth-token="props.interpretToken"
      :context="props.interpretContext"
      @close="interpretPopover = null"
    />
  </Teleport>
</template>

<style scoped>
.live-interpret-toolbar {
  position: fixed;
  transform: translateX(-50%);
  z-index: 90;
  background: var(--ink);
  color: var(--paper);
  border-radius: var(--r-md);
  padding: 4px;
  box-shadow: var(--shadow-3);
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-family: var(--sans);
  font-size: 12px;
  max-width: calc(100vw - 16px);
  overflow-x: auto;
}

.live-interpret-toolbar button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  background: transparent;
  border: none;
  color: var(--paper);
  padding: 7px 9px;
  border-radius: var(--r-sm);
  min-height: 30px;
  font-family: var(--sans);
  font-size: 12px;
}

.live-interpret-toolbar button:hover {
  background: rgba(255, 255, 255, .12);
}

@media (max-width: 560px) {
  .live-interpret-toolbar {
    left: 8px !important;
    right: 8px;
    transform: none;
  }

  .live-interpret-toolbar button {
    flex: 1 0 auto;
    justify-content: center;
  }
}
</style>
