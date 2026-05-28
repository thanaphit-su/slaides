<script setup lang="ts">
import { h, onBeforeUnmount, onMounted, render, watch, ref, nextTick } from "vue";
import { renderMarkdown, serialiseContentEditable } from "@/markdown/render";
import WidgetFrame from "@/widgets/WidgetFrame.vue";
import type { SlideWidgetEmbed, Widget } from "@/api/types";
import Icon from "@/components/Icon.vue";

const props = defineProps<{
  markdown: string;
  slideId: string;
  widgets?: SlideWidgetEmbed[];
  /** Bumped by the parent when an AI-applied edit (or other out-of-band
   * mutation) changes the cached widget body — forces a fresh paint so the
   * iframe srcdoc rebuilds with the new HTML/JS/CSS. */
  widgetRev?: number;
  getWidget?: (id: string) => Widget | null;
  onAdjust?: (placement: SlideWidgetEmbed) => void;
  onRemove?: (placement: SlideWidgetEmbed) => void;
}>();
const emit = defineEmits<{
  (e: "update", markdown: string): void;
  (e: "interpret", payload: { x: number; y: number; text: string }): void;
  (e: "context-menu", payload: { x: number; y: number; selection: string }): void;
  (e: "focus-change", focused: boolean): void;
}>();

const root = ref<HTMLElement | null>(null);
const toolbar = ref<{ x: number; y: number; text: string } | null>(null);
let lastEmittedMarkdown: string | null = null;
type BlockKind = "h1" | "h2" | "h3" | "p" | "quote" | "rule" | "list";

function paint(md: string) {
  if (!root.value) return;
  const wrapper = h(
    "div",
    {},
    renderMarkdown(md, {
      widgets: props.widgets,
      usePlacementRevision: true,
      getWidget: props.getWidget,
      WidgetFrameComp: WidgetFrame,
      onAdjust: props.onAdjust,
      onRemove: props.onRemove,
    }),
  );
  render(null, root.value);
  render(wrapper, root.value);
}

function onInput() {
  const inner = editorInner();
  if (!inner) return;
  normaliseBlockAttrs(inner);
  promoteMarkdownHeadingShortcut(inner);
  const md = serialiseContentEditable(inner);
  lastEmittedMarkdown = md;
  emit("update", md);
}

function editorInner(): HTMLElement | null {
  return (root.value?.firstElementChild as HTMLElement | null) || null;
}

onMounted(async () => {
  paint(props.markdown);
  await nextTick();
  document.addEventListener("selectionchange", onSelectionChange);
});
onBeforeUnmount(() => document.removeEventListener("selectionchange", onSelectionChange));

// Re-paint when slide changes (different slide id) or when the widget placement
// list/cache changes (e.g. widget data finished loading, or props were updated).
watch(
  () => props.slideId,
  async () => {
    paint(props.markdown);
    await nextTick();
  },
);
watch(
  () => props.widgets,
  async () => {
    paint(props.markdown);
    await nextTick();
  },
  { deep: true },
);
watch(
  () => props.widgetRev,
  async () => {
    paint(props.markdown);
    await nextTick();
  },
);
// Repaint when the markdown changes from outside the canvas (modal save,
// AI-applied edits, etc.) — but NOT when the change came from our own
// onInput emit (which would stomp the caret during normal typing).
watch(
  () => props.markdown,
  async (md) => {
    if (md === lastEmittedMarkdown) return;
    paint(md);
    await nextTick();
  },
);

function selectionWithinRoot(range: Range): boolean {
  if (!root.value) return false;
  const container = range.commonAncestorContainer;
  return root.value === container || root.value.contains(container);
}

function onSelectionChange() {
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
    toolbar.value = null;
    return;
  }
  const range = sel.getRangeAt(0);
  if (!selectionWithinRoot(range)) {
    toolbar.value = null;
    return;
  }
  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) {
    toolbar.value = null;
    return;
  }
  toolbar.value = {
    x: rect.left + rect.width / 2,
    y: rect.top,
    text: sel.toString(),
  };
}

function normaliseBlockAttrs(inner: HTMLElement) {
  for (const child of Array.from(inner.children)) {
    const el = child as HTMLElement;
    if (el.getAttribute("data-block") === "widget") continue;
    const tag = el.tagName.toLowerCase();
    if (tag === "h1") applyBlockPresentation(el, "h1");
    else if (tag === "h2") applyBlockPresentation(el, "h2");
    else if (tag === "h3") applyBlockPresentation(el, "h3");
    else if (tag === "blockquote") applyBlockPresentation(el, "quote");
    else if (tag === "hr") applyBlockPresentation(el, "rule");
    else if (tag === "ul" || tag === "ol") applyBlockPresentation(el, "list");
    else applyBlockPresentation(el, "p");
  }
}

function applyBlockPresentation(el: HTMLElement, kind: BlockKind) {
  el.setAttribute("data-block", kind);
  el.className = "";
  el.removeAttribute("style");
  if (kind === "h1") {
    el.className = "t-display";
    el.style.margin = "0 0 18px";
  } else if (kind === "h2") {
    el.className = "t-h2";
    el.style.margin = "24px 0 12px";
  } else if (kind === "h3") {
    el.className = "t-h3";
    el.style.margin = "24px 0 10px";
  } else if (kind === "p") {
    el.className = "t-body";
    el.style.margin = "0 0 18px";
    el.style.color = "var(--ink)";
  } else if (kind === "quote") {
    el.style.margin = "18px 0";
    el.style.paddingLeft = "18px";
    el.style.borderLeft = "2px solid var(--accent)";
    el.style.fontFamily = "var(--serif)";
    el.style.fontStyle = "italic";
    el.style.fontSize = "22px";
    el.style.color = "var(--ink-soft)";
    el.style.lineHeight = "1.55";
  } else if (kind === "rule") {
    el.style.border = "none";
    el.style.borderTop = "1px solid var(--ink)";
    el.style.width = "48px";
    el.style.margin = "24px 0";
  } else if (kind === "list") {
    el.className = "t-body";
    el.setAttribute("data-ordered", el.tagName.toLowerCase() === "ol" ? "true" : "false");
    el.style.margin = "0 0 18px";
    el.style.paddingLeft = "28px";
    el.style.color = "var(--ink)";
  }
}

function selectedTopLevelBlock(inner: HTMLElement): HTMLElement | null {
  const sel = document.getSelection();
  if (!sel || !sel.rangeCount) return null;
  let node: Node | null = sel.anchorNode;
  while (node && node !== inner) {
    if (node.parentNode === inner && node instanceof HTMLElement) return node;
    node = node.parentNode;
  }
  return null;
}

function caretOffsetWithin(el: HTMLElement): number {
  const sel = document.getSelection();
  if (!sel || !sel.rangeCount) return 0;
  const range = sel.getRangeAt(0).cloneRange();
  range.selectNodeContents(el);
  range.setEnd(sel.anchorNode || el, sel.anchorOffset);
  return range.toString().length;
}

function setCaretOffset(el: HTMLElement, offset: number) {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let remaining = offset;
  let textNode = walker.nextNode() as Text | null;
  while (textNode) {
    if (remaining <= textNode.data.length) {
      const range = document.createRange();
      range.setStart(textNode, remaining);
      range.collapse(true);
      const sel = document.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      return;
    }
    remaining -= textNode.data.length;
    textNode = walker.nextNode() as Text | null;
  }
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = document.getSelection();
  sel?.removeAllRanges();
  sel?.addRange(range);
}

function promoteMarkdownHeadingShortcut(inner: HTMLElement) {
  const block = selectedTopLevelBlock(inner);
  if (!block || block.getAttribute("data-block") === "widget") return;
  const text = block.textContent || "";
  const match = text.match(/^(#{1,3})\s/);
  if (!match) return;

  const kind = match[1].length === 1 ? "h1" : match[1].length === 2 ? "h2" : "h3";
  const tag = kind;
  const caret = caretOffsetWithin(block);
  const replacement = document.createElement(tag);
  replacement.textContent = text.slice(match[0].length);
  applyBlockPresentation(replacement, kind);
  block.replaceWith(replacement);
  setCaretOffset(replacement, Math.max(0, caret - match[0].length));
}

function syncAfterNativeEdit() {
  window.setTimeout(() => {
    onInput();
    onSelectionChange();
  }, 0);
}

function paragraphHtml() {
  return '<p data-block="p" class="t-body" style="margin: 0 0 18px; color: var(--ink);"><br></p>';
}

function onKeydown(e: KeyboardEvent) {
  const key = e.key.toLowerCase();
  if ((e.metaKey || e.ctrlKey) && key === "z") {
    syncAfterNativeEdit();
    return;
  }

  if (e.key !== "Enter" || e.shiftKey) return;
  const inner = editorInner();
  if (!inner) return;
  const block = selectedTopLevelBlock(inner);
  if (!block) {
    syncAfterNativeEdit();
    return;
  }

  const kind = block.getAttribute("data-block");
  if ((kind === "h1" || kind === "h2" || kind === "h3") && caretOffsetWithin(block) === 0) {
    e.preventDefault();
    document.execCommand("insertHTML", false, paragraphHtml());
    syncAfterNativeEdit();
    return;
  }

  syncAfterNativeEdit();
}

function syncAfterCommand() {
  nextTick(() => {
    onInput();
    onSelectionChange();
  });
}

function exec(cmd: string, value?: string) {
  document.execCommand(cmd, false, value);
  root.value?.focus();
  syncAfterCommand();
}

function formatBlock(tag: "h1" | "h2" | "p" | "blockquote") {
  document.execCommand("formatBlock", false, tag);
  syncAfterCommand();
}

function applyInlineCode() {
  const sel = document.getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return;
  const range = sel.getRangeAt(0);
  const code = document.createElement("code");
  code.textContent = range.toString();
  code.style.fontFamily = "var(--mono)";
  code.style.fontSize = ".92em";
  code.style.background = "var(--paper-2)";
  code.style.padding = "1px 6px";
  code.style.borderRadius = "4px";
  range.deleteContents();
  range.insertNode(code);
  sel.removeAllRanges();
  syncAfterCommand();
}

function applyLink() {
  const url = window.prompt("Link URL", "https://");
  if (url) exec("createLink", url);
}

function interpretSelection() {
  if (!toolbar.value) return;
  const sel = document.getSelection();
  const text = toolbar.value.text;
  const x = toolbar.value.x - 190;
  const y = toolbar.value.y + 34;
  sel?.removeAllRanges();
  toolbar.value = null;
  emit("interpret", { x, y, text });
}

function onContextMenu(e: MouseEvent) {
  e.preventDefault();
  const sel = document.getSelection();
  let text = "";
  if (sel && sel.rangeCount && selectionWithinRoot(sel.getRangeAt(0))) {
    text = sel.toString();
  }
  emit("context-menu", { x: e.clientX, y: e.clientY, selection: text });
}

function focusCanvas(where: "start" | "end" = "end") {
  const el = root.value;
  if (!el) return;
  el.focus();
  const sel = window.getSelection();
  if (!sel) return;
  const range = document.createRange();
  if (where === "end") {
    range.selectNodeContents(el);
    range.collapse(false);
  } else {
    range.setStart(el, 0);
    range.collapse(true);
  }
  sel.removeAllRanges();
  sel.addRange(range);
}

defineExpose({ focus: focusCanvas });
</script>

<template>
  <div>
    <div
      v-if="toolbar"
      class="wys-toolbar scale-in"
      :style="{ left: toolbar.x + 'px', top: Math.max(8, toolbar.y - 48) + 'px' }"
      contenteditable="false"
      @mousedown.prevent
    >
      <button @click="exec('bold')" style="font-weight: 700">B</button>
      <button @click="exec('italic')" style="font-style: italic">I</button>
      <button @click="exec('underline')" style="text-decoration: underline">U</button>
      <span />
      <button @click="formatBlock('h1')">H1</button>
      <button @click="formatBlock('h2')">H2</button>
      <button @click="formatBlock('p')">P</button>
      <button @click="formatBlock('blockquote')">“”</button>
      <span />
      <button @click="applyInlineCode">`</button>
      <button @click="applyLink">Link</button>
      <span />
      <button class="accent" @click="interpretSelection"><Icon name="astroid" :strokeWidth="2"/></button>
    </div>
    <div
      ref="root"
      class="slaides-canvas"
      contenteditable="true"
      spellcheck="false"
      @input="onInput"
      @keydown="onKeydown"
      @contextmenu="onContextMenu"
      @focus="emit('focus-change', true)"
      @blur="emit('focus-change', false)"
      :style="{
        outline: 'none',
      }"
    />
  </div>
</template>

<style>
.slaides-canvas:focus {
  outline: none;
}
.slaides-canvas [data-block='widget'] {
  caret-color: transparent;
}

.slaides-canvas [data-block='widget']:hover .widget-action-chrome,
.slaides-canvas [data-block='widget']:focus-within .widget-action-chrome {
  opacity: 1 !important;
}

.wys-toolbar {
  position: fixed;
  transform: translateX(-50%);
  z-index: 70;
  background: var(--ink);
  color: var(--paper);
  border-radius: var(--r-md);
  padding: 4px;
  box-shadow: var(--shadow-3);
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-family: var(--sans);
  font-size: 13px;
}

.wys-toolbar button {
  background: transparent;
  border: none;
  color: var(--paper);
  padding: 6px 8px;
  border-radius: var(--r-sm);
  min-width: 28px;
  font-family: var(--sans);
  font-size: 13px;
}

.wys-toolbar button:hover {
  background: rgba(255,255,255,.12);
}

.wys-toolbar button.accent {
  color: #8bb0ff;
  font-weight: 700;
}

.wys-toolbar > span {
  width: 1px;
  height: 18px;
  background: rgba(255,255,255,.18);
  margin: 0 2px;
}
</style>
