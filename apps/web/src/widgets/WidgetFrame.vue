<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch, type CSSProperties } from "vue";
import { llmApi } from "@/api/llm";
import { useSessionStore } from "@/stores/session";
import { WIDGET_BRIDGE_SOURCE } from "./bridge";
import { buildThemeStyleBlock, readHostTokens } from "./theme-tokens";
import type { Widget } from "@/api/types";

const props = withDefaults(
  defineProps<{
    widget: Widget;
    placementId: string;
    bootProps: Record<string, unknown>;
    role?: "instructor" | "audience" | "preview" | "thumbnail";
    minHeight?: number;
    /** When true, the widget is the sole occupant of its slide and should
     * stretch to fill the canvas instead of collapsing to scrollHeight. */
    fill?: boolean;
    /** Audience identity baked into `window.slaides.participant` so widgets
     * can greet/score by name without re-asking. `display_name` is `null`
     * for presenter / preview / fully-anonymous joins. `ref` is the stable
     * per-participant id — used ONLY to scope per-viewer scratch state in
     * sessionStorage; it is NOT injected into the iframe boot (the widget
     * still sees `participant.id === null`). */
    participant?: { display_name?: string | null; anon?: boolean; ref?: string | null };
  }>(),
  { role: "preview", minHeight: 80, fill: false },
);

const emit = defineEmits<{
  (e: "interaction", payload: { type: string; payload: Record<string, unknown> }): void;
  (e: "selection", payload: { x: number; y: number; text: string; contextMenu?: boolean }): void;
}>();

interface WidgetBroadcastDetail {
  widgetId: string;
  type: string;
  payload: Record<string, unknown>;
}

const iframeEl = ref<HTMLIFrameElement | null>(null);
const measured = shallowRef<number>(props.minHeight);
const frameReady = shallowRef(props.role === "thumbnail");
let revealTimer = 0;

// `window.__slaides_preview` is set by Audience.vue / Presenter.vue right after
// the preview-iframe handshake. When true, we bake a click-inspector script
// into the widget srcdoc so the editor's preview tab can click an element and
// feed it into the AI Adjust chat. Captured once at mount so a later flip
// doesn't reload the iframe and wipe widget state.
const isPreviewContext =
  typeof window !== "undefined" && (window as unknown as { __slaides_preview?: boolean }).__slaides_preview === true;

// Widget event types the host will relay. Anything outside this set is
// silently dropped, so a misbehaving or malicious widget can't smuggle
// arbitrary `type` strings through the bridge.
const ALLOWED_INTERACTION_TYPES = new Set([
  "vote",
  "text",
  "value",
  "slider",
  "plotter.update",
  "question.raise",
  "state.set",
  // Widgets v2 Step 4 — Loud widgets emit `widget.contribute` for the
  // unified protocol. The parent page forwards it to the WS as
  // `widget.contribute { placement_id, value }`.
  "widget.contribute",
]);

// Bound the number of concurrent LLM calls one widget can have in flight.
// Real widgets only need one; the cap exists so a buggy widget can't spray
// the proxy with unbounded requests.
const MAX_INFLIGHT_LLM = 4;
const inflightLlm = new Map<string, AbortController>();

// Theme tokens are resolved once at mount time and baked into the iframe's
// :root. Shared with WidgetThumbnail so the sidebar previews and the canvas
// render against the same token set. See widgets/theme-tokens.ts.
const hostTokens = readHostTokens();

function cloneForPostMessage(value: Record<string, unknown>): Record<string, unknown> {
  try {
    const cloned = JSON.parse(JSON.stringify(value ?? {}));
    return cloned && typeof cloned === "object" ? cloned as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

// Snapshot bootProps at mount so later mutations don't recompute `srcdoc` and
// reload the iframe — that would wipe live widget state (poll votes, input
// text, plotter expression). Live prop updates flow exclusively through the
// `props.update` postMessage in the watch() below. Deep-clone via JSON to
// detach from Vue's reactive proxy so nested mutations stay invisible here.
const bootSnapshot = cloneForPostMessage(props.bootProps || {});
// Same idiom for participant identity: snapshot at mount so a transient
// change in the join state doesn't reload the iframe and wipe in-progress
// quiz answers.
const participantSnapshot = {
  id: null,
  display_name: props.participant?.display_name ?? null,
  anon: props.participant?.anon ?? false,
};

// Per-viewer scratch state (slaides.setState/getState). The sandboxed iframe
// has a null origin and can't use sessionStorage, so the host persists it and
// replays it as `boot.state` on (re)mount — that's what makes a submitted
// answer survive navigating away from the slide and back.
function viewerStateStorageKey(): string | null {
  if (!props.placementId) return null; // editor preview / thumbnail: ephemeral
  // Scope by participant_ref, not role: multiple audience members can share one
  // browsing context (the multi-audience preview harness mounts every audience
  // iframe in one page → one sessionStorage). A role-only key makes them clobber
  // each other so everyone reads the last writer's answer. Fall back to role
  // when there's no participant (single presenter / preview).
  const viewer = props.participant?.ref || props.role;
  return `slaides:wstate:${props.widget.id}:${props.placementId}:${viewer}`;
}

function loadViewerState(): Record<string, unknown> {
  const key = viewerStateStorageKey();
  if (!key) return {};
  try {
    const raw = sessionStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function persistViewerState(stateKey: string, value: unknown): void {
  const key = viewerStateStorageKey();
  if (!key) return;
  try {
    const current = loadViewerState();
    current[stateKey] = value;
    sessionStorage.setItem(key, JSON.stringify(current));
  } catch {
    // sessionStorage unavailable (private mode / SSR / quota) — degrade to the
    // old in-memory-only behaviour rather than throwing.
  }
}

// Snapshot at mount, same rationale as bootProps: a later change must not
// recompute srcdoc and reload the iframe.
const bootStateSnapshot = loadViewerState();

const srcdoc = computed(() =>
  buildSrcdoc(
    props.widget,
    {
      props: bootSnapshot,
      role: props.role,
      participant: participantSnapshot,
      behavior: props.widget.behavior || { kind: "quiet" },
      state: bootStateSnapshot,
    },
    props.fill,
  ),
);

const showSkeleton = computed(() => props.role !== "thumbnail" && !frameReady.value);
const iframeStyle = computed<CSSProperties>(() => {
  const base: CSSProperties = {
    width: "100%",
    border: "0",
    borderRadius: "0",
    background: "transparent",
    display: "block",
    overflow: "hidden",
  };
  if (props.role === "thumbnail") return base;
  if (props.fill) {
    return {
      ...base,
      height: `${props.minHeight}px`,
      opacity: showSkeleton.value ? 0 : 1,
      transition: "opacity .18s ease",
    };
  }
  return {
    ...base,
    height: `${measured.value}px`,
    opacity: showSkeleton.value ? 0 : 1,
    transition: "height .15s ease, opacity .18s ease",
  };
});

function buildSrcdoc(w: Widget, boot: Record<string, unknown>, fill: boolean): string {
  // NOTE: closing script tags are split into "</scr" + "ipt>" so this Vue SFC
  // parses correctly — a literal closing tag inside a string would otherwise
  // end the surrounding script setup block.
  const close = "</scr" + "ipt>";
  const open = "<scr" + "ipt>";
  // CSP locks the widget down to its own srcdoc: no network (`connect-src
  // 'none'`), no external scripts/styles/fonts, no frame embedding, no form
  // submissions, no relative `base` retargeting. Inline scripts/styles stay
  // permitted because seed and user widgets author them inline; we accept the
  // residual XSS risk inside the sandbox-null origin in exchange for the
  // network lockdown.
  //
  // img-src admits `https:` (in addition to `data:`) so widgets like the
  // Carousel can load images from arbitrary HTTPS URLs the instructor
  // supplies. The trade-off: a malicious widget could exfil what-it-sees
  // by encoding it into an image-src URL (image GETs are not blocked by
  // `connect-src 'none'`). Acceptable because (a) the iframe is
  // sandbox=allow-scripts with a null origin so it has zero access to
  // host cookies/localStorage/Pinia, (b) the only data inside the iframe
  // is props the instructor chose to pass + audience contributions the
  // audience chose to send, and (c) widget authoring is already trusted
  // workflow (LLM-generated drafts are reviewed before apply).
  const csp =
    "default-src 'none'; " +
    "style-src 'unsafe-inline'; " +
    "script-src 'unsafe-inline'; " +
    "img-src data: https:; " +
    "font-src data:; " +
    "connect-src 'none'; " +
    "base-uri 'none'; " +
    "form-action 'none'; " +
    "frame-ancestors 'self';";
  // Bake host theme tokens into the iframe's :root so widgets can reference
  // `var(--background)`, `var(--primary)`, etc. instead of hard-coding hex.
  const themeStyle = buildThemeStyleBlock(hostTokens, { fill });
  const widgetCss = w.css ? `<style>\n${w.css}\n</style>` : "";
  const widgetJs = w.js ? `${open}\n${w.js}\n${close}` : "";
  const selectionBridgeScript =
    props.role !== "thumbnail"
      ? `${open}
(function(){
  var lastText = "";
  var timer = 0;
  function readSelection(){
    var sel = window.getSelection && window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
    var text = String(sel.toString() || "").trim();
    if (!text) return null;
    var range = sel.getRangeAt(0);
    var rect = range.getBoundingClientRect();
    if ((!rect.width && !rect.height) && range.getClientRects) {
      var rects = range.getClientRects();
      rect = rects && rects.length ? rects[0] : rect;
    }
    if (!rect || (!rect.width && !rect.height)) return null;
    return {
      text: text.slice(0, 4000),
      rect: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height
      }
    };
  }
  function postSelection(contextMenu){
    var selected = readSelection();
    if (!selected) {
      if (lastText) {
        lastText = "";
        parent.postMessage({ slaides: true, type: "widget.selection.clear", payload: {} }, "*");
      }
      return false;
    }
    lastText = selected.text;
    parent.postMessage({
      slaides: true,
      type: "widget.selection",
      payload: {
        text: selected.text,
        rect: selected.rect,
        contextMenu: !!contextMenu
      }
    }, "*");
    return true;
  }
  function schedule(){
    clearTimeout(timer);
    timer = setTimeout(function(){ postSelection(false); }, 0);
  }
  document.addEventListener("selectionchange", schedule);
  document.addEventListener("pointerup", schedule, true);
  document.addEventListener("keyup", schedule, true);
  document.addEventListener("contextmenu", function(e){
    if (!postSelection(true)) return;
    e.preventDefault();
    e.stopPropagation();
  }, true);
})();
${close}`
      : "";
  // Preview-tab inspector. Listens for `preview.inspect` from the host and,
  // when armed, intercepts the next click to send a `preview.pick` message
  // up with a CSS-ish selector + visible text snippet. Not loaded outside
  // the preview tab — production audience iframes don't see this.
  const inspectorScript = isPreviewContext
    ? `${open}
(function(){
  var on = false;
  var lastEl = null;
  function buildSelector(el){
    if (!el || !el.tagName) return "";
    var tag = el.tagName.toLowerCase();
    if (el.id) return tag + "#" + el.id;
    var cls = el.className && typeof el.className === "string" ? el.className.trim().split(/\\s+/).slice(0, 2).join(".") : "";
    return cls ? tag + "." + cls : tag;
  }
  function outline(el, on){
    if (!el || !el.style) return;
    el.style.outline = on ? "2px solid #d9534f" : "";
    el.style.outlineOffset = on ? "2px" : "";
  }
  document.addEventListener("mouseover", function(e){
    if (!on) return;
    if (lastEl && lastEl !== e.target) outline(lastEl, false);
    lastEl = e.target;
    outline(lastEl, true);
  }, true);
  document.addEventListener("mouseout", function(e){
    if (!on) return;
    if (e.target === lastEl) { outline(lastEl, false); lastEl = null; }
  }, true);
  document.addEventListener("click", function(e){
    if (!on) return;
    e.preventDefault();
    e.stopPropagation();
    var el = e.target;
    var classes = el && el.classList ? Array.prototype.slice.call(el.classList) : [];
    var text = el && el.textContent ? el.textContent.trim().slice(0, 80) : "";
    parent.postMessage({
      slaides: true,
      type: "preview.pick",
      payload: {
        selector: buildSelector(el),
        tag: el && el.tagName ? el.tagName.toLowerCase() : "",
        classes: classes,
        text: text,
      },
    }, "*");
  }, true);
  window.addEventListener("message", function(e){
    var d = e.data;
    if (!d || d.slaides !== true || d.type !== "preview.inspect") return;
    on = !!d.on;
    document.body.style.cursor = on ? "crosshair" : "";
    if (!on && lastEl) { outline(lastEl, false); lastEl = null; }
  });
})();
${close}`
    : "";
  // Boot props get injected BEFORE the bridge runs so widget scripts read
  // window.slaides.props synchronously — no async race with bridge.init.
  const bootJSON = JSON.stringify(boot).replace(/</g, "\\u003c");
  return `<!doctype html>
<html><head><meta charset="utf-8"/>
<meta http-equiv="Content-Security-Policy" content="${csp}"/>
<style>${themeStyle}</style>
${widgetCss}
${open}window.__slaides_boot = ${bootJSON};${close}
${open}${WIDGET_BRIDGE_SOURCE}${close}
${selectionBridgeScript}
${inspectorScript}
</head>
<body>
${w.html || ""}
${widgetJs}
</body></html>`;
}

function send(type: string, payload: Record<string, unknown>) {
  iframeEl.value?.contentWindow?.postMessage(
    { slaides: true, type, payload: cloneForPostMessage(payload) },
    "*",
  );
}

function emitSelectionFromIframe(payload: Record<string, unknown>, contextMenu = false) {
  const iframe = iframeEl.value;
  if (!iframe) return;
  const text = typeof payload.text === "string" ? payload.text.trim() : "";
  if (!text) return;
  const rect = payload.rect && typeof payload.rect === "object"
    ? payload.rect as { left?: unknown; top?: unknown; width?: unknown; height?: unknown }
    : null;
  if (!rect) return;
  const left = Number(rect.left);
  const top = Number(rect.top);
  const width = Number(rect.width);
  const height = Number(rect.height);
  if (![left, top, width, height].every(Number.isFinite)) return;
  const frameRect = iframe.getBoundingClientRect();
  emit("selection", {
    x: frameRect.left + left + width / 2,
    y: frameRect.top + top,
    text,
    contextMenu,
  });
}

function onMessage(ev: MessageEvent) {
  const data = ev.data as { slaides?: boolean; type?: string; on?: boolean; payload?: Record<string, unknown> } | null;
  if (!data || !data.slaides) return;
  // Preview-tab inspect toggle from the audience/presenter page above us:
  // forward straight to the widget iframe so the inspector script can arm/disarm.
  if (isPreviewContext && data.type === "preview.inspect" && ev.source !== iframeEl.value?.contentWindow) {
    iframeEl.value?.contentWindow?.postMessage(
      { slaides: true, type: "preview.inspect", on: !!data.on },
      "*",
    );
    return;
  }
  // Identity check on the source window — sandbox=allow-scripts iframes have
  // a "null" opaque origin so event.origin comparison is meaningless; relying
  // on contentWindow identity is the only viable filter.
  if (ev.source !== iframeEl.value?.contentWindow) return;
  // preview.pick travels widget-iframe → host → up to the preview tab. Skip
  // the allowlist (it's a dev-mode channel) and only forward when the host
  // itself is inside the preview tab.
  if (data.type === "preview.pick" && isPreviewContext && window.parent !== window) {
    try {
      window.parent.postMessage(
        { slaides: true, type: "preview.pick", payload: data.payload || {} },
        "*",
      );
    } catch {
      // window.parent is same-origin in our preview tab; the try/catch is defence in depth.
    }
    return;
  }
  const type = typeof data.type === "string" ? data.type : "";
  if (!type) return;
  if (type === "widget.selection") {
    emitSelectionFromIframe(data.payload || {}, !!data.payload?.contextMenu);
    return;
  }
  if (type === "widget.selection.clear") {
    emit("selection", { x: 0, y: 0, text: "" });
    return;
  }
  if (type === "state.set") {
    // Persist per-viewer scratch state so it survives an iframe remount. The
    // widget already updated its own in-iframe copy; we mirror it to host
    // sessionStorage and replay via boot.state next mount.
    const payload = (data.payload || {}) as { key?: unknown; value?: unknown };
    if (typeof payload.key === "string") persistViewerState(payload.key, payload.value);
    return;
  }
  if (type === "resize") {
    // In fill mode the iframe owns the height (via minHeight) and the widget's
    // body resolves to that height via `height:100%`. Echoing scrollHeight back
    // would feed into the body height and cause an infinite +2px growth loop,
    // so ignore resize events in fill mode entirely.
    if (props.fill) return;
    const h = Number((data.payload as { height?: number } | undefined)?.height);
    if (Number.isFinite(h) && h > 0) {
      const next = Math.max(props.minHeight, Math.ceil(h));
      if (Math.abs(next - measured.value) > 1) measured.value = next;
    }
    return;
  }
  if (type === "llm.request") {
    const id = String((data.payload || {}).id || "");
    const prompt = String((data.payload || {}).prompt || "");
    if (!id || !prompt) return;
    if (props.role === "audience" || props.role === "thumbnail") {
      send("llm.reply", { id, error: "LLM calls from audience widgets are disabled." });
      return;
    }
    if (inflightLlm.has(id)) return;
    if (inflightLlm.size >= MAX_INFLIGHT_LLM) {
      send("llm.reply", { id, error: "Too many concurrent LLM requests from this widget." });
      return;
    }
    const controller = new AbortController();
    inflightLlm.set(id, controller);
    void llmApi
      .completeText(
        {
          purpose: "inline_write",
          prompt,
          context: { widget_id: props.widget.id, widget_kind: props.widget.kind },
        },
        { signal: controller.signal },
      )
      .then((text) => {
        if (!controller.signal.aborted) send("llm.reply", { id, text });
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        send("llm.reply", { id, error: err instanceof Error ? err.message : "LLM request failed." });
      })
      .finally(() => {
        if (inflightLlm.get(id) === controller) inflightLlm.delete(id);
      });
    return;
  }
  if (props.role === "thumbnail") return;
  if (!ALLOWED_INTERACTION_TYPES.has(type)) return;
  emit("interaction", { type, payload: data.payload || {} });
}

function onBroadcast(ev: Event) {
  const detail = (ev as CustomEvent<WidgetBroadcastDetail>).detail;
  if (!detail || detail.widgetId !== props.widget.id) return;
  send(detail.type, detail.payload);
}

function onIframeLoad() {
  window.clearTimeout(revealTimer);
  revealTimer = window.setTimeout(() => {
    frameReady.value = true;
  }, 220);

  // Replay the persisted Loud-widget state from the session store so the
  // freshly-loaded iframe boots with whatever the host already knew about
  // this placement. Quiet widgets have no placement state and skip silently.
  // Pinia may not be active in non-live contexts (editor preview, thumbnail
  // tests); guard accordingly.
  let entry;
  try {
    entry = useSessionStore().placementStates[props.placementId];
  } catch {
    return;
  }
  if (!entry) return;
  send("state", {
    placement_id: entry.placement_id,
    state: entry.state,
    state_version: entry.state_version,
    closed: entry.closed,
  });
}

onMounted(() => {
  window.addEventListener("message", onMessage);
  window.addEventListener("slaides:widget-broadcast", onBroadcast as EventListener);
});
onBeforeUnmount(() => {
  window.clearTimeout(revealTimer);
  window.removeEventListener("message", onMessage);
  window.removeEventListener("slaides:widget-broadcast", onBroadcast as EventListener);
  for (const controller of inflightLlm.values()) controller.abort();
  inflightLlm.clear();
});

// When props change (e.g. Adjust panel updates), push them into the running iframe.
watch(
  () => props.bootProps,
  (next) => send("props.update", { props: next || {} }),
  { deep: true },
);

watch(srcdoc, () => {
  window.clearTimeout(revealTimer);
  frameReady.value = props.role === "thumbnail";
});
</script>

<template>
  <div class="widget-frame-shell">
    <iframe
      ref="iframeEl"
      class="widget-frame"
      :srcdoc="srcdoc"
      :title="`Widget · ${widget.kind}`"
      sandbox="allow-scripts allow-forms"
      scrolling="no"
      @load="onIframeLoad"
      :style="iframeStyle"
    />
    <div
      v-if="role !== 'thumbnail'"
      class="widget-frame-skeleton"
      :class="{ 'is-hidden': !showSkeleton }"
      aria-hidden="true"
    >
      <div class="widget-frame-skeleton-head" />
      <div class="widget-frame-skeleton-line widget-frame-skeleton-line-main" />
      <div class="widget-frame-skeleton-line" />
      <div class="widget-frame-skeleton-action" />
    </div>
  </div>
</template>

<style scoped>
.widget-frame-shell {
  position: relative;
}

.widget-frame-skeleton {
  position: absolute;
  inset: 0;
  min-height: 80px;
  padding: 20px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  overflow: hidden;
  pointer-events: none;
  opacity: 1;
  transition: opacity .18s ease;
}

.widget-frame-skeleton.is-hidden {
  opacity: 0;
}

.widget-frame-skeleton-head,
.widget-frame-skeleton-line,
.widget-frame-skeleton-action {
  position: relative;
  z-index: 1;
  display: block;
  border-radius: var(--r-sm);
  background: color-mix(in srgb, var(--ink-soft) 11%, var(--paper));
}

.widget-frame-skeleton-head {
  width: 76px;
  height: 8px;
  margin-bottom: 20px;
}

.widget-frame-skeleton-line {
  width: 52%;
  height: 10px;
  margin-top: 10px;
}

.widget-frame-skeleton-line-main {
  width: 68%;
  height: 16px;
}

.widget-frame-skeleton-action {
  width: 116px;
  height: 28px;
  margin-top: 20px;
}
</style>
