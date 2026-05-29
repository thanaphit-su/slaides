<script setup lang="ts">
import { computed, inject, type Ref } from "vue";
import { NodeViewWrapper, nodeViewProps } from "@tiptap/vue-3";
import WidgetBlock from "@/components/WidgetBlock.vue";
import { WIDGET_CONTEXT, type WidgetContext } from "./widget-context";

// Bridges a TipTap `widget` node to the existing WidgetBlock.vue. The node only
// stores `placementId`; everything live (placement, resolved widget, callbacks)
// comes from the reactive runtime context.
const props = defineProps(nodeViewProps);

const fallback: WidgetContext = { placements: [], rev: 0, fill: false };

// Primary source: the context passed through the node's extension options
// (always present synchronously). Fallback: Vue inject, kept for resilience.
const injected = inject(WIDGET_CONTEXT, undefined);
const optionCtx = (props.extension.options as { context?: Ref<WidgetContext> | null }).context ?? null;
const ctx = computed<WidgetContext>(() => optionCtx?.value ?? injected?.value ?? fallback);

const placementId = computed(() => String(props.node.attrs.placementId || ""));

const placement = computed(
  () => ctx.value.placements.find((p) => p.placement_id === placementId.value) ?? null,
);

const widget = computed(() => {
  const p = placement.value;
  // Touch `rev` so the resolver (an opaque call into the store cache, not a
  // tracked dep) is re-read whenever the parent signals a widget-data change —
  // defensive even if the context object identity already changed.
  void ctx.value.rev;
  return p && ctx.value.getWidget ? ctx.value.getWidget(p.widget_id) : null;
});

const fill = computed(() => ctx.value.fill);

// `rev` participates in the key so the iframe remounts when the widget body
// changes out of band (AI apply / props reset), but not on routine autosave.
const frameKey = computed(() => {
  const p = placement.value;
  return `${placementId.value}-${p?.widget_id ?? "x"}-${p?.revision_id ?? "x"}-${ctx.value.rev}`;
});

function onAdjust() {
  if (placement.value) ctx.value.onAdjust?.(placement.value);
}
function onRemove() {
  if (placement.value) ctx.value.onRemove?.(placement.value);
}
</script>

<template>
  <NodeViewWrapper
    class="widget-node-view"
    contenteditable="false"
    :data-widget-id="placementId"
  >
    <WidgetBlock
      :key="frameKey"
      :placement-id="placementId"
      :placement="placement"
      :widget="widget"
      :fill="fill"
      :on-adjust="onAdjust"
      :on-remove="onRemove"
    />
  </NodeViewWrapper>
</template>

<style scoped>
.widget-node-view {
  /* The wrapper is non-editable; spacing/visuals live in WidgetBlock. */
  user-select: none;
}
</style>
