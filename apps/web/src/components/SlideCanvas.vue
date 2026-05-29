<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, shallowRef, watch } from "vue";
import { Editor, EditorContent } from "@tiptap/vue-3";
import StarterKit from "@tiptap/starter-kit";
import { Heading } from "@tiptap/extension-heading";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import Icon from "@/components/Icon.vue";
import { WidgetNode } from "@/components/editor/widget-node";
import { WIDGET_CONTEXT, type WidgetContext } from "@/components/editor/widget-context";
import { docToMarkdown, markdownToDoc } from "@/markdown/tiptap-doc";
import { parseBlocks } from "@/markdown/render";
import type { SlideWidgetEmbed, Widget } from "@/api/types";

const props = defineProps<{
  markdown: string;
  slideId: string;
  widgets?: SlideWidgetEmbed[];
  /** Bumped by the parent to force a widget iframe to remount (AI Adjust apply
   * or props save). Flows through the injected widget context → only widget
   * node views react; the editable text is untouched, so the caret survives. */
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

const editor = shallowRef<Editor | null>(null);
const toolbar = ref<{ x: number; y: number; text: string } | null>(null);
let lastEmittedMarkdown: string | null = null;

/* --------------- runtime widget context provided to node views ----------- */

// A single widget block fills the canvas (matches the old `isFill`).
const isFill = computed(() => {
  const blocks = parseBlocks(props.markdown);
  return blocks.length === 1 && blocks[0]?.type === "widget";
});

const widgetContext = ref<WidgetContext>({
  placements: props.widgets ?? [],
  getWidget: props.getWidget,
  onAdjust: props.onAdjust,
  onRemove: props.onRemove,
  rev: props.widgetRev ?? 0,
  fill: isFill.value,
});
provide(WIDGET_CONTEXT, widgetContext);

// Keep the context in sync with props. This intentionally does NOT touch the
// editor document — widget node views read it reactively, so a new widgets
// array (e.g. from an autosave that replaced the slide object) repaints only
// the widget node, never the focused text around it.
watch(
  () => [props.widgets, props.getWidget, props.onAdjust, props.onRemove, props.widgetRev, isFill.value] as const,
  () => {
    widgetContext.value = {
      placements: props.widgets ?? [],
      getWidget: props.getWidget,
      onAdjust: props.onAdjust,
      onRemove: props.onRemove,
      rev: props.widgetRev ?? 0,
      fill: isFill.value,
    };
  },
  { deep: true },
);

/* ------------------------------- editor ---------------------------------- */

onMounted(() => {
  editor.value = new Editor({
    content: markdownToDoc(props.markdown),
    extensions: [
      StarterKit.configure({
        // Use our own heading (below) so each level carries the same global
        // type token class the live session renders with (single source of
        // truth in theme/tokens.css). Everything else stays default.
        heading: false,
        link: { openOnClick: false, autolink: false },
        // Paragraphs and lists inherit the session's body type.
        paragraph: { HTMLAttributes: { class: "t-body" } },
        bulletList: { HTMLAttributes: { class: "t-body" } },
        orderedList: { HTMLAttributes: { class: "t-body" } },
      }),
      // h1 → .t-display, h2 → .t-h2, h3 → .t-h3 — identical to renderBlock() so
      // the editor and the live session render the exact same typography.
      Heading.extend({
        renderHTML({ node, HTMLAttributes }) {
          const level: number = node.attrs.level;
          const cls = level === 1 ? "t-display" : level === 2 ? "t-h2" : "t-h3";
          return [
            `h${level}`,
            { ...HTMLAttributes, class: cls },
            0,
          ];
        },
      }).configure({ levels: [1, 2, 3] }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      // Deliver the reactive widget context through the node's options so the
      // NodeView gets it synchronously (no inject mount-order race). `provide`
      // above is kept as a secondary fallback.
      WidgetNode.configure({ context: widgetContext }),
    ],
    editorProps: {
      attributes: { class: "slaides-canvas", spellcheck: "false" },
    },
    onUpdate: ({ editor: ed }) => {
      const md = docToMarkdown(ed.getJSON() as Parameters<typeof docToMarkdown>[0]);
      lastEmittedMarkdown = md;
      emit("update", md);
    },
    onFocus: () => emit("focus-change", true),
    onBlur: () => emit("focus-change", false),
    onSelectionUpdate: refreshToolbar,
  });
  document.addEventListener("selectionchange", refreshToolbar);
});

onBeforeUnmount(() => {
  document.removeEventListener("selectionchange", refreshToolbar);
  editor.value?.destroy();
  editor.value = null;
});

// External markdown change (AI apply, modal save, autosave round-trip) →
// rebuild the doc, but NOT when it's the echo of our own edit (that would
// reset the document and drop the caret mid-typing).
watch(
  () => props.markdown,
  (md) => {
    if (!editor.value) return;
    if (md === lastEmittedMarkdown) return;
    editor.value.commands.setContent(markdownToDoc(md), { emitUpdate: false });
  },
);

// New slide → reset content and clear the echo guard.
watch(
  () => props.slideId,
  () => {
    if (!editor.value) return;
    lastEmittedMarkdown = null;
    editor.value.commands.setContent(markdownToDoc(props.markdown), { emitUpdate: false });
  },
);

/* ------------------------------- toolbar --------------------------------- */

function refreshToolbar() {
  const ed = editor.value;
  if (!ed || !ed.isFocused) {
    toolbar.value = null;
    return;
  }
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
    toolbar.value = null;
    return;
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  if (!rect.width && !rect.height) {
    toolbar.value = null;
    return;
  }
  toolbar.value = { x: rect.left + rect.width / 2, y: rect.top, text: sel.toString() };
}

function chain() {
  return editor.value?.chain().focus();
}

function toggleBold() {
  chain()?.toggleBold().run();
}
function toggleItalic() {
  chain()?.toggleItalic().run();
}
function toggleUnderline() {
  chain()?.toggleUnderline().run();
}
function toggleCode() {
  chain()?.toggleCode().run();
}
function setHeading(level: 1 | 2) {
  chain()?.toggleHeading({ level }).run();
}
function setParagraph() {
  chain()?.setParagraph().run();
}
function toggleQuote() {
  chain()?.toggleBlockquote().run();
}
function applyLink() {
  const url = window.prompt("Link URL", "https://");
  if (url == null) return;
  if (url === "") {
    chain()?.unsetLink().run();
    return;
  }
  chain()?.setLink({ href: url }).run();
}

function interpretSelection() {
  if (!toolbar.value) return;
  const text = toolbar.value.text;
  const x = toolbar.value.x - 190;
  const y = toolbar.value.y + 34;
  toolbar.value = null;
  emit("interpret", { x, y, text });
}

function onContextMenu(e: MouseEvent) {
  e.preventDefault();
  const sel = document.getSelection();
  let text = "";
  if (sel && sel.rangeCount && !sel.isCollapsed) text = sel.toString();
  emit("context-menu", { x: e.clientX, y: e.clientY, selection: text });
}

/* -------------------------------- expose --------------------------------- */

function focus(where: "start" | "end" = "end") {
  editor.value?.commands.focus(where);
}

defineExpose({ focus });
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
      <button :class="{ on: editor?.isActive('bold') }" @click="toggleBold" style="font-weight: 700">B</button>
      <button :class="{ on: editor?.isActive('italic') }" @click="toggleItalic" style="font-style: italic">I</button>
      <button :class="{ on: editor?.isActive('underline') }" @click="toggleUnderline" style="text-decoration: underline">U</button>
      <span />
      <button :class="{ on: editor?.isActive('heading', { level: 1 }) }" @click="setHeading(1)">H1</button>
      <button :class="{ on: editor?.isActive('heading', { level: 2 }) }" @click="setHeading(2)">H2</button>
      <button :class="{ on: editor?.isActive('paragraph') }" @click="setParagraph">P</button>
      <button :class="{ on: editor?.isActive('blockquote') }" @click="toggleQuote">“”</button>
      <span />
      <button :class="{ on: editor?.isActive('code') }" @click="toggleCode">`</button>
      <button :class="{ on: editor?.isActive('link') }" @click="applyLink">Link</button>
      <span />
      <button class="accent" @click="interpretSelection"><Icon name="astroid" :strokeWidth="2" /></button>
    </div>

    <EditorContent v-if="editor" :editor="editor" @contextmenu="onContextMenu" />
  </div>
</template>

<style>
/* ----- TipTap content styled with Slaides tokens (no Tailwind) ----- */
.slaides-canvas {
  outline: none;
}
.slaides-canvas:focus,
.slaides-canvas:focus-visible {
  outline: none;
}

/* Font family / size / weight come from the shared type-token classes
   (.t-display, .t-h2, .t-h3, .t-body) applied to the nodes themselves, so the
   editor and the live session (which render through the same tokens.css) stay
   identical. Only block spacing + colour live here, matching renderBlock(). */
.slaides-canvas h1 {
  margin: 0 0 18px;
}
.slaides-canvas h2 {
  margin: 24px 0 12px;
}
.slaides-canvas h3 {
  margin: 24px 0 10px;
}
.slaides-canvas p {
  margin: 0 0 18px;
  color: var(--ink);
}
.slaides-canvas blockquote {
  margin: 18px 0;
  padding-left: 18px;
  border-left: 2px solid var(--accent);
  font-family: var(--serif);
  font-style: italic;
  font-size: 22px;
  color: var(--ink-soft);
  line-height: 1.55;
}
.slaides-canvas blockquote p {
  font-size: inherit;
  font-style: inherit;
  margin: 0;
}
.slaides-canvas ul,
.slaides-canvas ol {
  margin: 0 0 18px;
  padding-left: 28px;
  color: var(--ink);
}
.slaides-canvas hr {
  border: none;
  border-top: 1px solid var(--ink);
  width: 48px;
  margin: 24px 0;
}
.slaides-canvas code {
  font-family: var(--mono);
  font-size: 0.92em;
  background: var(--paper-2);
  padding: 1px 6px;
  border-radius: 4px;
}
.slaides-canvas a {
  color: var(--accent);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
.slaides-canvas table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 22px;
  color: var(--ink);
}
.slaides-canvas th,
.slaides-canvas td {
  border: 1px solid var(--rule);
  padding: 9px 12px;
  vertical-align: top;
  text-align: left;
}
.slaides-canvas th {
  background: var(--paper-2);
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 700;
}
.slaides-canvas .ProseMirror-selectednode {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* ----- floating selection toolbar ----- */
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
  background: rgba(255, 255, 255, 0.12);
}

.wys-toolbar button.on {
  background: rgba(255, 255, 255, 0.22);
}

.wys-toolbar button.accent {
  color: #8bb0ff;
  font-weight: 700;
}

.wys-toolbar > span {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.18);
  margin: 0 2px;
}
</style>
