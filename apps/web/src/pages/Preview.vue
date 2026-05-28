<script setup lang="ts">
/**
 * Multi-audience widget testing harness — meeting-app layout.
 *
 * Left rail = vertical thumbnails (live renders) of every view; clicking a
 * thumb swaps it into the main stage. The right aside is the existing AI
 * Adjust chat, scoped to the current slide's first widget placement.
 *
 * IMPORTANT — iframe DOM stability:
 *   Browsers reload an iframe whenever its parent DOM node changes (Vue's
 *   <Teleport> moves the DOM and would trigger this). To keep the live state
 *   across thumb→stage swaps we mount every iframe ONCE in a stable
 *   `.preview-floats` container at the page root and only mutate inline
 *   styles (top/left/width/height/transform) to position each tile over its
 *   target slot — either the stage frame (active) or its rail thumb
 *   (inactive). The iframe document never reloads on selection swaps.
 *
 *   Inactive tiles render at the stage's full pixel size and use
 *   `transform: scale()` to fit the thumb visually — the inner widget code
 *   still lays out at "normal" resolution, so it's a true scaled-down live
 *   render, not a tiny low-DPI mini-version.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import type { Deck, GuestJoinResponse, PreviewFakeGuest, PreviewSessionResponse, Slide } from "@/api/types";
import PreviewTile from "@/components/PreviewTile.vue";
import WidgetCollection from "@/components/WidgetCollection.vue";
import Icon from "@/components/Icon.vue";

const props = defineProps<{ deckId: string }>();
const router = useRouter();

const PREVIEW_AUDIENCE_MAX = 5;
const deck = ref<Deck | null>(null);
const previewSession = ref<PreviewSessionResponse | null>(null);
const audienceCount = ref(3);
const slideIndex = ref(0);
const inspect = ref(false);
const asideOpen = ref(true);
const loading = ref(false);
const activeKey = ref<string>("presenter");

// Resizable AI Adjust panel — drag the handle on its left edge. Width
// persisted in localStorage so the next preview tab opens at the same size.
const ASIDE_WIDTH_KEY = "slaides:preview-aside-width";
const ASIDE_MIN = 300;
const ASIDE_MAX = 720;
function clampAsideWidth(w: number): number {
  if (typeof window === "undefined") return Math.min(ASIDE_MAX, Math.max(ASIDE_MIN, w));
  const viewportMax = Math.max(ASIDE_MIN, window.innerWidth - 480);
  return Math.round(Math.min(Math.min(ASIDE_MAX, viewportMax), Math.max(ASIDE_MIN, w)));
}
function readAsideWidth(): number {
  if (typeof window === "undefined") return 360;
  const raw = Number(window.localStorage.getItem(ASIDE_WIDTH_KEY));
  return clampAsideWidth(Number.isFinite(raw) && raw > 0 ? raw : 360);
}
const asideWidth = ref(readAsideWidth());
const asideResizing = ref(false);
let resizeRightEdge = 0;
let resizeFrame = 0;
let pendingAsideWidth = 0;

function startAsideResize(event: PointerEvent) {
  resizeRightEdge = window.innerWidth;
  pendingAsideWidth = asideWidth.value;
  asideResizing.value = true;
  window.addEventListener("pointerup", stopAsideResize, { once: true });
  window.addEventListener("blur", stopAsideResize, { once: true });
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  onAsideResize(event);
}

function onAsideResize(event: PointerEvent) {
  if (!asideResizing.value) return;
  pendingAsideWidth = clampAsideWidth(resizeRightEdge - event.clientX);
  if (resizeFrame) return;
  resizeFrame = window.requestAnimationFrame(() => {
    asideWidth.value = pendingAsideWidth;
    resizeFrame = 0;
  });
}

function stopAsideResize() {
  asideResizing.value = false;
  window.removeEventListener("pointerup", stopAsideResize);
  window.removeEventListener("blur", stopAsideResize);
  if (resizeFrame) {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = 0;
  }
  asideWidth.value = pendingAsideWidth || asideWidth.value;
  try {
    window.localStorage.setItem(ASIDE_WIDTH_KEY, String(asideWidth.value));
  } catch {}
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
}

function syncAsideWidth() {
  asideWidth.value = clampAsideWidth(asideWidth.value);
}
const error = ref<string | null>(null);
const selectedTarget = ref<{ selector: string; tag: string; classes: string[]; text: string } | null>(null);

const slides = computed<Slide[]>(() => deck.value?.slides ?? []);
const currentSlide = computed<Slide | null>(() => slides.value[slideIndex.value] ?? null);

// Per-tile current-slide map. Each tile (presenter + each audience) posts
// `preview.slide-changed` from inside its iframe whenever it advances; we
// route those into this map keyed by `tiles[].key`. The AI Adjust chat
// panel binds to the ACTIVE tile's current slide — so if the user clicks
// an audience thumb that's been stepped to a different slide than the
// presenter, the chat panel reflects the widget on THAT audience's slide.
const tileSlideIds = reactive<Record<string, string>>({});

// Slide currently visible in the active tile (`tileSlideIds[activeKey]`)
// or, as a fallback, the slide at `slideIndex` if no tile has reported yet.
const activeSlide = computed<Slide | null>(() => {
  const id = tileSlideIds[activeKey.value];
  if (id) {
    const found = slides.value.find((s) => s.id === id);
    if (found) return found;
  }
  return currentSlide.value;
});

const currentPlacement = computed(() => activeSlide.value?.widgets[0] ?? null);

function readQuery() {
  const route = router.currentRoute.value;
  const s = parseInt((route.query.slide as string) ?? "0", 10);
  const a = parseInt((route.query.audience as string) ?? "3", 10);
  const i = (route.query.inspect as string) === "1";
  const v = typeof route.query.view === "string" ? route.query.view : "";
  if (Number.isFinite(s) && s >= 0) slideIndex.value = s;
  if (Number.isFinite(a)) audienceCount.value = Math.min(Math.max(a, 1), PREVIEW_AUDIENCE_MAX);
  inspect.value = i;
  if (v) activeKey.value = v;
}

function writeQuery() {
  void router.replace({
    query: {
      slide: String(slideIndex.value),
      audience: String(audienceCount.value),
      ...(inspect.value ? { inspect: "1" } : {}),
      ...(activeKey.value && activeKey.value !== "presenter" ? { view: activeKey.value } : {}),
    },
  });
}

async function spinUpPreview() {
  if (!deck.value) return;
  loading.value = true;
  error.value = null;
  try {
    previewSession.value = await sessionsApi.createPreview(deck.value.id, audienceCount.value);
    // Reset to presenter view after a re-spin (new participant refs → URL
    // view= key would be stale anyway).
    activeKey.value = "presenter";
    // Advance the session to the chosen slide so the iframes load it
    // straight away instead of the deck's first slide.
    await advanceTo(slideIndex.value);
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function endCurrentPreview() {
  const sess = previewSession.value;
  if (!sess) return;
  previewSession.value = null;
  try {
    await sessionsApi.end(sess.session_id);
  } catch (err) {
    console.warn("preview end failed", err);
  }
}

async function advanceTo(idx: number) {
  if (!previewSession.value || !deck.value) return;
  const slide = slides.value[idx];
  if (!slide) return;
  try {
    await sessionsApi.advance(previewSession.value.session_id, slide.id, false);
  } catch (err) {
    console.warn("preview advance failed", err);
  }
}

async function setSlide(idx: number) {
  if (idx < 0 || idx >= slides.value.length) return;
  slideIndex.value = idx;
  writeQuery();
  await advanceTo(idx);
}

async function changeAudienceCount(delta: number) {
  const next = audienceCount.value + delta;
  if (next < 1 || next > PREVIEW_AUDIENCE_MAX) return;
  audienceCount.value = next;
  writeQuery();
  // Re-spin after explicitly ending the current preview; the server allows
  // only one active preview per instructor.
  await endCurrentPreview();
  await spinUpPreview();
}

async function resetState() {
  // Re-mint after explicitly ending the current preview. This clears
  // placement_state + participants without keeping duplicate previews alive.
  await endCurrentPreview();
  await spinUpPreview();
}

function toggleInspect() {
  inspect.value = !inspect.value;
  writeQuery();
  if (!inspect.value) selectedTarget.value = null;
}

function onPick(payload: { selector: string; tag: string; classes: string[]; text: string }) {
  selectedTarget.value = payload;
}

function onSlideChanged(tileKey: string, slideId: string) {
  tileSlideIds[tileKey] = slideId;
  // The control-bar Prev/Next only makes sense relative to the presenter
  // (it calls sessionsApi.advance, which broadcasts to audiences). Sync
  // `slideIndex` only when the presenter's iframe reports a slide change.
  if (tileKey !== "presenter") return;
  const idx = slides.value.findIndex((s) => s.id === slideId);
  if (idx < 0 || idx === slideIndex.value) return;
  slideIndex.value = idx;
  writeQuery();
}

function clearSelection() {
  selectedTarget.value = null;
}

function asGuestJoin(g: PreviewFakeGuest, sessionId: string): GuestJoinResponse {
  return {
    session_id: sessionId,
    participant_id: g.participant_id,
    participant_ref: g.participant_ref,
    token: g.token,
    display_name: g.display_name,
    anon: false,
  };
}

interface Tile {
  key: string;
  role: "presenter" | "audience";
  guest?: GuestJoinResponse;
  label: string;
  roleLabel: string;
}

const tiles = computed<Tile[]>(() => {
  const list: Tile[] = [];
  if (previewSession.value) {
    list.push({ key: "presenter", role: "presenter", label: "Presenter", roleLabel: "PRESENTER" });
    for (const g of previewSession.value.fake_guests) {
      list.push({
        key: `aud-${g.participant_ref}`,
        role: "audience",
        guest: asGuestJoin(g, previewSession.value.session_id),
        label: g.display_name,
        roleLabel: "AUDIENCE",
      });
    }
  }
  return list;
});

const activeTile = computed<Tile | null>(() => {
  const list = tiles.value;
  return list.find((t) => t.key === activeKey.value) || list[0] || null;
});

function selectTile(key: string) {
  activeKey.value = key;
  writeQuery();
}

// --- Float positioning -----------------------------------------------------
//
// Each iframe is rendered once in `.preview-floats` and positioned via
// fixed-position inline styles. We track the rect of every thumb slot + the
// stage frame, recompute on resize, and derive each tile's style from the
// rectsMap + activeKey.

const thumbEls = ref<Record<string, HTMLElement | null>>({});
const stageFrameEl = ref<HTMLElement | null>(null);

function setThumbEl(key: string, el: HTMLElement | Element | null) {
  thumbEls.value[key] = (el as HTMLElement | null) || null;
}

const rectsMap = reactive<Record<string, DOMRect>>({});
const stageRect = ref<DOMRect | null>(null);

function recomputeRects() {
  if (stageFrameEl.value) {
    stageRect.value = stageFrameEl.value.getBoundingClientRect();
  }
  for (const t of tiles.value) {
    const el = thumbEls.value[t.key];
    if (el) {
      rectsMap[t.key] = el.getBoundingClientRect();
    }
  }
}

const floatStyle = computed<Record<string, Record<string, string>>>(() => {
  const out: Record<string, Record<string, string>> = {};
  const sr = stageRect.value;
  if (!sr || sr.width === 0 || sr.height === 0) return out;
  for (const t of tiles.value) {
    if (t.key === activeKey.value) {
      out[t.key] = {
        position: "fixed",
        top: `${sr.top}px`,
        left: `${sr.left}px`,
        width: `${sr.width}px`,
        height: `${sr.height}px`,
        transform: "none",
        transformOrigin: "top left",
        zIndex: "5",
      };
      continue;
    }
    const tr = rectsMap[t.key];
    if (!tr || tr.width === 0) {
      out[t.key] = { display: "none" };
      continue;
    }
    const scale = tr.width / sr.width;
    out[t.key] = {
      position: "fixed",
      top: `${tr.top}px`,
      left: `${tr.left}px`,
      width: `${sr.width}px`,
      height: `${sr.height}px`,
      transform: `scale(${scale})`,
      transformOrigin: "top left",
      // Inactive tiles render their iframe at full pixel size, then scale
      // visually — the click-shield above intercepts taps that would
      // otherwise reach the inner inspector.
      pointerEvents: "none",
      zIndex: "1",
    };
  }
  return out;
});

let resizeObserver: ResizeObserver | null = null;

function observeAll() {
  if (!resizeObserver) return;
  resizeObserver.disconnect();
  if (stageFrameEl.value) resizeObserver.observe(stageFrameEl.value);
  for (const el of Object.values(thumbEls.value)) {
    if (el) resizeObserver.observe(el);
  }
  recomputeRects();
}

// Recompute when tiles change (re-spin), when active swaps, when the aside
// width changes (stage rect shifts), or on viewport resize.
watch(
  () => tiles.value.map((t) => t.key).join("|"),
  async () => {
    await nextTick();
    observeAll();
  },
);
watch(asideWidth, async () => {
  await nextTick();
  recomputeRects();
});
watch(asideOpen, async () => {
  await nextTick();
  recomputeRects();
});
watch(activeKey, async () => {
  await nextTick();
  recomputeRects();
});

onMounted(async () => {
  readQuery();
  resizeObserver = new ResizeObserver(() => recomputeRects());
  window.addEventListener("resize", onWindowResize);
  // End the preview session on tab close so the row doesn't block this
  // instructor's next preview start.
  window.addEventListener("beforeunload", onBeforeUnload);
  try {
    deck.value = await decksApi.get(props.deckId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    return;
  }
  await spinUpPreview();
  await nextTick();
  observeAll();
  // Belt-and-braces: the thumb's `aspect-ratio: 16/10` resolves into a real
  // pixel height only after the browser has done its first layout pass.
  // `nextTick` returns after Vue's microtask but the browser may still be
  // pre-layout, leaving `getBoundingClientRect()` reporting 0×0 for the
  // presenter thumb. If the user then clicks an audience thumb before any
  // ResizeObserver callback fires, the floatStyle short-circuits to
  // `{ display: "none" }` and the presenter thumb stays blank forever.
  // Force two more recomputes after layout has definitely settled.
  requestAnimationFrame(() => {
    recomputeRects();
    requestAnimationFrame(() => recomputeRects());
  });
});

function onWindowResize() {
  syncAsideWidth();
  recomputeRects();
}

function onBeforeUnload() {
  const sess = previewSession.value;
  if (!sess) return;
  // `keepalive: true` lets the request survive the page being torn down.
  // We bypass the api/client wrapper because that returns a promise — and on
  // beforeunload there's no event loop tick to await. Auth comes off
  // localStorage; if missing, the request 401s and the row stays (no harm).
  try {
    const raw = localStorage.getItem("slaides:auth");
    const access = raw ? (JSON.parse(raw)?.access as string | undefined) : undefined;
    if (!access) return;
    const base = import.meta.env.VITE_API_URL || "/api/v1";
    void fetch(`${base}/sessions/${sess.session_id}/end`, {
      method: "POST",
      headers: { Authorization: `Bearer ${access}` },
      keepalive: true,
    });
  } catch {
    // Best-effort; swallow.
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("resize", onWindowResize);
  window.removeEventListener("beforeunload", onBeforeUnload);
  resizeObserver?.disconnect();
  resizeObserver = null;
  stopAsideResize();
});

// Keep URL in sync with slideIndex when the user navigates with arrow keys.
watch(slideIndex, writeQuery);
</script>

<template>
  <div class="preview-page">
    <header class="preview-controls">
      <div class="preview-controls-group">
        <button
          class="btn btn-ghost btn-sm"
          :disabled="slideIndex <= 0"
          @click="setSlide(slideIndex - 1)"
          title="Previous slide"
        >
          <Icon name="chev_left" :size="14" /> Prev
        </button>
        <span class="preview-controls-label">
          slide {{ slideIndex + 1 }} of {{ slides.length }}
        </span>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="slideIndex >= slides.length - 1"
          @click="setSlide(slideIndex + 1)"
          title="Next slide"
        >
          Next <Icon name="chev_right" :size="14" />
        </button>
      </div>

      <div class="preview-controls-group">
        <span class="preview-controls-label">audiences</span>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="audienceCount <= 1 || loading"
          @click="changeAudienceCount(-1)"
        >−</button>
        <span class="preview-controls-count">{{ audienceCount }}</span>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="audienceCount >= PREVIEW_AUDIENCE_MAX || loading"
          @click="changeAudienceCount(1)"
        >+</button>
      </div>

      <div class="preview-controls-group preview-controls-group--right">
        <button class="btn btn-ghost btn-sm" :disabled="loading" @click="resetState">
          ⟳ reset
        </button>
        <button
          class="btn btn-ghost btn-sm"
          :class="{ 'preview-inspect-on': inspect }"
          @click="toggleInspect"
          title="Click an element in the stage to send it to Adjust"
        >
          inspect {{ inspect ? "●" : "○" }}
        </button>
      </div>
    </header>

    <main
      class="preview-main"
      :class="{ 'preview-main--collapsed': !asideOpen, 'preview-main--resizing': asideResizing }"
      :style="
        asideOpen
          ? { gridTemplateColumns: `200px 1fr ${asideWidth}px` }
          : { gridTemplateColumns: '200px 1fr 0px' }
      "
    >
      <aside class="preview-views-rail">
        <div class="preview-views-title">
          VIEWS · {{ tiles.length || 0 }}
        </div>
        <div v-if="error" class="preview-rail-empty">{{ error }}</div>
        <div v-else-if="!previewSession" class="preview-rail-empty">
          spinning up preview…
        </div>
        <template v-else>
          <div
            v-for="t in tiles"
            :key="`thumb-${t.key}`"
            :ref="(el) => setThumbEl(t.key, el as HTMLElement | null)"
            class="preview-thumb"
            :class="{ active: t.key === activeKey }"
            :data-testid="`preview-thumb-${t.key}`"
            @click="selectTile(t.key)"
          >
            <div class="preview-thumb-label">
              <span class="preview-thumb-name">{{ t.label }}</span>
              <span class="preview-thumb-role">{{ t.roleLabel }}</span>
            </div>
            <div class="preview-thumb-frame">
              <!-- Iframe is positioned over this slot from .preview-floats -->
              <div
                v-if="t.key !== activeKey"
                class="preview-thumb-shield"
                aria-hidden="true"
              />
            </div>
          </div>
        </template>
        <p class="preview-views-hint">click a tile to switch</p>
      </aside>

      <section class="preview-stage">
        <header class="preview-stage-chrome" data-testid="preview-stage-chrome">
          <span class="preview-stage-name">{{ activeTile?.label || "" }}</span>
          <span class="preview-stage-role">{{ activeTile?.roleLabel || "" }}</span>
        </header>
        <div
          ref="stageFrameEl"
          class="preview-stage-frame"
          :data-testid="'preview-stage-frame'"
        >
          <!-- Iframe is positioned over this frame from .preview-floats -->
        </div>
      </section>

      <aside v-if="asideOpen" class="preview-aside">
        <div
          class="preview-aside-resizer"
          role="separator"
          aria-orientation="vertical"
          title="Resize chat panel"
          @pointerdown.prevent="startAsideResize"
        />
        <WidgetCollection
          v-if="deck"
          :placement="currentPlacement"
          :deck-id="deck.id"
          mode="adjust"
          :initial-tab="'generate'"
          :slide-number="slideIndex + 1"
          :disabled="!currentPlacement"
          :disabled-reason="!currentPlacement ? 'This slide has no widget. Add one in the editor first.' : undefined"
          :selected-target="selectedTarget"
          @close="asideOpen = false"
          @clear-selected-target="clearSelection"
        />
      </aside>
      <aside v-else class="preview-rail">
        <button
          class="preview-rail-button"
          title="Open AI Adjust"
          @click="asideOpen = true"
        >
          <Icon name="widget" :size="13" />
          <span class="preview-rail-label">ADJUST</span>
        </button>
      </aside>
    </main>

    <!-- All iframes mount here ONCE; positioned over their target slot via
         inline styles. Reparenting these would reload the iframe documents
         and wipe live state, so they live in a stable container. -->
    <div class="preview-floats" aria-hidden="true">
      <template v-if="previewSession">
        <PreviewTile
          v-for="t in tiles"
          :key="t.key"
          :session-id="previewSession.session_id"
          :role="t.role"
          :guest="t.guest ?? null"
          :inspect="inspect && t.key === activeKey"
          :label="t.label"
          :style="floatStyle[t.key]"
          class="preview-float-tile"
          @pick="onPick"
          @slide-changed="(slideId: string) => onSlideChanged(t.key, slideId)"
        />
      </template>
    </div>

    <div
      v-if="asideResizing"
      class="preview-resize-layer"
      @pointermove.prevent="onAsideResize"
      @pointerup.prevent="stopAsideResize"
    />
  </div>
</template>

<style scoped>
.preview-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--paper);
  color: var(--ink);
}

.preview-controls {
  flex-shrink: 0;
  height: 44px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 0 24px;
}

.preview-controls-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.preview-controls-group--right {
  margin-left: auto;
}

.preview-controls-label {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.preview-controls-count {
  font-family: var(--mono);
  font-size: 13px;
  min-width: 18px;
  text-align: center;
}

.preview-inspect-on {
  background: var(--ink);
  color: var(--paper);
}

.preview-main {
  flex: 1;
  display: grid;
  /* default; overridden by inline style */
  grid-template-columns: 200px 1fr 360px;
  min-height: 0;
  overflow: hidden;
}

.preview-main--collapsed {
  /* Reserve a thin column for the ADJUST pill so the stage iframe doesn't
     overlap it. Without this the float-tile (z-index 5) sits over the pill
     (z-index 4) at the right edge and the pill gets visually clipped. */
  grid-template-columns: 200px 1fr 44px;
}

/* --- Views rail (left) -------------------------------------------------- */

.preview-views-rail {
  border-right: 1px solid var(--rule);
  background: var(--bg-soft, #f7f7f7);
  padding: 10px 10px 14px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-views-title {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--ink-soft);
  text-transform: uppercase;
  padding: 2px 4px 6px;
}

.preview-rail-empty {
  padding: 18px 6px;
  font-family: var(--serif);
  font-size: 12px;
  color: var(--ink-soft);
  font-style: italic;
}

.preview-thumb {
  position: relative;
  cursor: pointer;
  border-radius: var(--r-sm);
  background: var(--paper);
  border: 1px solid var(--rule);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.preview-thumb.active {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  border-color: var(--accent);
}

.preview-thumb-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  gap: 6px;
  border-bottom: 1px solid var(--rule);
  background: var(--paper);
}

.preview-thumb-name {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-thumb-role {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.06em;
  color: var(--ink-soft);
  flex-shrink: 0;
}

.preview-thumb-frame {
  position: relative;
  aspect-ratio: 16 / 10;
  background: var(--paper);
  overflow: hidden;
}

.preview-thumb-shield {
  /* Sits above the floated iframe so a tap on an inactive thumb selects the
     view instead of falling through to the inspector script inside. */
  position: absolute;
  inset: 0;
  z-index: 10;
  cursor: pointer;
  background: transparent;
}

.preview-views-hint {
  margin-top: auto;
  padding: 10px 4px 0;
  font-family: var(--sans);
  font-size: 10px;
  color: var(--ink-soft);
}

/* --- Stage (centre) ----------------------------------------------------- */

.preview-stage {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  padding: 14px;
  gap: 0;
  background: var(--bg-soft, #f7f7f7);
}

.preview-stage-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-bottom: 0;
  border-radius: var(--r-md) var(--r-md) 0 0;
}

.preview-stage-name {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.preview-stage-role {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--ink-soft);
}

.preview-stage-frame {
  position: relative;
  flex: 1;
  min-height: 0;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 0 0 var(--r-md) var(--r-md);
  overflow: hidden;
}

/* --- Floats container --------------------------------------------------- */

.preview-floats {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.preview-float-tile {
  /* :style sets position: fixed + top/left/width/height/transform. Re-enable
     pointer events for the active tile so its iframe is interactive; inactive
     tiles already get pointer-events:none from floatStyle. */
  pointer-events: auto;
  background: var(--paper);
  border-radius: 0 0 var(--r-md) var(--r-md);
}

/* --- Right aside / collapsed rail (unchanged) --------------------------- */

.preview-rail {
  position: relative;
  width: 0;
  min-height: 0;
  pointer-events: none;
}

.preview-rail-button {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  width: 31px;
  height: 115px;
  padding: 14px 8px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  background: var(--paper);
  color: var(--ink-soft);
  cursor: pointer;
  border: 1px solid var(--rule);
  border-right: 0;
  border-radius: 8px 0 0 8px;
  box-shadow:
    0 1px 2px rgba(11, 13, 16, 0.04),
    -2px 6px 18px rgba(11, 13, 16, 0.08),
    -4px 14px 36px rgba(11, 13, 16, 0.08);
  /* Sits above the active float-tile (z-index 5) so the pill is never clipped
     by the iframe even if the reserved 44px collapses on a narrow viewport. */
  z-index: 6;
  transition: box-shadow 0.18s ease, border-color 0.18s ease, color 0.18s ease;
  pointer-events: auto;
}

.preview-rail-button:hover,
.preview-rail-button:focus-visible {
  color: var(--ink);
  border-color: var(--ink);
  box-shadow:
    0 1px 2px rgba(11, 13, 16, 0.06),
    -3px 8px 22px rgba(11, 13, 16, 0.12),
    -6px 18px 44px rgba(11, 13, 16, 0.1);
  outline: none;
}

.preview-rail-label {
  writing-mode: vertical-rl;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 1.6px;
  color: inherit;
  text-transform: uppercase;
}

.preview-rail-button svg {
  flex-shrink: 0;
}

.preview-aside {
  position: relative;
  border-left: 1px solid var(--rule);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.preview-main--resizing {
  transition: none !important;
}

.preview-aside-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -4px;
  width: 8px;
  z-index: 5;
  cursor: col-resize;
  touch-action: none;
}

.preview-aside-resizer::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
  background: transparent;
  transition: background 0.15s ease;
}

.preview-aside-resizer:hover::after,
.preview-aside-resizer:focus-visible::after {
  background: var(--accent);
}

.preview-resize-layer {
  position: fixed;
  inset: 0;
  z-index: 120;
  cursor: col-resize;
  background: transparent;
  touch-action: none;
}
</style>
