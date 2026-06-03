<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useEditorStore } from "@/stores/editor";
import { useWidgetsStore } from "@/stores/widgets";
import { decksApi } from "@/api/decks";
import { sessionsApi } from "@/api/sessions";
import { widgetsApi } from "@/api/widgets";
import Wordmark from "@/components/Wordmark.vue";
import Icon from "@/components/Icon.vue";
import SidebarOpen from "@/components/SidebarOpen.vue";
import SidebarCollapsed from "@/components/SidebarCollapsed.vue";
import SlideCanvas from "@/components/SlideCanvas.vue";
import SlideStepper from "@/components/SlideStepper.vue";
import AddSlideRibbon from "@/components/AddSlideRibbon.vue";
import WidgetCollection from "@/components/WidgetCollection.vue";
import SettingsDrawer from "@/components/SettingsDrawer.vue";
import InterpretPopover from "@/components/InterpretPopover.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import type { SessionListItem, SlideWidgetEmbed, Widget, WidgetSummary } from "@/api/types";

const props = defineProps<{ deckId: string }>();
const router = useRouter();
const auth = useAuthStore();
const editor = useEditorStore();
const widgetsStore = useWidgetsStore();

const sidebarOpen = ref(true);
const sidebarTab = ref<"sections" | "widgets" | "theme">("sections");
const widgetDragActive = ref(false);
const hoverTop = ref(false);
const hoverBottom = ref(false);
const toast = ref<string | null>(null);
const drawerOpen = ref(false);
const drawerTab = ref<"library" | "generate" | "code">("library");
const widgetSidebarMode = ref<"create" | "adjust">("create");
const settingsOpen = ref(false);
const widgetRev = ref(0);
const interpretPopover = ref<{ x: number; y: number; text: string } | null>(null);
const contextMenu = ref<{ x: number; y: number; selection: string } | null>(null);
const canvasFocused = ref(false);
const slideDelete = ref<{ id: string } | null>(null);
const slideDeleting = ref(false);
const activeSession = ref<SessionListItem | null>(null);
const editorMode = ref<"rendered" | "markdown">("rendered");
const WIDGET_SIDEBAR_WIDTH_KEY = "slaides:widget-sidebar-width";
const WIDGET_SIDEBAR_MIN = 340;
const WIDGET_SIDEBAR_MAX = 720;
const widgetSidebarWidth = ref(readWidgetSidebarWidth());
const widgetSidebarEl = ref<HTMLElement | null>(null);
const widgetSidebarResizing = ref(false);
let toastTimer = 0;
let resizeRightEdge = 0;
let resizeFrame = 0;
let pendingSidebarWidth = 0;

function clampWidgetSidebarWidth(width: number): number {
  if (typeof window === "undefined") {
    return Math.round(Math.min(WIDGET_SIDEBAR_MAX, Math.max(WIDGET_SIDEBAR_MIN, width)));
  }
  const leftColumnWidth = sidebarOpen.value ? 260 : 44;
  const viewportMax = Math.max(WIDGET_SIDEBAR_MIN, window.innerWidth - leftColumnWidth - 520);
  return Math.round(Math.min(Math.min(WIDGET_SIDEBAR_MAX, viewportMax), Math.max(WIDGET_SIDEBAR_MIN, width)));
}

function readWidgetSidebarWidth(): number {
  if (typeof window === "undefined") return 420;
  const raw = Number(window.localStorage.getItem(WIDGET_SIDEBAR_WIDTH_KEY));
  return clampWidgetSidebarWidth(Number.isFinite(raw) && raw > 0 ? raw : 420);
}

function syncWidgetSidebarWidth() {
  widgetSidebarWidth.value = clampWidgetSidebarWidth(widgetSidebarWidth.value);
}

onMounted(async () => {
  window.addEventListener("resize", syncWidgetSidebarWidth);
  window.addEventListener("keydown", onEditorKeydown);
  await editor.loadDeck(props.deckId);
  // Restore the active slide from `?slide=N` (1-based position) so a refresh
  // lands the user on the same slide they were editing. Falls through to the
  // store's default (first slide) when the param is missing or out of range.
  restoreActiveSlideFromQuery();
  // Eagerly fetch full widget bodies so they mount inline without a flash.
  await preloadCurrentWidgets();
  widgetRev.value++;
  await refreshActiveSession();
});

function restoreActiveSlideFromQuery() {
  const raw = router.currentRoute?.value?.query?.slide;
  if (typeof raw !== "string") return;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return;
  const slides = editor.deck?.slides ?? [];
  const target = slides[n - 1];
  if (target) editor.setActive(target.id);
}

// Keep the URL in sync with the active slide so a refresh restores it.
// Uses 1-based position to match the visible kicker numbering (`§ 01 …`).
// Position N gets cleared from the URL when N === 1 (the default) so a
// freshly-opened deck has a clean URL.
watch(
  () => [editor.deck?.id, editor.activeSlideId] as const,
  () => {
    if (!editor.deck || !editor.activeSlideId) return;
    const idx = editor.deck.slides.findIndex((s) => s.id === editor.activeSlideId);
    if (idx < 0) return;
    const position = idx + 1;
    const current = router.currentRoute?.value?.query;
    // Skip silently when running under a router mock that doesn't track
    // currentRoute (e.g. some unit tests). The refresh-restore is the only
    // observable effect, so dropping it in tests is harmless.
    if (!current) return;
    const next: Record<string, string | string[]> = { ...current } as Record<string, string | string[]>;
    if (position > 1) {
      next.slide = String(position);
    } else {
      delete next.slide;
    }
    if ((current.slide ?? null) === (next.slide ?? null)) return;
    void router.replace({ query: next });
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("resize", syncWidgetSidebarWidth);
  window.removeEventListener("keydown", onEditorKeydown);
  stopWidgetSidebarResize();
});

watch([sidebarOpen, drawerOpen], syncWidgetSidebarWidth);

function startWidgetSidebarResize(event: PointerEvent) {
  if (!drawerOpen.value) return;
  resizeRightEdge = window.innerWidth;
  pendingSidebarWidth = widgetSidebarWidth.value;
  widgetSidebarResizing.value = true;
  window.addEventListener("pointerup", stopWidgetSidebarResize, { once: true });
  window.addEventListener("blur", stopWidgetSidebarResize, { once: true });
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  onWidgetSidebarResize(event);
}

function onWidgetSidebarResize(event: PointerEvent) {
  if (!widgetSidebarResizing.value) return;
  pendingSidebarWidth = clampWidgetSidebarWidth(resizeRightEdge - event.clientX);
  if (resizeFrame) return;
  resizeFrame = window.requestAnimationFrame(() => {
    widgetSidebarWidth.value = pendingSidebarWidth;
    resizeFrame = 0;
  });
}

function stopWidgetSidebarResize() {
  widgetSidebarResizing.value = false;
  window.removeEventListener("pointerup", stopWidgetSidebarResize);
  window.removeEventListener("blur", stopWidgetSidebarResize);
  if (resizeFrame) {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = 0;
  }
  widgetSidebarWidth.value = pendingSidebarWidth || widgetSidebarWidth.value;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(WIDGET_SIDEBAR_WIDTH_KEY, String(widgetSidebarWidth.value));
  }
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
}

async function refreshActiveSession() {
  try {
    activeSession.value = await sessionsApi.active(props.deckId);
  } catch {
    activeSession.value = null;
  }
}

const activeSlide = computed(() =>
  editor.deck?.slides.find((s) => s.id === editor.activeSlideId) || null,
);
const activeSlideIndex = computed(() => {
  if (!editor.deck || !editor.activeSlideId) return -1;
  return editor.deck.slides.findIndex((s) => s.id === editor.activeSlideId);
});

const activePlacement = computed(() => activeSlide.value?.widgets[0] ?? null);

function onCanvasFocusChange(focused: boolean) {
  canvasFocused.value = focused;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function shouldIgnoreEditorArrow(event: KeyboardEvent): boolean {
  return (
    event.defaultPrevented ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    editorMode.value === "markdown" ||
    canvasFocused.value ||
    drawerOpen.value ||
    settingsOpen.value ||
    !!slideDelete.value ||
    !!interpretPopover.value ||
    !!contextMenu.value ||
    widgetSidebarResizing.value ||
    isEditableTarget(event.target)
  );
}

async function selectRelativeSlide(delta: -1 | 1) {
  if (!editor.deck) return;
  const next = editor.deck.slides[activeSlideIndex.value + delta];
  if (!next) return;
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  editor.setActive(next.id);
}

function onEditorKeydown(event: KeyboardEvent) {
  if (shouldIgnoreEditorArrow(event)) return;

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    void selectRelativeSlide(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    void selectRelativeSlide(1);
  }
}

const derivedKicker = computed(() => {
  if (!editor.deck || !activeSlide.value) return "";
  const slides = editor.deck.slides;
  const idx = slides.findIndex((s) => s.id === activeSlide.value!.id);
  const page = String(idx + 1).padStart(2, "0");
  const section = editor.deck.sections.find((s) => s.id === activeSlide.value!.section_id);
  const label = section?.title?.trim() || "Unsectioned";
  return `§ ${page} — ${label}`;
});

function getWidget(widgetId: string): Widget | null {
  return widgetsStore.cache[widgetId] || null;
}

function onAdjustWidget(placement: SlideWidgetEmbed) {
  void placement;
  openWidgetAdjust();
}

function onRemoveWidgetFromChrome(placement: SlideWidgetEmbed) {
  if (placement.placement_id !== activePlacement.value?.placement_id) return;
  void removeActiveWidget();
}

watch(activePlacement, async (p) => {
  if (!p) return;
  await widgetsStore.fetchOne(p.widget_id);
  // The widget body just landed in the store cache. Bump widgetRev so the
  // canvas's widget node re-reads the resolver and swaps its loading stub for
  // the live iframe (the resolver is an opaque call, not a tracked dep).
  widgetRev.value++;
});

async function preloadCurrentWidgets() {
  if (!editor.deck) return;
  const ids = new Set<string>();
  for (const s of editor.deck.slides) {
    for (const w of s.widgets) ids.add(w.widget_id);
  }
  if (ids.size) await widgetsStore.ensureLoaded([...ids]);
}

function showToast(msg: string) {
  toast.value = msg;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.value = null), 1800);
}

function onCanvasMove(e: MouseEvent) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  hoverTop.value = e.clientY - rect.top < 90;
  hoverBottom.value = rect.bottom - e.clientY < 110;
}
function onCanvasLeave() {
  hoverTop.value = false;
  hoverBottom.value = false;
}

// Widget drag-and-drop from the left-sidebar widgets tab. Activates on
// dragenter if the dragged payload carries our custom MIME type.
const WIDGET_DRAG_MIME = "application/x-slaides-widget";

function hasWidgetPayload(e: DragEvent): boolean {
  const types = e.dataTransfer?.types;
  if (!types) return false;
  // `DataTransferItemList.types` is a DOMStringList in some browsers.
  for (let i = 0; i < types.length; i += 1) {
    if (types[i] === WIDGET_DRAG_MIME) return true;
  }
  return false;
}

function onWidgetDragEnter(e: DragEvent) {
  if (!hasWidgetPayload(e)) return;
  widgetDragActive.value = true;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
}

function onWidgetDragOver(e: DragEvent) {
  if (!hasWidgetPayload(e)) return;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
}

function onWidgetDragLeave(e: DragEvent) {
  // Only clear when the cursor leaves the section element entirely, not when
  // it crosses an inner child boundary (those fire leave + enter in quick
  // succession). `relatedTarget === null` is the cleanest cross-browser
  // signal that the drag left the element.
  if (e.relatedTarget == null) widgetDragActive.value = false;
}

async function onWidgetDrop(e: DragEvent) {
  widgetDragActive.value = false;
  const raw = e.dataTransfer?.getData(WIDGET_DRAG_MIME);
  if (!raw) return;
  if (!activeSlide.value || !editor.deck) {
    showToast("Select a slide first.");
    return;
  }
  let payload: { widget_id?: string; deck_id?: string };
  try {
    payload = JSON.parse(raw) as { widget_id?: string; deck_id?: string };
  } catch {
    return;
  }
  if (!payload.widget_id) return;

  try {
    let summary: WidgetSummary | undefined;
    if (payload.deck_id && payload.deck_id !== editor.deck.id) {
      // Cross-deck. Dedupe by lineage: if this deck already carries a copy
      // derived from the same source widget, reuse it instead of spawning
      // another. Without this, repeated drops of the same widget pollute
      // the deck library with orphan duplicates.
      const existing = widgetsStore.summaries.find(
        (w) => w.derived_from_id === payload.widget_id,
      );
      if (existing) {
        summary = existing;
      } else {
        const copy = await widgetsApi.copyIntoDeck(editor.deck.id, payload.widget_id);
        summary = {
          id: copy.id,
          deck_id: copy.deck_id,
          derived_from_id: copy.derived_from_id ?? null,
          name: copy.name,
          kind: copy.kind,
          description: copy.description ?? null,
          tags: copy.tags ?? [],
          version: copy.version,
          behavior: copy.behavior,
        } as WidgetSummary;
        // Refresh the deck-local list so the new copy appears in the right
        // sidebar library too.
        await widgetsStore.fetchListForDeck(editor.deck.id);
      }
    } else {
      summary = widgetsStore.summaries.find((w) => w.id === payload.widget_id)
        || widgetsStore.crossDeck.find((w) => w.id === payload.widget_id);
    }
    if (!summary) {
      showToast("Widget not found.");
      return;
    }
    // If the slide already has a widget, replace it: detach first so the
    // server's 1-widget-per-slide guard doesn't 409 on the attach below.
    // Match the placement_id off the FRESHLY-RELOADED slide because the
    // cross-deck copy path above reloads the deck and rebinds activeSlide.
    const existing = activeSlide.value?.widgets[0] ?? null;
    const replacing = !!existing;
    if (existing) {
      await editor.detachWidget(activeSlide.value!.id, existing.placement_id);
    }
    await editor.attachWidget(activeSlide.value!.id, summary);
    widgetRev.value++;
    showToast(replacing ? "Widget replaced." : "Widget inserted.");
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not insert widget.");
  }
}

async function patchSlide(md: string) {
  if (!activeSlide.value) return;
  editor.queueSlideUpdate(activeSlide.value.id, md);
}

function setEditorMode(mode: "rendered" | "markdown") {
  contextMenu.value = null;
  canvasFocused.value = false;
  editorMode.value = mode;
}

function onMarkdownInput(e: Event) {
  const target = e.target as HTMLTextAreaElement;
  patchSlide(target.value);
}

async function onMarkdownBlur() {
  canvasFocused.value = false;
  if (activeSlide.value) await editor.flushSlide(activeSlide.value.id);
}

async function insertSlideAbove() {
  if (!activeSlide.value) return;
  await editor.flushSlide(activeSlide.value.id);
  await editor.insertSlideAt(activeSlide.value.position, activeSlide.value.section_id);
}

async function insertSlideBelow() {
  if (!activeSlide.value) return;
  await editor.flushSlide(activeSlide.value.id);
  await editor.insertSlideAt(activeSlide.value.position + 1, activeSlide.value.section_id);
}

async function onTitleBlur(e: Event) {
  const target = e.target as HTMLElement;
  const newTitle = (target.textContent || "").trim();
  if (!editor.deck) return;
  if (newTitle && newTitle !== editor.deck.title) {
    await editor.patchTitle(newTitle);
  } else {
    target.textContent = editor.deck.title;
  }
}

async function onStartSession() {
  if (!editor.deck) return;
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  if (activeSession.value) {
    await router.push(`/present/${activeSession.value.id}`);
    return;
  }
  try {
    const session = await sessionsApi.create(editor.deck.id);
    activeSession.value = {
      id: session.id,
      deck_id: session.deck_id,
      code: session.code,
      started_at: session.started_at,
      ended_at: session.ended_at,
      deck_title: editor.deck?.title || "",
      participant_count: 0,
      interaction_count: 0,
    };
    await router.push(`/present/${session.id}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Could not start the session.";
    showToast(msg);
  }
}

function onPreview() {
  if (!editor.deck) return;
  // Open the preview harness in a new tab so the editor stays available
  // underneath. The preview tab mints its own ephemeral session.
  const slideIdx = editor.deck.slides.findIndex((s) => s.id === editor.activeSlideId);
  const startSlide = slideIdx >= 0 ? slideIdx : 0;
  window.open(
    `/decks/${editor.deck.id}/preview?slide=${startSlide}&audience=3`,
    "_blank",
    "noopener",
  );
}

async function onExport() {
  if (!editor.deck) return;
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  const blob = await decksApi.exportDeck(editor.deck.id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${editor.deck.title.replace(/[^a-z0-9-]+/gi, "-")}.slaides`;
  a.click();
  URL.revokeObjectURL(url);
}

async function onPickWidget(w: WidgetSummary) {
  if (!activeSlide.value) return;
  await editor.attachWidget(activeSlide.value.id, w);
  await preloadCurrentWidgets();
  // SlideCanvas paints once when `activeSlide.widgets` changes (right after
  // attachWidget), but the widget body isn't in the store cache yet — so it
  // paints a dashed placeholder. After preload populates the cache we need
  // to nudge SlideCanvas to repaint with the actual iframe, otherwise the
  // slide looks blank until a manual refresh.
  widgetRev.value++;
  widgetSidebarMode.value = "adjust";
}

async function removeActiveWidget() {
  if (!activeSlide.value || !activePlacement.value) return;
  const placementId = activePlacement.value.placement_id;
  try {
    await editor.detachWidget(activeSlide.value.id, placementId);
    widgetRev.value++;
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not remove widget.");
  }
}

async function onSavePlacementProps(payload: { placement_id: string; props: Record<string, unknown> }) {
  // Legacy emit handler — only reached if WidgetCollection wasn't passed the
  // `onPatchPlacementProps` callback prop. The callback path (preferred) goes
  // through patchPlacementPropsForWidget below so the reset-confirm modal can
  // intercept 409s.
  if (!activeSlide.value) return;
  try {
    await editor.patchPlacementProps(activeSlide.value.id, payload.placement_id, payload.props);
    widgetRev.value++;
    showToast("Properties saved.");
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not save properties.");
  }
}

async function patchPlacementPropsForWidget(
  payload: { placement_id: string; props: Record<string, unknown> },
  opts: { resetState?: boolean },
): Promise<void> {
  if (!activeSlide.value) return;
  await editor.patchPlacementProps(
    activeSlide.value.id,
    payload.placement_id,
    payload.props,
    opts,
  );
  // Bump widgetRev so SlideCanvas re-srcdocs the iframe with the fresh
  // bootProps (WidgetFrame snapshots bootProps at mount, so the slide
  // canvas needs a full repaint to apply new prop values to the iframe).
  widgetRev.value++;
  showToast(opts.resetState ? "Saved — audience tally reset." : "Properties saved.");
}

async function onWidgetDeleted(widgetId: string) {
  widgetsStore.invalidate(widgetId);
  // Reload the deck so any slides that referenced this widget refresh their
  // widgets[] embed and the canvas re-paints without the dangling placeholder.
  if (editor.deck) await editor.loadDeck(editor.deck.id);
  widgetRev.value++;
}

function onWidgetApplied(widgetId: string) {
  const w = widgetsStore.cache[widgetId];
  if (w && editor.deck) {
    for (const slide of editor.deck.slides) {
      for (const placement of slide.widgets) {
        if (placement.widget_id === widgetId) {
          placement.kind = w.kind;
          placement.name = w.name;
        }
      }
    }
  }
  widgetRev.value++;
}

function openWidgetLibrary() {
  // If the slide already has a widget, "open the widget panel" should land
  // on the mounted widget's adjust pane (Props if any are declared, else
  // Generate) — not the create-mode library with a disabled banner.
  if (activePlacement.value) {
    openWidgetAdjust();
    return;
  }
  drawerTab.value = "library";
  widgetSidebarMode.value = "create";
  drawerOpen.value = true;
}

function openWidgetGenerator() {
  drawerTab.value = "generate";
  widgetSidebarMode.value = "create";
  drawerOpen.value = true;
}

// "Insert from collection" opens the LEFT sidebar's widgets tab (the browsable
// collection), not the right-hand generate/adjust drawer.
function openWidgetCollection() {
  if (activePlacement.value) {
    // Slide already has a widget — there's nothing to insert; land on adjust.
    openWidgetAdjust();
    return;
  }
  sidebarTab.value = "widgets";
  sidebarOpen.value = true;
}

function openWidgetAdjust() {
  drawerTab.value = "generate";
  widgetSidebarMode.value = "adjust";
  drawerOpen.value = true;
}

function openWidgetCode() {
  if (!activePlacement.value) return;
  drawerTab.value = "code";
  widgetSidebarMode.value = "adjust";
  drawerOpen.value = true;
}

function signOut() {
  auth.signOut();
  router.push("/signin");
}

function onInterpret(payload: { x: number; y: number; text: string }) {
  if (!payload.text.trim()) return;
  interpretPopover.value = payload;
  contextMenu.value = null;
}

function insertInterpretation(text: string) {
  if (!activeSlide.value) return;
  const md = `${activeSlide.value.markdown.trim()}\n\n${text.trim()}`.trim();
  patchSlide(md);
  interpretPopover.value = null;
}

function runClipboardCommand(command: "copy" | "cut" | "paste") {
  document.execCommand(command);
  contextMenu.value = null;
}

function onCanvasContextMenu(payload: { x: number; y: number; selection: string }) {
  contextMenu.value = payload;
}

async function onCreateSection(title: string) {
  try {
    await editor.createSection(title);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not create section.");
  }
}

async function onRenameSection(payload: { id: string; title: string }) {
  try {
    await editor.renameSection(payload.id, payload.title);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not rename section.");
  }
}

async function onDeleteSection(id: string) {
  try {
    await editor.deleteSection(id);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not delete section.");
  }
}

async function onReorderSections(orderedIds: string[]) {
  try {
    await editor.reorderSections(orderedIds);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not reorder sections.");
  }
}

function sectionInsertPosition(sectionId: string): number | null {
  if (!editor.deck) return null;
  const sections = editor.deck.sections.slice().sort((a, b) => a.position - b.position);
  const sectionIndex = new Map(sections.map((s, idx) => [s.id, idx] as const));
  const targetIndex = sectionIndex.get(sectionId);
  if (targetIndex === undefined) return null;

  const slides = editor.deck.slides.slice().sort((a, b) => a.position - b.position);
  const sectionSlides = slides.filter((s) => s.section_id === sectionId);
  if (sectionSlides.length) return Math.max(...sectionSlides.map((s) => s.position)) + 1;

  const firstLaterSlide = slides.find((s) => {
    const idx = s.section_id ? sectionIndex.get(s.section_id) : sections.length;
    return idx !== undefined && idx > targetIndex;
  });
  return firstLaterSlide?.position ?? slides.length;
}

async function onAddSlideToSection(sectionId: string) {
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  try {
    const insertSlideInSection = (editor as typeof editor & {
      insertSlideInSection?: (id: string) => Promise<unknown>;
    }).insertSlideInSection;
    if (typeof insertSlideInSection === "function") {
      await insertSlideInSection(sectionId);
      return;
    }
    const position = sectionInsertPosition(sectionId);
    if (position === null) throw new Error("Section not found.");
    await editor.insertSlideAt(position, sectionId);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not add slide to section.");
  }
}

async function onAddSlideAfter(slideId: string) {
  const slide = editor.deck?.slides.find((s) => s.id === slideId);
  if (!slide) return;
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  try {
    await editor.insertSlideAt(slide.position + 1, slide.section_id);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not add slide below.");
  }
}

async function onReorderSlides(order: { id: string; section_id: string | null }[]) {
  if (editor.activeSlideId) await editor.flushSlide(editor.activeSlideId);
  try {
    await editor.reorderSlides(order);
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not reorder slides.");
  }
}

function deleteSlideWithConfirm(slideId: string) {
  const slideCount = editor.deck?.slides.length ?? 0;
  if (slideCount <= 1) {
    showToast("This is the last slide in the deck — you can't delete it.");
    return;
  }
  slideDelete.value = { id: slideId };
}

async function confirmSlideDelete() {
  if (!slideDelete.value) return;
  slideDeleting.value = true;
  try {
    await editor.deleteSlide(slideDelete.value.id);
    slideDelete.value = null;
  } catch (err) {
    showToast(err instanceof Error ? err.message : "Could not delete slide.");
  } finally {
    slideDeleting.value = false;
  }
}

function onDeleteSlide() {
  contextMenu.value = null;
  if (!activeSlide.value) return;
  deleteSlideWithConfirm(activeSlide.value.id);
}

function onDeleteSlideById(id: string) {
  deleteSlideWithConfirm(id);
}
</script>

<template>
  <div
    :style="{ height: '100vh', overflow: 'hidden', background: 'var(--paper)', display: 'flex', flexDirection: 'column' }"
    @click="contextMenu = null"
  >
    <!-- Top bar -->
    <header
      :style="{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        height: '56px',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 18px',
        flexShrink: 0,
      }"
    >
      <div :style="{ display: 'flex', alignItems: 'center', gap: '14px' }">
        <button class="btn btn-ghost btn-sm" @click="router.push('/workspace')" title="Back to library">
          <Icon name="arrow_left" :size="16" />
        </button>
        <div :style="{ display: 'flex', alignItems: 'center', gap: '10px' }">
          <Wordmark :size="14" />
          <span class="t-meta">·</span>
          <span
            v-if="editor.deck"
            :style="{ fontFamily: 'var(--serif)', fontSize: '17px', letterSpacing: '-0.01em', outline: 'none' }"
            :contenteditable="true"
            @blur="onTitleBlur"
            @keydown.enter.prevent="(e: any) => e.target.blur()"
          >
            {{ editor.deck.title }}
          </span>
          <span
            :style="{
              background: 'var(--paper-2)',
              padding: '2px 7px',
              borderRadius: 'var(--r-xs)',
              fontSize: '11px',
              color: 'var(--ink-soft)',
              fontFamily: 'var(--mono)',
            }"
          >
            {{ editor.saving ? "saving…" : "draft" }}
          </span>
        </div>
      </div>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '8px' }">
        <button
          class="btn btn-sm"
          :disabled="!editor.deck"
          @click="onPreview"
          title="Open the multi-audience preview tab"
        >
          <Icon name="eye" :size="14" /> Preview
        </button>
        <button class="btn btn-sm" @click="onExport">
          <Icon name="download" :size="14" /> Export
        </button>
        <button class="btn btn-ghost btn-sm" @click="settingsOpen = true">
          <Icon name="gear" :size="16" />
        </button>
        <button
          class="btn btn-primary btn-sm"
          @click="onStartSession"
          :title="activeSession ? `Resume · ${activeSession.code}` : 'Start a live session for this deck'"
        >
          <span :style="{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--live)' }" />
          {{ activeSession ? "Resume session" : "Start session" }}
        </button>
      </div>
    </header>

    <div
      :style="{
        display: 'grid',
        gridTemplateColumns: `${sidebarOpen ? '260px' : '44px'} minmax(0, 1fr) ${drawerOpen ? widgetSidebarWidth + 'px' : '0px'}`,
        gridTemplateRows: 'minmax(0, 1fr)',
        flex: 1,
        minHeight: 0,
        transition: widgetSidebarResizing ? 'none' : 'grid-template-columns .2s ease',
      }"
    >
      <aside :style="{ borderRight: '1px solid var(--rule)', background: 'var(--paper-2)', display: 'flex', flexDirection: 'column' }">
        <template v-if="editor.deck">
          <SidebarOpen
            v-if="sidebarOpen"
            :deck="editor.deck"
            :active-slide-id="editor.activeSlideId"
            :tab="sidebarTab"
            @collapse="sidebarOpen = false"
            @set-tab="(t) => (sidebarTab = t)"
            @select-slide="(id) => editor.setActive(id)"
            @delete-slide="onDeleteSlideById"
            @add-slide-after="onAddSlideAfter"
            @add-slide-to-section="onAddSlideToSection"
            @reorder-slides="onReorderSlides"
            @create-section="onCreateSection"
            @rename-section="onRenameSection"
            @delete-section="onDeleteSection"
            @reorder-sections="onReorderSections"
          />
          <SidebarCollapsed
            v-else
            @expand="sidebarOpen = true"
            @select-tab="(t) => { sidebarTab = t; sidebarOpen = true; }"
          />
        </template>
      </aside>

      <main :style="{ position: 'relative', display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, overflow: 'hidden' }">
        <section
          @mousemove="onCanvasMove"
          @mouseleave="onCanvasLeave"
          @dragenter.prevent="onWidgetDragEnter"
          @dragover.prevent="onWidgetDragOver"
          @dragleave="onWidgetDragLeave"
          @drop.prevent="onWidgetDrop"
          class="editor-slide-scroll"
          :class="{ 'widget-drop-active': widgetDragActive }"
          :style="{ flex: 1, overflowY: 'auto', width: '100%', position: 'relative' }"
        >
          <div v-if="widgetDragActive" class="widget-drop-overlay" data-testid="widget-drop-overlay">
            <div class="widget-drop-overlay-card">
              Drop to insert into <strong>slide {{ activeSlideIndex >= 0 ? activeSlideIndex + 1 : "?" }}</strong>
            </div>
          </div>
          <AddSlideRibbon :visible="hoverTop" placement="top" label="Add slide above" @insert="insertSlideAbove" />
          <AddSlideRibbon :visible="hoverBottom" placement="bottom" label="Add slide below" @insert="insertSlideBelow" />

          <div :style="{ maxWidth: '920px', margin: '0 auto', padding: '56px 64px 96px' }">
            <template v-if="activeSlide">
              <div :class="{ 'fade-in': !activeSlide.widgets.length }" :key="activeSlide.id">
                <div class="editor-surface-header">
                  <div class="t-kicker">
                    {{ derivedKicker }}
                  </div>
                  <button
                    type="button"
                    class="editor-mode-switch"
                    :aria-label="editorMode === 'rendered' ? 'Switch to Markdown' : 'Switch to Rendered'"
                    :title="editorMode === 'rendered' ? 'Edit as Markdown' : 'Back to rendered view'"
                    @click="setEditorMode(editorMode === 'rendered' ? 'markdown' : 'rendered')"
                  >
                    <Icon :name="editorMode === 'rendered' ? 'md' : 'eye'" :size="16" />
                  </button>
                </div>
                <SlideCanvas
                  v-if="editorMode === 'rendered'"
                  :markdown="activeSlide.markdown"
                  :slide-id="activeSlide.id"
                  :widgets="activeSlide.widgets"
                  :widget-rev="widgetRev"
                  :get-widget="getWidget"
                  :on-adjust="onAdjustWidget"
                  :on-remove="onRemoveWidgetFromChrome"
                  @update="patchSlide"
                  @interpret="onInterpret"
                  @context-menu="onCanvasContextMenu"
                  @focus-change="onCanvasFocusChange"
                />
                <textarea
                  v-else-if="editorMode === 'markdown'"
                  class="markdown-editor"
                  :value="activeSlide.markdown"
                  spellcheck="false"
                  @input="onMarkdownInput"
                  @focus="canvasFocused = true"
                  @blur="onMarkdownBlur"
                />
                <div
                  :style="{
                    marginTop: '48px',
                    paddingTop: '24px',
                    borderTop: '1px solid var(--rule-soft)',
                    color: 'var(--ink-mute)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '12px',
                  }"
                >
                  <span class="t-mono">slide id · {{ activeSlide.id.slice(0, 8) }}</span>
                  <span class="t-mono">
                    {{ activePlacement ? `widget · ${activePlacement.kind}` : "no widget · 1 max per slide" }}
                  </span>
                </div>
              </div>
            </template>
            <template v-else>
              <div
                :style="{
                  marginTop: '120px',
                  textAlign: 'center',
                  fontFamily: 'var(--serif)',
                  color: 'var(--ink-soft)',
                  fontStyle: 'italic',
                }"
              >
                {{ editor.loading ? "Loading deck…" : "This deck has no slides yet." }}
              </div>
            </template>
          </div>
        </section>

        <SlideStepper
          v-if="editor.deck"
          :slides="editor.deck.slides"
          :active-slide-id="editor.activeSlideId"
          @select="(id) => editor.setActive(id)"
        />
      </main>

      <aside
        ref="widgetSidebarEl"
        :style="{
          width: '100%',
          boxSizing: 'border-box',
          borderLeft: drawerOpen ? '1px solid var(--rule)' : '0',
          background: drawerOpen ? 'var(--paper)' : 'transparent',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          minHeight: 0,
          overflow: drawerOpen ? 'hidden' : 'visible',
          position: 'relative',
        }"
      >
        <div
          v-if="drawerOpen"
          class="widget-sidebar-resizer"
          role="separator"
          aria-orientation="vertical"
          title="Resize widgets sidebar"
          @pointerdown.prevent="startWidgetSidebarResize"
        />
        <WidgetCollection
          v-if="drawerOpen"
          :disabled="!!activePlacement"
          :initial-tab="drawerTab"
          :mode="widgetSidebarMode"
          :placement="activePlacement"
          :deck-id="editor.deck?.id ?? null"
          :slide-number="activeSlideIndex >= 0 ? activeSlideIndex + 1 : null"
          :on-patch-placement-props="patchPlacementPropsForWidget"
          @pick="onPickWidget"
          @close="drawerOpen = false"
          @deleted="onWidgetDeleted"
          @applied="onWidgetApplied"
          @save-placement-props="onSavePlacementProps"
        />
        <div v-else class="right-sidebar-rail">
          <button
            class="right-rail-button"
            title="Open widgets"
            @click="openWidgetLibrary"
          >
            <Icon name="widget" :size="13" />
            <span class="right-rail-label">WIDGETS</span>
          </button>
        </div>
      </aside>

      <div
        v-if="widgetSidebarResizing"
        class="widget-sidebar-resize-layer"
        @pointermove.prevent="onWidgetSidebarResize"
        @pointerup.prevent="stopWidgetSidebarResize"
        @pointercancel.prevent="stopWidgetSidebarResize"
      />
    </div>

    <SettingsDrawer
      :open="settingsOpen"
      :user-name="auth.user?.display_name"
      :user-email="auth.user?.email"
      :can-start-session="!!editor.deck"
      @close="settingsOpen = false"
      @start-session="settingsOpen = false; onStartSession()"
      @sign-out="signOut"
    />

    <div
      v-if="contextMenu"
      class="scale-in"
      :style="{
        position: 'fixed',
        top: contextMenu.y + 4 + 'px',
        left: contextMenu.x + 4 + 'px',
        zIndex: 85,
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-3)',
        padding: '6px',
        minWidth: '240px',
        fontFamily: 'var(--sans)',
        fontSize: '13px',
      }"
      @click.stop
    >
      <div
        v-if="contextMenu.selection"
        :style="{
          padding: '4px 10px 8px',
          fontSize: '11px',
          color: 'var(--ink-mute)',
          fontFamily: 'var(--mono)',
          borderBottom: '1px solid var(--rule-soft)',
          marginBottom: '4px',
        }"
      >
        "{{ contextMenu.selection.slice(0, 32) }}{{ contextMenu.selection.length > 32 ? "..." : "" }}"
      </div>
      <button class="context-item" @click="runClipboardCommand('copy')">Copy <span class="kbd">⌘C</span></button>
      <button v-if="contextMenu.selection" class="context-item accent" @click="onInterpret({ x: contextMenu.x, y: contextMenu.y, text: contextMenu.selection })">
        Interpret with AI
      </button>
      <button class="context-item" @click="runClipboardCommand('cut')">Cut <span class="kbd">⌘X</span></button>
      <button class="context-item" @click="runClipboardCommand('paste')">Paste <span class="kbd">⌘V</span></button>
      <div class="context-divider" />
      <button class="context-item" @click="contextMenu = null; insertSlideAbove()">Add slide above</button>
      <button class="context-item" @click="contextMenu = null; insertSlideBelow()">Add slide below</button>
      <div class="context-divider" />
      <template v-if="activePlacement">
        <button class="context-item" @click="contextMenu = null; openWidgetAdjust()">Adjust widget...</button>
        <button class="context-item context-danger" @click="contextMenu = null; removeActiveWidget()">Remove widget</button>
        <div class="context-hint">1 widget per slide · max reached</div>
      </template>
      <template v-else>
        <button class="context-item" @click="contextMenu = null; openWidgetGenerator()">Generate widget...</button>
        <button class="context-item" @click="contextMenu = null; openWidgetCollection()">Insert from collection...</button>
      </template>
      <div class="context-divider" />
      <button
        class="context-item context-danger"
        :disabled="(editor.deck?.slides.length ?? 0) <= 1"
        @click="onDeleteSlide"
      >
        Delete slide
      </button>
    </div>

    <InterpretPopover
      v-if="interpretPopover"
      :x="interpretPopover.x"
      :y="interpretPopover.y"
      :text="interpretPopover.text"
      @close="interpretPopover = null"
      @insert="insertInterpretation"
    />

    <ConfirmDialog
      :open="!!slideDelete"
      title="Delete this slide?"
      message="The slide and its content will be permanently removed. This can't be undone."
      confirm-label="Delete slide"
      tone="danger"
      :busy="slideDeleting"
      @confirm="confirmSlideDelete"
      @cancel="slideDelete = null"
    />

    <transition name="fade">
      <div
        v-if="toast"
        :style="{
          position: 'fixed',
          bottom: '64px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--ink)',
          color: 'var(--paper)',
          padding: '10px 18px',
          borderRadius: 'var(--r-md)',
          fontSize: '12px',
          fontFamily: 'var(--sans)',
          zIndex: 100,
          boxShadow: 'var(--shadow-3)',
        }"
      >
        {{ toast }}
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.context-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink);
  text-align: left;
  font-size: 13px;
}

.context-item:hover {
  background: var(--paper-2);
}

.context-item.accent {
  color: var(--accent);
}

.context-item.context-danger {
  color: var(--err);
}

.context-item.context-danger:disabled {
  color: var(--ink-disabled);
  cursor: not-allowed;
  background: transparent;
}

.context-item .kbd {
  margin-left: auto;
}

.context-divider {
  height: 1px;
  background: var(--rule-soft);
  margin: 4px 0;
}

.context-hint {
  padding: 4px 10px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--ink-mute);
}

.right-sidebar-rail {
  position: relative;
  flex: 1;
  min-height: 0;
  width: 100%;
  pointer-events: none;
}

.right-rail-button {
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
  z-index: 4;
  transition: box-shadow 0.18s ease, border-color 0.18s ease, color 0.18s ease;
  pointer-events: auto;
}

.right-rail-button:hover,
.right-rail-button:focus-visible {
  color: var(--ink);
  border-color: var(--ink);
  box-shadow:
    0 1px 2px rgba(11, 13, 16, 0.06),
    -3px 8px 22px rgba(11, 13, 16, 0.12),
    -6px 18px 44px rgba(11, 13, 16, 0.1);
  outline: none;
}

.right-rail-label {
  writing-mode: vertical-rl;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 1.6px;
  color: inherit;
  text-transform: uppercase;
}

.right-rail-button svg {
  flex-shrink: 0;
}

.widget-sidebar-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -4px;
  width: 8px;
  z-index: 5;
  cursor: col-resize;
  touch-action: none;
}

.widget-sidebar-resizer::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 3px;
  width: 2px;
  background: transparent;
  transition: background 0.15s ease;
}

.widget-sidebar-resizer:hover::after,
.widget-sidebar-resizer:focus-visible::after {
  background: var(--accent);
}

.widget-sidebar-resize-layer {
  position: fixed;
  inset: 0;
  z-index: 120;
  cursor: col-resize;
  background: transparent;
  touch-action: none;
}

.editor-surface-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.editor-mode-switch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: var(--r-md);
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.12s ease;
}

.editor-mode-switch:hover {
  color: var(--accent);
}

.editor-mode-switch:focus-visible {
  outline: none;
  color: var(--accent);
}

.editor-slide-scroll {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.editor-slide-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}

.markdown-editor {
  width: 100%;
  min-height: 58vh;
  resize: vertical;
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1.65;
  padding: 18px 20px;
  background: var(--paper-2);
  color: var(--ink);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  outline: none;
  tab-size: 2;
  box-shadow: inset 0 1px 0 rgba(11, 13, 16, 0.03);
}

.markdown-editor:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(13, 59, 128, 0.08);
}

.widget-drop-active {
  outline: 2px dashed var(--accent, #0d3b80);
  outline-offset: -8px;
  background: rgba(13, 59, 128, 0.025);
}

.widget-drop-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 24px;
  z-index: 40;
}

.widget-drop-overlay-card {
  background: var(--paper);
  border: 1px solid var(--accent, #0d3b80);
  border-radius: var(--r-md);
  padding: 8px 14px;
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
  box-shadow: var(--shadow-2);
}
</style>
