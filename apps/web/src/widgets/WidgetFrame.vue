<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { llmApi } from "@/api/llm";
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
     * for presenter / preview / fully-anonymous joins. */
    participant?: { display_name?: string | null; anon?: boolean };
  }>(),
  { role: "preview", minHeight: 80, fill: false },
);

const emit = defineEmits<{
  (e: "interaction", payload: { type: string; payload: Record<string, unknown> }): void;
}>();

interface WidgetBroadcastDetail {
  widgetId: string;
  type: string;
  payload: Record<string, unknown>;
}

const iframeEl = ref<HTMLIFrameElement | null>(null);
const measured = ref<number>(props.minHeight);

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

const srcdoc = computed(() =>
  buildSrcdoc(
    props.widget,
    {
      props: bootSnapshot,
      role: props.role,
      participant: participantSnapshot,
      behavior: props.widget.behavior || { kind: "quiet" },
    },
    props.fill,
  ),
);

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

onMounted(() => {
  window.addEventListener("message", onMessage);
  window.addEventListener("slaides:widget-broadcast", onBroadcast as EventListener);
});
onBeforeUnmount(() => {
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
</script>

<template>
  <iframe
    ref="iframeEl"
    :srcdoc="srcdoc"
    :title="`Widget · ${widget.kind}`"
    sandbox="allow-scripts allow-forms"
    scrolling="no"
    :style="role === 'thumbnail'
      ? {
          border: '0',
          borderRadius: '0',
          background: 'transparent',
          display: 'block',
          overflow: 'hidden',
        }
      : fill
      ? {
          width: '100%',
          height: minHeight + 'px',
          border: '0',
          borderRadius: '0',
          background: 'transparent',
          display: 'block',
          overflow: 'hidden',
        }
      : {
          width: '100%',
          height: measured + 'px',
          border: '0',
          borderRadius: '0',
          background: 'transparent',
          display: 'block',
          transition: 'height .15s ease',
          overflow: 'hidden',
        }"
  />
</template>
