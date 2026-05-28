<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import Icon from "@/components/Icon.vue";
import WidgetThumbnail from "@/components/WidgetThumbnail.vue";
import { ApiError } from "@/api/client";
import { widgetsApi } from "@/api/widgets";
import { useWidgetsStore } from "@/stores/widgets";
import type { Deck, Slide, Section, Widget } from "@/api/types";

const props = defineProps<{
  deck: Deck;
  activeSlideId: string | null;
  tab: "sections" | "widgets" | "theme";
}>();
const emit = defineEmits<{
  (e: "collapse"): void;
  (e: "set-tab", t: "sections" | "widgets" | "theme"): void;
  (e: "select-slide", id: string): void;
  (e: "delete-slide", id: string): void;
  (e: "add-slide-after", id: string): void;
  (e: "add-slide-to-section", sectionId: string): void;
  (e: "reorder-slides", order: { id: string; section_id: string | null }[]): void;
  (e: "create-section", title: string): void;
  (e: "rename-section", payload: { id: string; title: string }): void;
  (e: "delete-section", id: string): void;
  (e: "reorder-sections", orderedIds: string[]): void;
}>();

// Widget-library tab — workspace-wide list rendered as draggable thumbnails.
const widgetsStore = useWidgetsStore();
const widgetsTabQuery = ref("");
const widgetsTabLoading = ref(false);

async function loadWidgetsTab() {
  if (widgetsTabLoading.value) return;
  widgetsTabLoading.value = true;
  try {
    await widgetsStore.fetchCrossDeckList();
    const list = widgetsStore.crossDeck ?? [];
    await widgetsStore.ensureLoaded(list.map((w) => w.id));
  } finally {
    widgetsTabLoading.value = false;
  }
}

onMounted(() => {
  if (props.tab === "widgets") void loadWidgetsTab();
});

watch(
  () => props.tab,
  (t) => {
    if (t === "widgets") void loadWidgetsTab();
  },
);

type SidebarTab = "sections" | "widgets" | "theme";

function onRailClick(t: SidebarTab) {
  // VSCode parity: clicking the icon for the active tab collapses the
  // sidebar; clicking a different tab switches to it. Re-opening (via the
  // collapsed rail) is handled by SidebarCollapsed's select-tab emit.
  if (props.tab === t) {
    emit("collapse");
  } else {
    emit("set-tab", t);
  }
}

function railTabIcon(t: SidebarTab): string {
  if (t === "sections") return "list";
  if (t === "widgets") return "widget";
  return "theme";
}

function railTabLabel(t: SidebarTab): string {
  if (t === "sections") return "Sections";
  if (t === "widgets") return "Widgets";
  return "Theme";
}

// Widget delete confirmation. Mirrors the WidgetCollection flow: first attempt
// is a soft delete; if the backend returns 409 with usage_count, re-prompt as
// a force/cascade delete.
const widgetDelete = ref<{ widget: Widget; usageCount: number | null } | null>(null);
const widgetDeleting = ref<string | null>(null);
const widgetDeleteError = ref<string | null>(null);

function askDeleteWidget(widget: Widget) {
  widgetDelete.value = { widget, usageCount: null };
  widgetDeleteError.value = null;
}

async function doDeleteWidget(force: boolean) {
  const target = widgetDelete.value?.widget;
  if (!target || widgetDeleting.value) return;
  widgetDeleting.value = target.id;
  widgetDeleteError.value = null;
  try {
    await widgetsApi.remove(target.id, { force });
    widgetsStore.invalidate(target.id);
    await loadWidgetsTab();
    widgetDelete.value = null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const detail = (err.body as { detail?: { usage_count?: number } } | undefined)?.detail;
      const count = typeof detail?.usage_count === "number" ? detail.usage_count : null;
      widgetDelete.value = { widget: target, usageCount: count };
    } else {
      widgetDeleteError.value = err instanceof Error ? err.message : "Couldn't delete widget.";
    }
  } finally {
    widgetDeleting.value = null;
  }
}

const filteredCrossDeck = computed(() => {
  // Guard against stores disposed mid-tick (test teardown can null the
  // backing array between an async fetch resolving and the watcher firing).
  const list = widgetsStore.crossDeck ?? [];
  const cache = widgetsStore.cache ?? {};
  const q = widgetsTabQuery.value.trim().toLowerCase();
  const all = list.filter((w) => cache[w.id]);
  if (!q) return all;
  return all.filter(
    (w) =>
      w.name.toLowerCase().includes(q) ||
      w.kind.toLowerCase().includes(q) ||
      (w.description || "").toLowerCase().includes(q),
  );
});

// Split into "this deck" and "other decks" sections so the user can tell
// at a glance which widgets are already local vs. would be copied on drop.
const thisDeckWidgets = computed(() =>
  filteredCrossDeck.value.filter((w) => w.deck_id === props.deck.id),
);
const otherDeckWidgets = computed(() =>
  filteredCrossDeck.value.filter((w) => w.deck_id !== props.deck.id),
);

const canDeleteSlide = computed(() => props.deck.slides.length > 1);

function onSlideDeleteClick(e: MouseEvent, slideId: string) {
  e.stopPropagation();
  if (!canDeleteSlide.value) return;
  emit("delete-slide", slideId);
}

function firstLine(md: string): string {
  for (const line of md.split("\n")) {
    if (line.startsWith("# ")) return line.slice(2).replace(/\*([^*]+)\*/g, "$1");
    if (line.trim()) return line.replace(/\*([^*]+)\*/g, "$1");
  }
  return "Untitled";
}

interface Group {
  section: Section | null;
  slides: Slide[];
}

const grouped = computed<Group[]>(() => {
  const out: Group[] = [];
  const slidesBySection = new Map<string | "none", Slide[]>();
  for (const s of props.deck.slides) {
    const key = s.section_id || "none";
    if (!slidesBySection.has(key)) slidesBySection.set(key, []);
    slidesBySection.get(key)!.push(s);
  }
  for (const sec of props.deck.sections) {
    const slides = slidesBySection.get(sec.id) || [];
    slides.sort((a, b) => a.position - b.position);
    out.push({ section: sec, slides });
  }
  const orphans = slidesBySection.get("none") || [];
  if (orphans.length) {
    orphans.sort((a, b) => a.position - b.position);
    out.push({ section: null, slides: orphans });
  }
  return out;
});

// New section input
const adding = ref(false);
const newTitle = ref("");
const newInput = ref<HTMLInputElement | null>(null);

async function startAddSection() {
  adding.value = true;
  newTitle.value = "";
  await nextTick();
  newInput.value?.focus();
}

function commitAddSection() {
  const title = newTitle.value.trim();
  if (title) emit("create-section", title);
  adding.value = false;
  newTitle.value = "";
}

function cancelAddSection() {
  adding.value = false;
  newTitle.value = "";
}

// Inline rename
const renamingId = ref<string | null>(null);
const renameDraft = ref("");

function startRename(s: Section) {
  renamingId.value = s.id;
  renameDraft.value = s.title;
}

function commitRename(s: Section) {
  const title = renameDraft.value.trim();
  if (title && title !== s.title) {
    emit("rename-section", { id: s.id, title });
  }
  renamingId.value = null;
}

function cancelRename() {
  renamingId.value = null;
}

// Delete with confirmation
const confirmDeleteId = ref<string | null>(null);

function askDelete(id: string) {
  confirmDeleteId.value = id;
}

function confirmDelete() {
  if (confirmDeleteId.value) emit("delete-section", confirmDeleteId.value);
  confirmDeleteId.value = null;
}

// Drag-and-drop reorder (sections)
const draggingId = ref<string | null>(null);
const dropTargetId = ref<string | null>(null);

function onDragStart(e: DragEvent, id: string) {
  draggingId.value = id;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", id);
  }
}

function onDragOver(e: DragEvent, id: string) {
  if (!draggingId.value || draggingId.value === id) return;
  e.preventDefault();
  dropTargetId.value = id;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onDrop(e: DragEvent, targetId: string) {
  e.preventDefault();
  const sourceId = draggingId.value;
  draggingId.value = null;
  dropTargetId.value = null;
  if (!sourceId || sourceId === targetId) return;
  const ids = props.deck.sections.map((s) => s.id);
  const from = ids.indexOf(sourceId);
  const to = ids.indexOf(targetId);
  if (from < 0 || to < 0) return;
  ids.splice(from, 1);
  ids.splice(to, 0, sourceId);
  emit("reorder-sections", ids);
}

function onDragEnd() {
  draggingId.value = null;
  dropTargetId.value = null;
}

// Drag-and-drop reorder (slides)
const draggingSlideId = ref<string | null>(null);
const dropTargetSlideId = ref<string | null>(null);
const dropTargetSectionId = ref<string | null>(null);

function flattenedSlides(): { id: string; section_id: string | null }[] {
  const out: { id: string; section_id: string | null }[] = [];
  for (const g of grouped.value) {
    for (const s of g.slides) {
      out.push({ id: s.id, section_id: g.section?.id ?? null });
    }
  }
  return out;
}

function onSlideDragStart(e: DragEvent, slideId: string) {
  draggingSlideId.value = slideId;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", slideId);
  }
}

function onSlideDragOver(e: DragEvent, slideId: string) {
  if (!draggingSlideId.value || draggingSlideId.value === slideId) return;
  e.preventDefault();
  dropTargetSlideId.value = slideId;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onSlideDrop(e: DragEvent, targetSlideId: string) {
  e.preventDefault();
  e.stopPropagation();
  const sourceId = draggingSlideId.value;
  draggingSlideId.value = null;
  dropTargetSlideId.value = null;
  dropTargetSectionId.value = null;
  if (!sourceId || sourceId === targetSlideId) return;
  const flat = flattenedSlides();
  const fromIdx = flat.findIndex((s) => s.id === sourceId);
  const toIdx = flat.findIndex((s) => s.id === targetSlideId);
  if (fromIdx < 0 || toIdx < 0) return;
  const [moved] = flat.splice(fromIdx, 1);
  // After splice, the target's index shifts when moving down.
  const insertAt = toIdx > fromIdx ? toIdx - 1 : toIdx;
  // Dropping above target → inherit target's section.
  moved.section_id = flat[insertAt].section_id;
  flat.splice(insertAt, 0, moved);
  emit("reorder-slides", flat);
}

function onSectionSlideDragOver(e: DragEvent, sectionId: string | null) {
  if (!draggingSlideId.value || !sectionId) return;
  e.preventDefault();
  dropTargetSectionId.value = sectionId;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onSectionSlideDrop(e: DragEvent, sectionId: string | null) {
  e.preventDefault();
  e.stopPropagation();
  const sourceId = draggingSlideId.value;
  draggingSlideId.value = null;
  dropTargetSlideId.value = null;
  dropTargetSectionId.value = null;
  if (!sourceId || !sectionId) return;
  const flat = flattenedSlides();
  const fromIdx = flat.findIndex((s) => s.id === sourceId);
  if (fromIdx < 0) return;
  const [moved] = flat.splice(fromIdx, 1);
  moved.section_id = sectionId;
  let insertAt = flat.length;
  for (let i = flat.length - 1; i >= 0; i -= 1) {
    if (flat[i].section_id === sectionId) {
      insertAt = i + 1;
      break;
    }
  }
  flat.splice(insertAt, 0, moved);
  emit("reorder-slides", flat);
}

function onSlideDragEnd() {
  draggingSlideId.value = null;
  dropTargetSlideId.value = null;
  dropTargetSectionId.value = null;
}
</script>

<template>
  <div :style="{ display: 'flex', flexDirection: 'row', height: '100%', minHeight: 0 }">
    <!-- VSCode-style vertical icon rail. Each tab is icon-only with a
         native tooltip on hover (via `title`). Active tab gets a left
         accent bar + filled state. -->
    <nav
      class="sidebar-rail"
      aria-label="Editor sidebar tabs"
      :style="{
        width: '44px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '10px 0',
        borderRight: '1px solid var(--rule)',
        flexShrink: 0,
        gap: '4px',
      }"
    >
      <button
        v-for="t in (['sections', 'widgets', 'theme'] as const)"
        :key="t"
        type="button"
        class="sidebar-rail-btn"
        :class="{ active: tab === t }"
        :title="railTabLabel(t)"
        :aria-label="railTabLabel(t)"
        :aria-current="tab === t ? 'page' : undefined"
        @click="onRailClick(t)"
      >
        <Icon :name="railTabIcon(t)" :size="16" />
      </button>
      <span :style="{ flex: 1 }" />
      <button
        type="button"
        class="sidebar-rail-btn"
        title="Collapse sidebar"
        aria-label="Collapse sidebar"
        @click="emit('collapse')"
      >
        <Icon name="chev_left" :size="14" />
      </button>
    </nav>

    <div :style="{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }">
    <div :style="{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '12px 8px 16px' }">
      <template v-if="tab === 'sections'">
        <div
          v-for="g in grouped"
          :key="g.section?.id || 'orphans'"
          :style="{ marginBottom: '10px' }"
          :class="{
            'drop-target': g.section && dropTargetId === g.section.id,
            'section-slide-drop-target': g.section && dropTargetSectionId === g.section.id,
          }"
          @dragover="onSectionSlideDragOver($event, g.section?.id ?? null)"
          @drop="onSectionSlideDrop($event, g.section?.id ?? null)"
        >
          <div
            v-if="g.section"
            class="section-header"
            :draggable="renamingId !== g.section.id"
            @dragstart="onDragStart($event, g.section.id)"
            @dragover="onDragOver($event, g.section.id)"
            @drop="onDrop($event, g.section.id)"
            @dragend="onDragEnd"
          >
            <span class="section-drag-handle" :title="'Drag to reorder'">⠿</span>
            <input
              v-if="renamingId === g.section.id"
              v-model="renameDraft"
              class="section-rename-input"
              :ref="(el) => { if (el) (el as HTMLInputElement).focus(); }"
              @keydown.enter.prevent="commitRename(g.section)"
              @keydown.esc.prevent="cancelRename"
              @blur="commitRename(g.section)"
            />
            <span
              v-else
              class="section-title"
              @dblclick="startRename(g.section)"
              :title="'Double-click to rename'"
            >
              {{ g.section.title }}
            </span>
            <div v-if="renamingId !== g.section.id" class="section-actions">
              <button class="section-icon-btn" @click.stop="emit('add-slide-to-section', g.section.id)" title="Add slide to section">
                <Icon name="plus" :size="11" />
              </button>
              <button class="section-icon-btn" @click="startRename(g.section)" title="Rename">
                <Icon name="edit" :size="11" />
              </button>
              <button class="section-icon-btn" @click="askDelete(g.section.id)" title="Delete section">
                <Icon name="trash" :size="11" />
              </button>
            </div>
          </div>
          <div
            v-else
            :style="{
              padding: '6px 12px',
              fontFamily: 'var(--sans)',
              fontSize: '10px',
              fontWeight: 600,
              color: 'var(--ink-mute)',
              textTransform: 'uppercase',
              letterSpacing: '.16em',
            }"
          >
            Unsectioned
          </div>
          <div
            v-for="s in g.slides"
            :key="s.id"
            class="slide-row"
            :class="{
              'slide-row-active': activeSlideId === s.id,
              'slide-row-drop-target': dropTargetSlideId === s.id,
              'slide-row-dragging': draggingSlideId === s.id,
            }"
            draggable="true"
            @click="emit('select-slide', s.id)"
            @dragstart="onSlideDragStart($event, s.id)"
            @dragover="onSlideDragOver($event, s.id)"
            @drop="onSlideDrop($event, s.id)"
            @dragend="onSlideDragEnd"
          >
            <span class="slide-row-handle" :title="'Drag to reorder'">⠿</span>
            <span class="slide-row-text">{{ firstLine(s.markdown) }}</span>
            <button
              class="slide-row-add"
              title="Add slide below"
              @click.stop="emit('add-slide-after', s.id)"
            >
              <Icon name="plus" :size="12" />
            </button>
            <button
              class="slide-row-delete"
              :disabled="!canDeleteSlide"
              :title="canDeleteSlide ? 'Delete slide' : 'Can’t delete the last slide'"
              @click="onSlideDeleteClick($event, s.id)"
            >
              <Icon name="trash" :size="12" />
            </button>
          </div>
          <button
            v-if="g.section && g.slides.length === 0"
            class="empty-section-add"
            @click.stop="emit('add-slide-to-section', g.section.id)"
          >
            <Icon name="plus" :size="12" /> Add slide
          </button>
        </div>

        <div :style="{ marginTop: '6px', padding: '0 4px' }">
          <input
            v-if="adding"
            ref="newInput"
            v-model="newTitle"
            class="section-rename-input"
            placeholder="Section name"
            @keydown.enter.prevent="commitAddSection"
            @keydown.esc.prevent="cancelAddSection"
            @blur="commitAddSection"
          />
          <button v-else class="section-add-btn" @click="startAddSection">
            <Icon name="plus" :size="12" /> Section
          </button>
        </div>
      </template>

      <template v-else-if="tab === 'widgets'">
        <div class="widgets-tab" data-testid="sidebar-widgets-tab">
          <input
            v-model="widgetsTabQuery"
            class="widgets-tab-search"
            placeholder="Search widgets…"
            aria-label="Filter widgets"
          />
          <p v-if="widgetsTabLoading && !filteredCrossDeck.length" class="widgets-tab-empty">Loading…</p>
          <p
            v-else-if="!widgetsTabLoading && !filteredCrossDeck.length"
            class="widgets-tab-empty"
          >
            {{ widgetsTabQuery ? "No widgets match." : "No widgets yet. Generate one in the right sidebar." }}
          </p>
          <template v-else>
            <section v-if="thisDeckWidgets.length" data-testid="widgets-section-this-deck">
              <h4 class="widgets-tab-section-title">This deck</h4>
              <div class="widgets-tab-grid">
                <WidgetThumbnail
                  v-for="w in thisDeckWidgets"
                  :key="w.id"
                  :widget="widgetsStore.cache[w.id]"
                  :current-deck-id="props.deck.id"
                  @delete="askDeleteWidget"
                />
              </div>
            </section>
            <section v-if="otherDeckWidgets.length" data-testid="widgets-section-other-decks">
              <h4 class="widgets-tab-section-title">Other decks</h4>
              <div class="widgets-tab-grid">
                <WidgetThumbnail
                  v-for="w in otherDeckWidgets"
                  :key="w.id"
                  :widget="widgetsStore.cache[w.id]"
                  :current-deck-id="props.deck.id"
                  @delete="askDeleteWidget"
                />
              </div>
            </section>
          </template>
          <p class="widgets-tab-hint">Drag a widget onto the slide canvas to insert it.</p>
        </div>
      </template>

      <template v-else>
        <div :style="{ padding: '8px 12px' }">
          <div
            :style="{
              border: '1px solid var(--ink)',
              borderRadius: 'var(--r-md)',
              padding: '12px',
              background: 'var(--paper)',
            }"
          >
            <div :style="{ fontFamily: 'var(--serif)', fontSize: '15px', marginBottom: '2px' }">Editorial Press</div>
            <div :style="{ fontSize: '11px', color: 'var(--ink-soft)' }">Selected · v 0.1</div>
          </div>
          <div
            v-for="t in ['Studio Noir', 'Garden Print']"
            :key="t"
            :style="{
              border: '1px solid var(--rule)',
              borderRadius: 'var(--r-md)',
              padding: '12px',
              marginTop: '8px',
              background: 'var(--paper)',
              opacity: 0.55,
            }"
          >
            <div :style="{ fontFamily: 'var(--serif)', fontSize: '15px', marginBottom: '2px' }">{{ t }}</div>
            <div :style="{ fontSize: '11px', color: 'var(--ink-soft)' }">Preview only</div>
          </div>
        </div>
      </template>
    </div>

    <div :style="{ padding: '10px 16px', borderTop: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between' }">
      <span class="t-mono" :style="{ color: 'var(--ink-mute)' }">v 0.1</span>
    </div>
    </div>

    <div
      v-if="confirmDeleteId"
      class="section-confirm-backdrop"
      @click.self="confirmDeleteId = null"
    >
      <div class="section-confirm-modal scale-in">
        <h3>Delete section?</h3>
        <p>Slides in this section will be kept (unsectioned). The section itself will be removed.</p>
        <div class="section-confirm-actions">
          <button class="btn btn-sm" @click="confirmDeleteId = null">Cancel</button>
          <button class="btn btn-sm btn-danger" @click="confirmDelete">Delete</button>
        </div>
      </div>
    </div>

    <div
      v-if="widgetDelete"
      data-testid="widget-delete-modal"
      class="section-confirm-backdrop"
      @click.self="widgetDeleting ? null : (widgetDelete = null)"
    >
      <div class="section-confirm-modal scale-in">
        <h3>Delete <em>{{ widgetDelete.widget.name }}</em>?</h3>
        <p v-if="widgetDelete.usageCount === null">
          This removes the widget from your workspace library. Slides that currently use it will lose
          the embedded interaction. Past session logs are preserved.
        </p>
        <p v-else>
          This widget is currently placed on <strong>{{ widgetDelete.usageCount }} slide{{ widgetDelete.usageCount === 1 ? '' : 's' }}</strong>.
          Deleting it will detach the widget from every slide and remove it from your library. This can't be undone.
        </p>
        <p v-if="widgetDeleteError" class="widget-delete-error">{{ widgetDeleteError }}</p>
        <div class="section-confirm-actions">
          <button class="btn btn-sm" :disabled="!!widgetDeleting" @click="widgetDelete = null">Cancel</button>
          <button
            class="btn btn-sm btn-danger"
            :disabled="!!widgetDeleting"
            @click="doDeleteWidget(widgetDelete.usageCount !== null)"
          >
            {{ widgetDeleting ? 'Deleting…' : widgetDelete.usageCount === null ? 'Delete' : 'Detach & delete' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 6px 6px;
  border-radius: var(--r-sm);
  cursor: grab;
}
.section-header[draggable="true"]:active {
  cursor: grabbing;
}
.section-header:hover {
  background: var(--paper);
}
.section-drag-handle {
  color: var(--ink-mute);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.15s ease;
  user-select: none;
}
.section-header:hover .section-drag-handle {
  opacity: 1;
}
.section-title {
  flex: 1;
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 600;
  color: var(--ink-mute);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  cursor: text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.section-rename-input {
  flex: 1;
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 600;
  color: var(--ink);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  background: var(--paper);
  border: 1px solid var(--accent);
  border-radius: var(--r-xs);
  padding: 3px 6px;
  outline: none;
  width: 100%;
}
.section-actions {
  display: inline-flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.section-header:hover .section-actions {
  opacity: 1;
}
.section-icon-btn {
  background: transparent;
  border: none;
  color: var(--ink-mute);
  padding: 3px;
  border-radius: var(--r-xs);
  cursor: pointer;
  line-height: 0;
}
.section-icon-btn:hover {
  background: var(--paper-2);
  color: var(--ink);
}
.section-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px dashed var(--rule);
  border-radius: var(--r-sm);
  padding: 6px 10px;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-soft);
  cursor: pointer;
  width: 100%;
  justify-content: center;
}
.section-add-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.drop-target > .section-header {
  border-top: 2px solid var(--accent);
}
.section-slide-drop-target {
  border-radius: var(--r-sm);
  outline: 1px dashed var(--accent);
  outline-offset: 2px;
}

.slide-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 8px 8px 6px;
  border-left: 2px solid transparent;
  border-top: 2px solid transparent;
  border-radius: var(--r-sm);
  cursor: pointer;
}
.slide-row[draggable="true"]:active {
  cursor: grabbing;
}
.slide-row-active {
  background: var(--paper);
  border-left-color: var(--ink);
}
.slide-row:hover:not(.slide-row-active) {
  background: var(--paper);
}
.slide-row-drop-target {
  border-top-color: var(--accent);
}
.slide-row-dragging {
  opacity: 0.45;
}
.slide-row-handle {
  color: var(--ink-mute);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.4;
  opacity: 0;
  transition: opacity 0.15s ease;
  user-select: none;
  flex-shrink: 0;
  padding-top: 1px;
}
.slide-row:hover .slide-row-handle {
  opacity: 1;
}
.slide-row-text {
  flex: 1;
  font-family: var(--serif);
  font-size: 13.5px;
  line-height: 1.35;
  color: var(--ink);
  font-weight: 400;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.slide-row-active .slide-row-text {
  font-weight: 500;
}
.slide-row-delete {
  background: transparent;
  border: none;
  color: var(--ink-mute);
  padding: 3px;
  border-radius: var(--r-xs);
  line-height: 0;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}
.slide-row-add {
  background: transparent;
  border: none;
  color: var(--ink-mute);
  padding: 3px;
  border-radius: var(--r-xs);
  line-height: 0;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}
.slide-row:hover .slide-row-add {
  opacity: 1;
}
.slide-row-add:hover {
  background: var(--paper-2);
  color: var(--accent);
}
.slide-row:hover .slide-row-delete:not(:disabled) {
  opacity: 1;
}
.slide-row-delete:hover:not(:disabled) {
  background: var(--paper-2);
  color: var(--err);
}
.slide-row-delete:disabled {
  cursor: not-allowed;
}
.empty-section-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: calc(100% - 16px);
  margin: 4px 8px 8px;
  padding: 7px 10px;
  border: 1px dashed var(--rule);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 12px;
  cursor: pointer;
}
.empty-section-add:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--paper);
}

.section-confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  background: rgba(11, 13, 16, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.section-confirm-modal {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 18px;
  width: 360px;
  box-shadow: var(--shadow-3);
}
.section-confirm-modal h3 {
  margin: 0 0 8px;
  font-family: var(--serif);
  font-size: 17px;
  color: var(--ink);
}
.section-confirm-modal p {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--ink-soft);
  font-family: var(--sans);
  line-height: 1.5;
}
.section-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn-danger {
  background: var(--err, #c2410c);
  color: var(--paper);
  border: 1px solid var(--err, #c2410c);
}
.btn-danger:hover {
  filter: brightness(0.95);
}

.sidebar-rail-btn {
  position: relative;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  border-radius: var(--r-sm);
  color: var(--ink-mute);
  cursor: pointer;
  transition: color 120ms ease, background 120ms ease;
}

.sidebar-rail-btn:hover {
  color: var(--ink);
  background: var(--paper);
}

.sidebar-rail-btn.active {
  color: var(--ink);
  background: var(--paper);
}

.sidebar-rail-btn.active::before {
  content: "";
  position: absolute;
  left: -6px;
  top: 4px;
  bottom: 4px;
  width: 2px;
  border-radius: 1px;
  background: var(--accent, #0d3b80);
}

.widgets-tab {
  padding: 4px 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.widgets-tab-search {
  width: 100%;
  padding: 6px 8px;
  font-family: var(--sans);
  font-size: 12px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper);
  color: var(--ink);
}

.widgets-tab-search:focus {
  outline: none;
  border-color: var(--ink);
}

.widgets-tab-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.widgets-tab-section-title {
  margin: 4px 0 6px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute);
}

.widgets-tab-empty {
  margin: 16px 0;
  text-align: center;
  font-size: 11px;
  color: var(--ink-mute);
  font-style: italic;
}

.widgets-tab-hint {
  margin: 4px 0 0;
  font-size: 10px;
  color: var(--ink-mute);
  font-family: var(--mono);
  text-align: center;
  letter-spacing: 0.05em;
}

.widget-delete-error {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--err);
}
</style>
