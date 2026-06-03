<script setup lang="ts">
import WidgetFrame from "@/widgets/WidgetFrame.vue";
import type { SlideWidgetEmbed, Widget } from "@/api/types";

// A single widget placement rendered in the editor canvas. It lives as a
// sibling OUTSIDE any contenteditable region, so a stray keystroke can never
// delete it (removal goes through the Remove chrome → `onRemove`). The body
// renders the *current* widget (passed in via `widget`), matching the old
// `renderWidgetBlock` with `usePlacementRevision: false`.
const props = defineProps<{
  placementId: string;
  placement: SlideWidgetEmbed | null;
  widget: Widget | null;
  /** True when the widget is the slide's only block — fill the canvas. */
  fill?: boolean;
  onAdjust?: (placement: SlideWidgetEmbed) => void;
  onRemove?: (placement: SlideWidgetEmbed) => void;
}>();

const ADJUST_PATH = "M4 16l1-3 8-8 3 3-8 8-3 1z";
const REMOVE_PATH = "M5 6h10M8 6V4h4v2M6.5 6l.7 10.2c0 .5.4.8.8.8h4c.4 0 .8-.3.8-.8L13.5 6";

function onAdjustClick() {
  if (props.placement) props.onAdjust?.(props.placement);
}
function onRemoveClick() {
  if (props.placement) props.onRemove?.(props.placement);
}
</script>

<template>
  <div
    class="widget-block"
    contenteditable="false"
    data-block="widget"
    :data-widget-id="placementId"
  >
    <div class="widget-block-chrome">
      <span class="t-mono-up widget-block-label">
        {{ placement ? `WIDGET · ${placement.kind} · #${placementId}` : `WIDGET · #${placementId}` }}
      </span>
    </div>

    <div v-if="placement && (onAdjust || onRemove)" class="widget-action-chrome">
      <button
        v-if="onAdjust"
        class="btn btn-sm widget-icon-btn"
        type="button"
        title="Adjust widget"
        aria-label="Adjust widget"
        @click.prevent.stop="onAdjustClick"
        @mousedown.prevent
      >
        <svg
          width="14" height="14" viewBox="0 0 20 20" fill="none"
          stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path :d="ADJUST_PATH" />
        </svg>
      </button>
      <button
        v-if="onRemove"
        class="btn btn-sm widget-icon-btn widget-icon-danger"
        type="button"
        title="Remove widget"
        aria-label="Remove widget"
        @click.prevent.stop="onRemoveClick"
        @mousedown.prevent
      >
        <svg
          width="14" height="14" viewBox="0 0 20 20" fill="none"
          stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path :d="REMOVE_PATH" />
        </svg>
      </button>
    </div>

    <WidgetFrame
      v-if="widget"
      :widget="widget"
      :placement-id="placementId"
      :boot-props="placement?.props || {}"
      role="instructor"
      :fill="!!fill"
      :min-height="fill ? 560 : 80"
    />
    <div v-else-if="placement" class="widget-block-skeleton" role="status" aria-live="polite">
      <span class="widget-block-loading-text">Loading widget</span>
      <div class="widget-block-skeleton-head" aria-hidden="true" />
      <div class="widget-block-skeleton-line widget-block-skeleton-line-main" aria-hidden="true" />
      <div class="widget-block-skeleton-line" aria-hidden="true" />
      <div class="widget-block-skeleton-action" aria-hidden="true" />
    </div>
    <div v-else class="widget-block-stub">
      {{ `WIDGET · #${placementId}` }}
    </div>
  </div>
</template>

<style scoped>
.widget-block {
  position: relative;
  margin: 32px 0;
  user-select: none;
  caret-color: transparent;
}

.widget-block-chrome {
  position: absolute;
  top: -20px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: flex-start;
  align-items: center;
  pointer-events: none;
  z-index: 1;
}

.widget-block-label {
  pointer-events: auto;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-soft);
}

.widget-action-chrome {
  position: absolute;
  right: 0;
  bottom: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  pointer-events: auto;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.widget-block:hover .widget-action-chrome,
.widget-block:focus-within .widget-action-chrome {
  opacity: 1;
}

.widget-icon-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--paper);
  line-height: 0;
}

.widget-icon-danger {
  border-color: var(--err);
  color: var(--err);
}

.widget-block-stub {
  padding: 28px 24px;
  border: 1px dashed var(--rule-strong);
  border-radius: var(--r-lg);
  background: var(--paper-2);
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-soft);
  letter-spacing: 0.04em;
  text-align: center;
}

.widget-block-skeleton {
  position: relative;
  min-height: 112px;
  padding: 20px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  overflow: hidden;
}

.widget-block-loading-text {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.widget-block-skeleton-head,
.widget-block-skeleton-line,
.widget-block-skeleton-action {
  position: relative;
  z-index: 1;
  display: block;
  border-radius: var(--r-sm);
  background: color-mix(in srgb, var(--ink-soft) 11%, var(--paper));
}

.widget-block-skeleton-head {
  width: 76px;
  height: 8px;
  margin-bottom: 20px;
}

.widget-block-skeleton-line {
  width: 52%;
  height: 10px;
  margin-top: 10px;
}

.widget-block-skeleton-line-main {
  width: 68%;
  height: 16px;
}

.widget-block-skeleton-action {
  width: 116px;
  height: 28px;
  margin-top: 20px;
}
</style>
