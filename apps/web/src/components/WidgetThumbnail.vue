<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/Icon.vue";
import WidgetFrame from "@/widgets/WidgetFrame.vue";
import type { Widget } from "@/api/types";

const props = defineProps<{
  widget: Widget;
  /** Current deck id — used to mark cross-deck widgets in the dataTransfer
   * payload so the drop handler knows whether to copy before attaching. */
  currentDeckId: string | null;
}>();

const emit = defineEmits<{
  (e: "delete", widget: Widget): void;
}>();

const isCrossDeck = computed(() => !!props.currentDeckId && props.widget.deck_id !== props.currentDeckId);
const behaviorKind = computed(() => (props.widget.behavior as { kind?: string } | undefined)?.kind ?? "quiet");
const exampleProps = computed(() => props.widget.example_props || {});

function onDragStart(e: DragEvent) {
  if (!e.dataTransfer) return;
  e.dataTransfer.effectAllowed = "copy";
  e.dataTransfer.setData(
    "application/x-slaides-widget",
    JSON.stringify({ widget_id: props.widget.id, deck_id: props.widget.deck_id }),
  );
}

function onDeleteClick(e: MouseEvent) {
  e.stopPropagation();
  emit("delete", props.widget);
}
</script>

<template>
  <div
    class="widget-thumbnail"
    data-testid="widget-thumbnail"
    :draggable="true"
    @dragstart="onDragStart"
    :title="`Drag onto a slide to insert${isCrossDeck ? ' (copies into this deck)' : ''}`"
  >
    <div class="widget-thumbnail-frame-wrap">
      <WidgetFrame
        class="widget-thumbnail-frame"
        :widget="widget"
        :placement-id="`thumbnail-${widget.id}`"
        :boot-props="exampleProps"
        role="thumbnail"
        :fill="true"
        :min-height="240"
      />
    </div>
    <div class="widget-thumbnail-meta">
      <span class="widget-thumbnail-name">{{ widget.name }}</span>
      <span class="widget-thumbnail-badges">
        <span class="t-mono widget-thumbnail-kind">{{ widget.kind }}</span>
        <span
          class="widget-thumbnail-dot"
          :class="behaviorKind === 'loud' ? 'is-loud' : 'is-quiet'"
          :title="behaviorKind === 'loud' ? 'Loud — shared across the room' : 'Quiet — private per viewer'"
        >{{ behaviorKind === "loud" ? "●" : "○" }}</span>
      </span>
    </div>
    <span
      v-if="isCrossDeck"
      class="widget-thumbnail-crossdeck"
      title="From another deck — drop will copy into this deck"
    >OTHER DECK</span>
    <button
      type="button"
      class="widget-thumbnail-delete"
      data-testid="widget-thumbnail-delete"
      :draggable="false"
      :title="`Delete ${widget.name}`"
      :aria-label="`Delete ${widget.name}`"
      @click="onDeleteClick"
      @mousedown.stop
      @dragstart.stop.prevent
    >
      <Icon name="trash" :size="12" />
    </button>
  </div>
</template>

<style scoped>
.widget-thumbnail {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  overflow: hidden;
  cursor: grab;
  transition: border-color 120ms ease, transform 120ms ease;
}

.widget-thumbnail:hover {
  border-color: var(--ink);
}

.widget-thumbnail:active {
  cursor: grabbing;
}

.widget-thumbnail-frame-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  background: var(--paper-2);
  overflow: hidden;
}

.widget-thumbnail-frame {
  position: absolute;
  inset: 0;
  /* The iframe must not capture pointer events or the drag won't start
   * from a click that lands on the preview. */
  pointer-events: none;
  transform: scale(0.6);
  transform-origin: top left;
  width: 166.67%;
  height: 166.67%;
}

.widget-thumbnail-frame :deep(iframe) {
  pointer-events: none;
}

.widget-thumbnail-meta {
  padding: 6px 8px;
  border-top: 1px solid var(--rule-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}

.widget-thumbnail-name {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.widget-thumbnail-badges {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.widget-thumbnail-kind {
  font-size: 9px;
  color: var(--ink-mute);
  letter-spacing: 0.05em;
}

.widget-thumbnail-dot {
  font-size: 8px;
  line-height: 1;
}

.widget-thumbnail-dot.is-loud {
  color: var(--accent, #c45a3b);
}

.widget-thumbnail-dot.is-quiet {
  color: var(--ink-mute);
}

.widget-thumbnail-crossdeck {
  position: absolute;
  top: 6px;
  right: 6px;
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  padding: 3px 6px;
  border-radius: var(--r-sm);
  background: var(--ink);
  color: var(--paper);
  pointer-events: none;
}

.widget-thumbnail-delete {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper);
  color: var(--ink-soft);
  cursor: pointer;
  opacity: 0;
  transition: opacity 120ms ease, color 120ms ease, border-color 120ms ease;
}

.widget-thumbnail:hover .widget-thumbnail-delete,
.widget-thumbnail-delete:focus-visible {
  opacity: 1;
}

.widget-thumbnail-delete:hover {
  color: var(--err);
  border-color: var(--err);
}
</style>
