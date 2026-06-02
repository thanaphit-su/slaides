<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { llmApi } from "@/api/llm";
import { workspaceApi } from "@/api/workspace";
import { widgetsApi } from "@/api/widgets";
import { ApiError } from "@/api/client";
import { useWidgetsStore } from "@/stores/widgets";
import Icon from "@/components/Icon.vue";
import PropsForm from "@/components/PropsForm.vue";
import WidgetFrame from "@/widgets/WidgetFrame.vue";

import { loadRecentPrompts, pushRecentPrompt } from "@/widgets/recent-prompts";
import { sanitiseBehavior } from "@/widgets/behavior";
import { validateDraftJs } from "@/widgets/draft-js";
import { extractPreviewFields, sanitizeStreamingHtml, type StreamingPreviewFields } from "@/widgets/streaming-parser";
import type { SlideWidgetEmbed, Widget, WidgetAiMessage, WidgetAiThread, WidgetSummary, Workspace } from "@/api/types";

const props = defineProps<{
  disabled?: boolean;
  disabledReason?: string;
  initialTab?: "library" | "generate" | "props" | "code";
  mode?: "create" | "adjust";
  placement?: SlideWidgetEmbed | null;
  /** Widgets v2 — widgets are deck-local. The library popover lists widgets
   * in this deck only; the cross-deck picker reads from the workspace-wide
   * list. */
  deckId?: string | null;
  /** 1-based slide index for the breadcrumb (e.g. 3 → "WIDGETS · 03"). */
  slideNumber?: number | null;
  /** Preview-mode markup — when set, the composer prepends a `re: <selector "text">`
   * line to the LLM prompt so the model has context about which element the
   * user means. Cleared via the chip's × button (emits clear-selected-target). */
  selectedTarget?: { selector: string; tag: string; classes: string[]; text: string } | null;
  /** Optional callback that performs the placement-props PATCH. When provided
   * we use this instead of the legacy `save-placement-props` emit, because
   * the callback returns a Promise — so we can catch the 409
   * `edit_requires_reset` and prompt the reset-confirm modal. The opts arg
   * carries the resetState flag the modal injects on confirm. */
  onPatchPlacementProps?: (
    payload: { placement_id: string; props: Record<string, unknown> },
    opts: { resetState?: boolean },
  ) => Promise<void>;
}>();
const emit = defineEmits<{
  (e: "pick", widget: WidgetSummary): void;
  (e: "close"): void;
  (e: "deleted", widgetId: string): void;
  (e: "applied", widgetId: string): void;
  (e: "save-placement-props", payload: { placement_id: string; props: Record<string, unknown> }): void;
  (e: "clear-selected-target"): void;
}>();

const widgets = useWidgetsStore();
const tab = ref<"library" | "generate" | "props" | "code">(props.initialTab || "library");
const codeTab = ref<"html" | "js" | "css">("html");
const query = ref("");
const composer = ref("");
const composerInput = ref<HTMLTextAreaElement | null>(null);
const thread = ref<HTMLElement | null>(null);
const generating = ref(false);
const streamingMessageId = ref<string | null>(null);
const streamedChars = ref(0);
const streamTail = ref("");
const streamingDraftFields = ref<{ html: string | null; css: string | null; name: string | null; kind: string | null } | null>(null);
const currentAbort = ref<AbortController | null>(null);
const error = ref<string | null>(null);
const savingMessageId = ref<string | null>(null);
const deleting = ref<string | null>(null);
const deleteError = ref<string | null>(null);
const confirmDelete = ref<{ widget: WidgetSummary; usageCount: number | null } | null>(null);
const workspace = ref<Workspace | null>(null);
const imageInput = ref<HTMLInputElement | null>(null);
const codeHtml = ref("");
const codeJs = ref("");
const codeCss = ref("");
const savingCode = ref(false);
const codeError = ref<string | null>(null);
const codeSaved = ref<string | null>(null);
// Props tab: local draft of the placement's per-instance props. Synced from
// `props.placement.props` whenever the placement changes; flushed to the
// server by clicking Save.
const propsDraft = ref<Record<string, unknown>>({});
const savingProps = ref(false);
const propsError = ref<string | null>(null);
const propsSaved = ref<string | null>(null);
// Copy-from-another-deck picker state. The widgets.crossDeck list comes from
// the workspace-wide endpoint and includes the current deck's widgets too;
// the candidate computed below filters this deck out.
const showCopyPicker = ref(false);
const copyPickerLoading = ref(false);
const copyingWidgetId = ref<string | null>(null);
const copyError = ref<string | null>(null);

// Bottom-toolbar popovers + composer focus state for the footer status line.
const libraryOpen = ref(false);
const workflowModeMenuOpen = ref(false);
const composerFocused = ref(false);
const libraryAnchor = ref<HTMLElement | null>(null);
const libraryPopover = ref<HTMLElement | null>(null);
const workflowModeAnchor = ref<HTMLElement | null>(null);
const workflowModePopover = ref<HTMLElement | null>(null);

// Recent prompts surfaced in the empty state (most recent first, capped at 5).
const recentPrompts = ref<string[]>([]);

type WidgetWorkflowMode = "clarify_first" | "build_now";
const workflowMode = ref<WidgetWorkflowMode>("build_now");
const workflowModeLabel = computed(() => workflowMode.value === "clarify_first" ? "Clarify first" : "Build now");

// Reset-confirm modal — surfaces the 409 `edit_requires_reset` flow from the
// server when the user tries to edit a widget that's actively aggregating
// audience contributions. Confirm re-runs the same operation with
// `resetState: true`; cancel rolls back.
interface ResetConfirm {
  openSessionCount: number;
  openPlacementCount: number;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  pending: boolean;
}
const resetConfirm = ref<ResetConfirm | null>(null);
const isUserNearBottom = ref(true);
const SCROLL_THRESHOLD_PX = 150;
let autoScrollRafId: number | null = null;
let isUnmounted = false;

/** Wraps a PATCH-like operation in the reset-confirm flow. Calls `op` once.
 *  If the server returns 409 `edit_requires_reset`, opens the modal and
 *  re-runs `op({ resetState: true })` on confirm. Resolves to whatever the
 *  successful call returned, or rejects with the underlying error. */
async function withResetConfirm<T>(
  op: (opts: { resetState?: boolean }) => Promise<T>,
): Promise<T> {
  try {
    return await op({});
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 409) throw err;
    const detail = (err.body as { detail?: { error?: string; open_session_count?: number; open_placement_count?: number } } | undefined)?.detail;
    if (detail?.error !== "edit_requires_reset") throw err;
    return await new Promise<T>((resolve, reject) => {
      resetConfirm.value = {
        openSessionCount: detail.open_session_count ?? 1,
        openPlacementCount: detail.open_placement_count ?? 1,
        pending: false,
        onCancel: () => {
          resetConfirm.value = null;
          reject(err);
        },
        onConfirm: async () => {
          if (!resetConfirm.value) return;
          resetConfirm.value.pending = true;
          try {
            const result = await op({ resetState: true });
            resetConfirm.value = null;
            resolve(result);
          } catch (retryErr) {
            resetConfirm.value = null;
            reject(retryErr);
          }
        },
      };
    });
  }
}

interface AttachedImage {
  id: string;
  name: string;
  mime_type: string;
  data_url: string;
}
const attachedImages = ref<AttachedImage[]>([]);

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  draft?: Partial<Widget>;
  applied?: boolean;
  appliedFromDraftNumber?: number;
  appliedFromMessageId?: string;
  raw?: string;
  images?: AttachedImage[];
  question?: WidgetWorkflowQuestion;
  plan?: string[];
  reflection?: string;
  // Post-stream warnings from the backend validators (_scan_behavior_violations,
  // _scan_theme_violations, _scan_props_contract_violations, _scan_layout_violations).
  // Non-blocking — the user can apply anyway.
  warnings?: string[];
}

const messages = ref<ChatMessage[]>([]);
const aiThread = ref<WidgetAiThread | null>(null);

interface WidgetWorkflowOption {
  id: string;
  label: string;
  value?: Record<string, unknown>;
}

interface WidgetWorkflowQuestion {
  question: string;
  options: WidgetWorkflowOption[];
}

type WidgetWorkflow =
  | { type: "question"; question: string; options: WidgetWorkflowOption[] }
  | { type: "plan" | "step" | "reflection"; plan?: string[]; reflection?: string }
  | {
      type: "draft";
      plan?: string[];
      reflection?: string;
      widget: Partial<Widget>;
      ai_spec?: Record<string, unknown>;
      example_props?: Record<string, unknown>;
    };

const WIDGET_REPAIR_MAX_ATTEMPTS = 3;
const LOADING_GRIP_CIRCLES = [
  { cx: 19, cy: 5 },
  { cx: 19, cy: 12 },
  { cx: 12, cy: 5 },
  { cx: 19, cy: 19 },
  { cx: 12, cy: 12 },
  { cx: 5, cy: 5 },
  { cx: 12, cy: 19 },
  { cx: 5, cy: 12 },
  { cx: 5, cy: 19 },
];

const latestDraft = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const draft = messages.value[i].draft;
    if (draft) return draft;
  }
  return null;
});

const pendingWorkflowQuestion = ref<(WidgetWorkflowQuestion & { messageId: string }) | null>(null);
const customClarificationAnswer = ref("");

const adjusting = computed(() => props.mode === "adjust" && !!props.placement);
const targetWidget = computed(() => props.placement ? widgets.cache[props.placement.widget_id] : null);
const hasWidgetCode = computed(() => !!props.placement);
const hasProps = computed(() => {
  const w = targetWidget.value;
  if (!w) return false;
  const schema = w.props_schema as Record<string, unknown> | undefined;
  if (!schema || typeof schema !== "object") return false;
  const properties = (schema.properties as Record<string, unknown> | undefined) || schema;
  return properties && typeof properties === "object" && Object.keys(properties).length > 0;
});
// Library is a popover now — only Generate/Props/Code are tab navigation.
// In create mode there's no tab strip at all (Generate is implicit).
const availableTabs = computed<Array<"library" | "generate" | "props" | "code">>(() => {
  if (!props.placement) return ["generate"];
  return hasProps.value ? ["generate", "props", "code"] : ["generate", "code"];
});
const widgetGenerationDisabled = computed(
  () => workspace.value !== null && !workspace.value.llm_capability_models?.widget_generate,
);
const chatDisabled = computed(() => (props.disabled && !adjusting.value) || widgetGenerationDisabled.value);
const widgetModel = computed(() => {
  const ws = workspace.value;
  if (!ws) return null;
  const modelId = ws.llm_capability_models?.widget_generate;
  return ws.llm_models.find((model) => model.id === modelId) || null;
});
const widgetModelSupportsImages = computed(() => !!widgetModel.value?.supports_image_input);
const currentCode = computed({
  get() {
    if (codeTab.value === "html") return codeHtml.value;
    if (codeTab.value === "js") return codeJs.value;
    return codeCss.value;
  },
  set(value: string) {
    codeError.value = null;
    codeSaved.value = null;
    if (codeTab.value === "html") codeHtml.value = value;
    else if (codeTab.value === "js") codeJs.value = value;
    else codeCss.value = value;
  },
});
const codeDirty = computed(() => {
  const w = targetWidget.value;
  if (!w) return false;
  return codeHtml.value !== (w.html || "") || codeJs.value !== (w.js || "") || codeCss.value !== (w.css || "");
});
const propsSchema = computed<Record<string, unknown>>(() => {
  const raw = targetWidget.value?.props_schema;
  return (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
});
const propsDirty = computed(() => {
  return JSON.stringify(propsDraft.value) !== JSON.stringify(props.placement?.props || {});
});
const composerPlaceholder = computed(() => {
  if (adjusting.value) return "Iterate on this widget…";
  return messages.value.some((m) => m.role === "user") ? "Iterate on this widget…" : "Ask for a widget…";
});

const slideLabel = computed(() => {
  const n = props.slideNumber;
  return typeof n === "number" && n > 0 ? String(n).padStart(2, "0") : null;
});

const showEmptyState = computed(
  () => !adjusting.value && !messages.value.some((m) => m.role === "user"),
);

const conversationActive = computed(
  () => messages.value.some((m) => m.role === "user") || adjusting.value,
);

function welcomeText(): string {
  return adjusting.value
    ? "Tell me what to change about the current widget. I’ll draft an adjustment you can apply in place."
    : "Describe the widget you want. I can generate a draft, then revise it as you ask for changes.";
}

onMounted(() => {
  if (props.deckId) {
    void widgets.fetchListForDeck(props.deckId);
  } else {
    widgets.reset();
  }
  recentPrompts.value = loadRecentPrompts();
  void loadWorkspaceSettings();
  document.addEventListener("mousedown", onDocumentMouseDown, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("mousedown", onDocumentMouseDown, true);
  isUnmounted = true;
  currentAbort.value?.abort();
  if (autoScrollRafId !== null) {
    cancelAnimationFrame(autoScrollRafId);
    autoScrollRafId = null;
  }
});

function onDocumentMouseDown(e: MouseEvent) {
  const target = e.target as Node | null;
  if (!target) return;
  if (libraryOpen.value && libraryPopover.value && libraryAnchor.value) {
    if (!libraryPopover.value.contains(target) && !libraryAnchor.value.contains(target)) {
      libraryOpen.value = false;
    }
  }
  if (workflowModeMenuOpen.value && workflowModePopover.value && workflowModeAnchor.value) {
    if (!workflowModePopover.value.contains(target) && !workflowModeAnchor.value.contains(target)) {
      workflowModeMenuOpen.value = false;
    }
  }
}

function toggleLibrary() {
  libraryOpen.value = !libraryOpen.value;
  if (libraryOpen.value) workflowModeMenuOpen.value = false;
}

function toggleWorkflowModeMenu() {
  workflowModeMenuOpen.value = !workflowModeMenuOpen.value;
  if (workflowModeMenuOpen.value) libraryOpen.value = false;
}

function setWorkflowMode(mode: WidgetWorkflowMode) {
  workflowMode.value = mode;
  workflowModeMenuOpen.value = false;
}

function pickRecentPrompt(text: string) {
  composer.value = text;
  void nextTick(() => {
    resizeComposer();
    composerInput.value?.focus();
  });
}

function openCodeFromDraft() {
  if (props.placement) tab.value = "code";
}

watch(
  () => props.deckId,
  (id) => {
    if (id) void widgets.fetchListForDeck(id);
    else widgets.reset();
  },
);

async function loadWorkspaceSettings() {
  try {
    workspace.value = await workspaceApi.get();
  } catch {
    workspace.value = null;
  }
}

watch(
  () => props.placement?.widget_id,
  async (id) => {
    if (id) {
      await widgets.fetchOne(id);
      await loadAiThread(id);
    } else {
      aiThread.value = null;
    }
  },
  { immediate: true },
);

watch(
  [() => props.mode, () => props.placement?.widget_id] as const,
  ([mode, widgetId], [previousMode, previousWidgetId]) => {
    if (mode !== previousMode || widgetId !== previousWidgetId) {
      clearConversation();
    }
  },
);

watch(
  () => targetWidget.value?.id,
  () => {
    const w = targetWidget.value;
    codeHtml.value = w?.html || "";
    codeJs.value = w?.js || "";
    codeCss.value = w?.css || "";
    codeError.value = null;
    codeSaved.value = null;
  },
  { immediate: true },
);

watch(
  () => [props.placement?.placement_id, props.placement?.props] as const,
  () => {
    propsDraft.value = JSON.parse(JSON.stringify(props.placement?.props || {}));
    propsError.value = null;
    propsSaved.value = null;
  },
  { immediate: true, deep: true },
);

watch(
  () => props.initialTab,
  (next) => {
    if (next) tab.value = next;
  },
);

watch(
  availableTabs,
  (tabs) => {
    if (!tabs.includes(tab.value)) {
      // In adjust mode, the props form is the most likely thing the user wants
      // to touch first — defer to it whenever the widget exposes any props.
      if (adjusting.value && tabs.includes("props")) tab.value = "props";
      else tab.value = "generate";
    }
  },
  { immediate: true },
);

const filtered = computed(() =>
  widgets.summaries.filter(
    (w) =>
      w.name.toLowerCase().includes(query.value.toLowerCase()) ||
      w.kind.toLowerCase().includes(query.value.toLowerCase()),
  ),
);

const copyCandidates = computed(() =>
  widgets.crossDeck.filter((w) => w.deck_id !== props.deckId),
);

async function openCopyPicker() {
  copyError.value = null;
  showCopyPicker.value = true;
  if (copyPickerLoading.value) return;
  copyPickerLoading.value = true;
  try {
    await widgets.fetchCrossDeckList();
  } catch (err) {
    copyError.value = err instanceof Error ? err.message : "Couldn't load other widgets.";
  } finally {
    copyPickerLoading.value = false;
  }
}

async function copyFromAnotherDeck(source: WidgetSummary) {
  if (!props.deckId) return;
  copyError.value = null;
  copyingWidgetId.value = source.id;
  try {
    await widgetsApi.copyIntoDeck(props.deckId, source.id);
    await widgets.fetchListForDeck(props.deckId);
    showCopyPicker.value = false;
  } catch (err) {
    copyError.value = err instanceof Error ? err.message : "Couldn't copy widget.";
  } finally {
    copyingWidgetId.value = null;
  }
}

async function duplicateInDeck(widget: WidgetSummary) {
  // Same-deck variant of `copyFromAnotherDeck`: clones a widget that
  // already belongs to this deck. The backend appends a " (copy)" /
  // " (copy 2)" suffix to keep names unique inside the library.
  if (!props.deckId) return;
  copyError.value = null;
  copyingWidgetId.value = widget.id;
  try {
    await widgetsApi.copyIntoDeck(props.deckId, widget.id);
    await widgets.fetchListForDeck(props.deckId);
  } catch (err) {
    copyError.value = err instanceof Error ? err.message : "Couldn't duplicate widget.";
  } finally {
    copyingWidgetId.value = null;
  }
}

function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match ? match[1].trim() : trimmed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normaliseWidgetDraft(parsed: Partial<Widget>, workflow: Extract<WidgetWorkflow, { type: "draft" }>): Partial<Widget> {
  const draft: Partial<Widget> = {};
  if (typeof parsed.name === "string") draft.name = parsed.name.slice(0, 80);
  if (typeof parsed.kind === "string") draft.kind = parsed.kind.slice(0, 60);
  if (typeof parsed.description === "string") draft.description = parsed.description.slice(0, 600);
  if (typeof parsed.html === "string") draft.html = parsed.html;
  if (parsed.js !== undefined) draft.js = parsed.js == null ? null : String(parsed.js);
  if (parsed.css !== undefined) draft.css = parsed.css == null ? null : String(parsed.css);
  if (parsed.props_schema && typeof parsed.props_schema === "object") draft.props_schema = parsed.props_schema;
  if (Array.isArray(parsed.tags)) draft.tags = parsed.tags.map(String).slice(0, 8);

  const parsedBehavior = sanitiseBehavior((parsed as Record<string, unknown>).behavior);
  if (parsedBehavior) draft.behavior = parsedBehavior as Widget["behavior"];
  if (workflow.ai_spec && typeof workflow.ai_spec === "object") draft.ai_spec = workflow.ai_spec;
  if (workflow.example_props && typeof workflow.example_props === "object") draft.example_props = workflow.example_props;

  if (adjusting.value) return draft;
  return {
    name: draft.name || "Generated widget",
    kind: draft.kind || "custom",
    description: draft.description || "Generated widget draft.",
    html: draft.html || "",
    js: draft.js ?? null,
    css: draft.css ?? null,
    props_schema: draft.props_schema || {},
    tags: draft.tags || ["ai-generated"],
    ...(draft.behavior ? { behavior: draft.behavior } : {}),
    ...(draft.ai_spec ? { ai_spec: draft.ai_spec } : {}),
    ...(draft.example_props ? { example_props: draft.example_props } : {}),
  };
}

function parseWidgetWorkflow(text: string): WidgetWorkflow {
  const parsed = JSON.parse(stripCodeFence(text)) as unknown;
  if (!isRecord(parsed)) throw new Error("workflow response must be an object");
  if (parsed.type === "question") {
    if (typeof parsed.question !== "string") throw new Error("question response requires question");
    if (!Array.isArray(parsed.options) || parsed.options.length === 0) {
      throw new Error("question response requires options");
    }
    const options = parsed.options
      .filter(isRecord)
      .map((option) => ({
        id: String(option.id || option.label || ""),
        label: String(option.label || option.id || ""),
        ...(isRecord(option.value) ? { value: option.value } : {}),
      }))
      .filter((option) => option.id && option.label);
    if (!options.length) throw new Error("question response requires options");
    return { type: "question", question: parsed.question, options };
  }
  if (parsed.type === "draft") {
    if (!isRecord(parsed.widget)) throw new Error("draft response requires widget");
    const workflow: Extract<WidgetWorkflow, { type: "draft" }> = {
      type: "draft",
      widget: parsed.widget as Partial<Widget>,
      ...(Array.isArray(parsed.plan) ? { plan: parsed.plan.map(String) } : {}),
      ...(typeof parsed.reflection === "string" ? { reflection: parsed.reflection } : {}),
      ...(isRecord(parsed.ai_spec) ? { ai_spec: parsed.ai_spec } : {}),
      ...(isRecord(parsed.example_props) ? { example_props: parsed.example_props } : {}),
    };
    return { ...workflow, widget: normaliseWidgetDraft(workflow.widget, workflow) };
  }
  if (parsed.type === "plan" || parsed.type === "step" || parsed.type === "reflection") {
    return {
      type: parsed.type,
      ...(Array.isArray(parsed.plan) ? { plan: parsed.plan.map(String) } : {}),
      ...(typeof parsed.step === "string" ? { plan: [parsed.step] } : {}),
      ...(typeof parsed.reflection === "string" ? { reflection: parsed.reflection } : {}),
    };
  }
  throw new Error("workflow response type must be question, plan, step, reflection, or draft");
}

function widgetWorkflowContract(): string {
  if (workflowMode.value === "clarify_first") {
    return "Return a widget workflow envelope. Clarify First mode is active: ask exactly one useful question with 2-4 concrete options. Do not return type=draft. If you need to summarize first, return type=question with the summary in the question text.";
  }
  return adjusting.value
    ? "Return a widget workflow envelope. Build Now mode is active: ask a question only if blocked; otherwise return type=draft with only changed widget fields."
    : "Return a widget workflow envelope. Build Now mode is active: ask a question only if behavior or requirements are blocked; otherwise return type=draft with widget, ai_spec, and example_props.";
}

function clarifyFirstDraftFallback(): Extract<WidgetWorkflow, { type: "question" }> {
  return {
    type: "question",
    question: "Clarify First is on. Build from this direction now, or clarify one more detail first?",
    options: [
      { id: "build_now", label: "Build now", value: { workflow_mode: "build_now" } },
      { id: "clarify_more", label: "Clarify more", value: { workflow_mode: "clarify_first" } },
    ],
  };
}

function looksLikeDraftWorkflowEnvelope(source: string): boolean {
  return /["']type["']\s*:\s*["']draft["']/.test(source);
}

function messageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function workflowOptionsFromContent(content: Record<string, unknown>): WidgetWorkflowOption[] {
  const raw = Array.isArray(content.options) ? content.options : [];
  return raw
    .filter(isRecord)
    .map((option) => ({
      id: String(option.id || option.label || ""),
      label: String(option.label || option.id || ""),
      ...(isRecord(option.value) ? { value: option.value } : {}),
    }))
    .filter((option) => option.id && option.label);
}

function draftNumberForMessage(sourceMessageId: string, list = messages.value): number {
  let count = 0;
  for (const message of list) {
    if (message.draft) count += 1;
    if (message.id === sourceMessageId) return count || 1;
  }
  return Math.max(count, 1);
}

function draftMessageIdForNumber(draftNumber: number, list = messages.value): string | null {
  let count = 0;
  for (const message of list) {
    if (!message.draft) continue;
    count += 1;
    if (count === draftNumber) return message.id;
  }
  return null;
}

function numberFromContent(value: unknown): number | undefined {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : undefined;
}

function decorateAppliedReferences(list: ChatMessage[]): ChatMessage[] {
  const draftIdsByNumber = new Map<number, string>();
  const appliedDraftNumbers = new Set<number>();
  let lastDraftNumber = 0;
  const next = list.map((message) => {
    const copy = { ...message };
    if (copy.draft) {
      lastDraftNumber += 1;
      draftIdsByNumber.set(lastDraftNumber, copy.id);
    }
    if (copy.appliedFromDraftNumber !== undefined && copy.appliedFromDraftNumber <= 0) {
      copy.appliedFromDraftNumber = lastDraftNumber || undefined;
    }
    if (copy.appliedFromDraftNumber !== undefined) {
      appliedDraftNumbers.add(copy.appliedFromDraftNumber);
    }
    return copy;
  });

  for (const message of next) {
    if (message.appliedFromDraftNumber !== undefined) {
      message.appliedFromMessageId = draftIdsByNumber.get(message.appliedFromDraftNumber) || message.appliedFromMessageId;
    }
  }

  let draftNumber = 0;
  return next.map((message) => {
    if (!message.draft) return message;
    draftNumber += 1;
    return appliedDraftNumbers.has(draftNumber) ? { ...message, applied: true } : message;
  });
}

function pendingQuestionFromMessages(list: ChatMessage[]): (WidgetWorkflowQuestion & { messageId: string }) | null {
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const message = list[i];
    if (message.question) return { messageId: message.id, ...message.question };
    if (
      message.role === "user" ||
      message.draft ||
      message.appliedFromDraftNumber !== undefined ||
      message.plan?.length ||
      message.reflection ||
      message.text.trim()
    ) {
      return null;
    }
  }
  return null;
}

function messageFromThread(row: WidgetAiMessage): ChatMessage {
  const content = row.content || {};
  const plan = Array.isArray(content.plan)
    ? content.plan.map(String)
    : Array.isArray(content.steps)
      ? content.steps.map(String)
      : undefined;
  const reflection = typeof content.reflection === "string" ? content.reflection : undefined;
  const questionText = typeof content.question === "string" ? content.question : null;
  const options = workflowOptionsFromContent(content);
  const question = questionText && options.length ? { question: questionText, options } : undefined;
  const isApply = row.message_type === "apply";
  const draft = !isApply && isRecord(content.widget) ? content.widget as Partial<Widget> : undefined;
  const appliedFromDraftNumber = isApply ? numberFromContent(content.applied_from_draft_number) ?? -1 : undefined;
  const appliedFromMessageId = isApply && typeof content.applied_from_message_id === "string"
    ? content.applied_from_message_id
    : undefined;
  const text =
    typeof content.text === "string"
      ? content.text
      : questionText
        ? questionText
        : reflection
          ? reflection
          : row.message_type === "apply"
            ? "Applied to the widget."
            : plan?.length
              ? "AI is planning the next widget change."
              : "";
  return {
    id: row.id,
    role: row.role === "user" ? "user" : "assistant",
    text,
    ...(draft ? { draft } : {}),
    ...(appliedFromDraftNumber !== undefined ? { appliedFromDraftNumber } : {}),
    ...(appliedFromMessageId ? { appliedFromMessageId } : {}),
    ...(question ? { question } : {}),
    ...(plan?.length ? { plan } : {}),
    ...(reflection ? { reflection } : {}),
  };
}

function hydrateThread(threadRow: WidgetAiThread | null) {
  aiThread.value = threadRow;
  if (!adjusting.value) return;
  if (!threadRow?.messages.length) {
    clearConversation();
    return;
  }
  const hydrated = decorateAppliedReferences(threadRow.messages.map(messageFromThread));
  messages.value = hydrated;
  pendingWorkflowQuestion.value = pendingQuestionFromMessages(hydrated);
}

async function loadAiThread(widgetId: string) {
  if (!adjusting.value) {
    aiThread.value = null;
    return;
  }
  try {
    hydrateThread(await widgetsApi.getAiThread(widgetId));
  } catch {
    aiThread.value = null;
  }
}

async function ensureAiThread(widget: Widget): Promise<WidgetAiThread | null> {
  if (aiThread.value?.widget_id === widget.id) return aiThread.value;
  try {
    const existing = await widgetsApi.getAiThread(widget.id);
    if (existing) {
      aiThread.value = existing;
      return existing;
    }
    const created = await widgetsApi.createAiThread(widget.id, {
      title: widget.name,
      compact_summary: isRecord(widget.ai_spec) ? widget.ai_spec : {},
    });
    aiThread.value = created;
    return created;
  } catch {
    return null;
  }
}

async function appendAiThreadMessage(
  widget: Widget,
  body: Parameters<typeof widgetsApi.appendAiMessage>[2],
) {
  const threadRow = await ensureAiThread(widget);
  if (!threadRow) return;
  try {
    const saved = await widgetsApi.appendAiMessage(widget.id, threadRow.id, body);
    aiThread.value = { ...threadRow, messages: [...threadRow.messages, saved] };
  } catch {
    // Chat persistence is non-blocking; the widget save path should still succeed.
  }
}

function workflowThreadContent(workflow: WidgetWorkflow): Record<string, unknown> {
  if (workflow.type === "question") {
    return { question: workflow.question, options: workflow.options };
  }
  if (workflow.type === "draft") {
    return {
      widget: workflow.widget,
      ...(workflow.plan ? { plan: workflow.plan } : {}),
      ...(workflow.reflection ? { reflection: workflow.reflection } : {}),
    };
  }
  return {
    ...(workflow.plan ? { plan: workflow.plan } : {}),
    ...(workflow.reflection ? { reflection: workflow.reflection } : {}),
  };
}

function chatMessageType(message: ChatMessage): string {
  if (message.role === "user") return "user";
  if (message.appliedFromDraftNumber !== undefined) return "apply";
  if (message.question) return "question";
  if (message.draft) return "draft";
  if (message.plan?.length) return "plan";
  if (message.reflection) return "reflection";
  return "assistant";
}

function chatMessageContent(message: ChatMessage): Record<string, unknown> {
  return {
    ...(message.text ? { text: message.text } : {}),
    ...(message.appliedFromDraftNumber !== undefined ? { applied_from_draft_number: message.appliedFromDraftNumber } : {}),
    ...(message.appliedFromMessageId ? { applied_from_message_id: message.appliedFromMessageId } : {}),
    ...(message.question ? { question: message.question.question, options: message.question.options } : {}),
    ...(message.draft && message.appliedFromDraftNumber === undefined ? { widget: message.draft } : {}),
    ...(message.plan?.length ? { plan: message.plan } : {}),
    ...(message.reflection ? { reflection: message.reflection } : {}),
    ...(message.warnings?.length ? { warnings: message.warnings } : {}),
  };
}

async function persistConversationSnapshot(widget: Widget) {
  const rows = messages.value.filter((message) => message.id !== "assistant-welcome");
  for (const message of rows) {
    await appendAiThreadMessage(widget, {
      role: message.role,
      message_type: chatMessageType(message),
      content: chatMessageContent(message),
      revision_id: widget.current_revision_id ?? null,
    });
  }
}

async function scrollThreadToBottom() {
  await nextTick();
  if (thread.value) {
    thread.value.scrollTop = thread.value.scrollHeight;
    isUserNearBottom.value = true;
  }
}

function updateIsUserNearBottom() {
  const el = thread.value;
  if (!el) return;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  isUserNearBottom.value = distanceFromBottom <= SCROLL_THRESHOLD_PX;
}

function onThreadScroll() {
  updateIsUserNearBottom();
}

function queueAutoScrollToBottom(opts: { force?: boolean; smooth?: boolean } = {}) {
  const { force = false, smooth = false } = opts;

  if (!force && !isUserNearBottom.value) return;

  if (autoScrollRafId !== null) cancelAnimationFrame(autoScrollRafId);

  autoScrollRafId = requestAnimationFrame(() => {
    autoScrollRafId = null;
    const el = thread.value;
    if (!el) return;
    if (!force && !isUserNearBottom.value) return;

    if (smooth) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } else {
      el.scrollTop = el.scrollHeight;
    }

    isUserNearBottom.value = true;
  });
}

async function scrollToDraftReference(message: ChatMessage) {
  const sourceId = message.appliedFromMessageId
    || (message.appliedFromDraftNumber !== undefined ? draftMessageIdForNumber(message.appliedFromDraftNumber) : null);
  if (!sourceId || !thread.value) return;
  await nextTick();
  const target = Array.from(thread.value.querySelectorAll<HTMLElement>("[data-message-id]"))
    .find((el) => el.dataset.messageId === sourceId);
  target?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function resizeComposer() {
  const el = composerInput.value;
  if (!el) return;
  el.style.height = "0px";
  el.style.height = `${Math.min(el.scrollHeight, 110)}px`;
}

function readImageFile(file: File): Promise<AttachedImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.onload = () => {
      resolve({
        id: messageId("image"),
        name: file.name,
        mime_type: file.type || "image/png",
        data_url: String(reader.result || ""),
      });
    };
    reader.readAsDataURL(file);
  });
}

async function onAttachImages(e: Event) {
  const input = e.target as HTMLInputElement;
  const files = Array.from(input.files || []).filter((file) => file.type.startsWith("image/"));
  input.value = "";
  if (!files.length) return;
  error.value = null;
  try {
    const remaining = Math.max(0, 6 - attachedImages.value.length);
    const next = await Promise.all(files.slice(0, remaining).map(readImageFile));
    attachedImages.value.push(...next);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not attach image.";
  }
}

function removeAttachedImage(id: string) {
  attachedImages.value = attachedImages.value.filter((image) => image.id !== id);
}

function tabLabel(t: "library" | "generate" | "props" | "code"): string {
  if (t === "library") return "My library";
  if (t === "code") return "Code";
  if (t === "props") return "Props";
  return adjusting.value ? "AI Adjust" : "Generate with AI";
}

function conversationContext(): string {
  return messages.value
    .filter((m) => m.id !== "assistant-welcome")
    .map((m) => {
      const draft = m.draft
        ? `\nDraft JSON: ${JSON.stringify({
            name: m.draft.name,
            kind: m.draft.kind,
            description: m.draft.description,
            html: m.draft.html,
            js: m.draft.js,
            css: m.draft.css,
            props_schema: m.draft.props_schema,
            tags: m.draft.tags,
          })}`
        : "";
      return `${m.role === "user" ? "User" : "Assistant"}: ${m.text}${draft}`;
    })
    .join("\n\n");
}

function resolvedDraft(draft: Partial<Widget>): Partial<Widget> {
  if (!adjusting.value || !targetWidget.value) return draft;
  return { ...targetWidget.value, ...draft };
}

function draftPreviewWidget(draft: Partial<Widget>, fallbackId: string): Widget {
  return {
    id: draft.id || `draft-${fallbackId}`,
    deck_id: draft.deck_id || props.deckId || "draft",
    derived_from_id: draft.derived_from_id ?? null,
    name: draft.name || "Generated widget",
    kind: draft.kind || "custom",
    description: draft.description ?? null,
    html: draft.html || "",
    js: draft.js ?? null,
    css: draft.css ?? null,
    props_schema: draft.props_schema || {},
    tags: draft.tags || [],
    version: draft.version || "draft",
    behavior: draft.behavior || { kind: "quiet" },
    current_revision_id: draft.current_revision_id ?? null,
    example_props: draft.example_props || {},
    ai_spec: draft.ai_spec || {},
  };
}

function draftPreviewProps(draft: Partial<Widget>): Record<string, unknown> {
  return draft.example_props && typeof draft.example_props === "object" ? draft.example_props : {};
}

const streamingPreviewDraft = computed<Partial<Widget> | null>(() => {
  const fields = streamingDraftFields.value;
  if (!fields?.html) return null;
  
  const draft: Partial<Widget> = {
    name: fields.name || undefined,
    kind: fields.kind || undefined,
    html: sanitizeStreamingHtml(fields.html),
    css: null,  // NO CSS during streaming - prevents @import/url() bypasses
    js: null,
    behavior: { kind: "quiet" },
  };
  
  if (adjusting.value && targetWidget.value) {
    return { ...targetWidget.value, ...draft };
  }
  
  return draft;
});

const streamingPreviewWidget = computed<Widget | null>(() => {
  const draft = streamingPreviewDraft.value;
  if (!draft) return null;
  return draftPreviewWidget(draft, "streaming-preview");
});

function validateDraftHtml(html: string): string | null {
  const trimmed = html.trim();
  if (!trimmed) return "AI returned empty HTML.";
  const opens = (trimmed.match(/</g) || []).length;
  const closes = (trimmed.match(/>/g) || []).length;
  if (opens !== closes) return "AI HTML looks truncated. Try regenerating.";
  if (trimmed.length < 24) return "AI HTML is suspiciously short. Try a more specific instruction.";
  return null;
}

function validateWorkflowDraft(workflow: WidgetWorkflow): string | null {
  if (workflow.type !== "draft") return null;
  const draft = workflow.widget;
  if (typeof draft.html === "string") {
    const trimmed = draft.html.trim();
    if (!trimmed) return "AI returned empty HTML.";
    const opens = (trimmed.match(/</g) || []).length;
    const closes = (trimmed.match(/>/g) || []).length;
    if (opens !== closes) return "AI HTML looks truncated. Try regenerating.";
  }
  if (typeof draft.js === "string") {
    const warn = validateDraftJs(draft.js);
    if (warn) return warn;
  }
  return null;
}

function repairPrompt(originalPrompt: string, errorMessage: string): string {
  return [
    "Repair the previous widget response.",
    `Validation failed: ${errorMessage}`,
    "Return only a corrected SLAIDES widget workflow JSON envelope.",
    "Do not explain, do not use markdown fences, and preserve the user's intent.",
    "",
    "Original user request:",
    originalPrompt,
  ].join("\n");
}

function repairContext(
  baseContext: Record<string, unknown>,
  errorMessage: string,
  previousOutput: string,
  attempt: number,
): Record<string, unknown> {
  return {
    ...baseContext,
    repair_attempt: attempt,
    repair_max_attempts: WIDGET_REPAIR_MAX_ATTEMPTS,
    repair_error: errorMessage,
    previous_invalid_output: previousOutput.slice(-6000),
    contract: `${String(baseContext.contract || "")} Repair mode: fix the validation error and return a valid workflow envelope.`,
  };
}

async function sendMessage(overrideText?: string) {
  const baseText = (overrideText ?? composer.value).trim();
  if (!baseText || chatDisabled.value || generating.value) return;
  // Preview-mode selection chip — prepend a one-line context note so the LLM
  // knows which element the user is talking about. Mirrors how the user would
  // type "re: <button.start>" by hand, but spelled out by the harness.
  const selection = props.selectedTarget;
  const text = selection
    ? `re: <${selection.selector}${selection.text ? ` "${selection.text}"` : ""}>\n\n${baseText}`
    : baseText;
  const imagesForMessage = widgetModelSupportsImages.value ? [...attachedImages.value] : [];
  const currentWidget = targetWidget.value;
  if (adjusting.value && !currentWidget) {
    error.value = "Widget is still loading. Try again in a moment.";
    return;
  }
  composer.value = "";
  pendingWorkflowQuestion.value = null;
  if (selection) emit("clear-selected-target");
  attachedImages.value = [];
  resizeComposer();
  if (!adjusting.value) {
    pushRecentPrompt(text);
    recentPrompts.value = loadRecentPrompts();
  }
  generating.value = true;
  error.value = null;
  const controller = new AbortController();
  currentAbort.value = controller;
  messages.value.push({ id: messageId("user"), role: "user", text, images: imagesForMessage });
  const assistantId = messageId("assistant");
  const clarifyFirst = workflowMode.value === "clarify_first";
  const assistantMessage: ChatMessage = {
    id: assistantId,
    role: "assistant",
    text: clarifyFirst
      ? "Preparing a clarification…"
      : adjusting.value ? "Drafting your changes…" : "Drafting your widget…",
  };
  messages.value.push(assistantMessage);
  streamingMessageId.value = assistantId;
  streamedChars.value = 0;
  streamTail.value = "";
  await scrollThreadToBottom();
  let raw = "";
  let lastExtractedFields: StreamingPreviewFields | null = null;
  let streamingPreviewRafId: number | null = null;
  try {
    const baseContext: Record<string, unknown> = {
      contract: widgetWorkflowContract(),
      widget_workflow_mode: workflowMode.value,
      rules:
        "Return the COMPLETE document fragment in `html` — every opened tag must be closed; never truncate. " +
        "If you set a dark background, set a matching light text color (and vice versa) so content is visible. " +
        "Use inline styles or the `css` field — do not rely on outer CSS variables.",
      one_widget_per_slide: true,
      conversation: conversationContext(),
      previous_widget: latestDraft.value ? JSON.stringify(latestDraft.value) : null,
      adjust_existing: adjusting.value,
      current: currentWidget
        ? {
            name: currentWidget.name,
            kind: currentWidget.kind,
            description: currentWidget.description,
            html: currentWidget.html,
            js: currentWidget.js,
            css: currentWidget.css,
            props_schema: currentWidget.props_schema,
            example_props: currentWidget.example_props,
            ai_spec: currentWidget.ai_spec,
            tags: currentWidget.tags,
            behavior: currentWidget.behavior,
          }
        : null,
      bound_props: props.placement?.props ?? null,
    };
    const requestImages = imagesForMessage.map((image) => ({
      data_url: image.data_url,
      name: image.name,
      mime_type: image.mime_type,
    }));
    let workflow: WidgetWorkflow | null = null;
    let lastError: unknown = null;
    let previousOutput = "";
    let stoppedClarifyDraft = false;
    for (let attempt = 1; attempt <= WIDGET_REPAIR_MAX_ATTEMPTS; attempt += 1) {
      raw = "";
      assistantMessage.warnings = undefined;
      if (attempt > 1) {
        assistantMessage.text = `Repairing widget output — attempt ${attempt} of ${WIDGET_REPAIR_MAX_ATTEMPTS}...`;
      }
      const prompt = attempt === 1 ? text : repairPrompt(text, lastError instanceof Error ? lastError.message : String(lastError || "Unknown validation error"));
      const context = attempt === 1
        ? baseContext
        : repairContext(baseContext, lastError instanceof Error ? lastError.message : String(lastError || "Unknown validation error"), previousOutput, attempt);
      let responseText = "";
      try {
        responseText = await llmApi.completeText(
          {
            purpose: "widget_generate",
            prompt,
            context,
            images: requestImages,
          },
          {
            signal: controller.signal,
            onToken: (delta) => {
              raw += delta;
              if (clarifyFirst && looksLikeDraftWorkflowEnvelope(raw)) {
                stoppedClarifyDraft = true;
                streamTail.value = "";
                streamedChars.value = 0;
                controller.abort();
                return;
              }
              streamedChars.value = raw.length;
              
              const fields = extractPreviewFields(raw);
              const hasChanged = !lastExtractedFields ||
                fields.html !== lastExtractedFields.html ||
                fields.css !== lastExtractedFields.css ||
                fields.name !== lastExtractedFields.name ||
                fields.kind !== lastExtractedFields.kind;
              
              if (hasChanged && fields.html) {
                if (streamingPreviewRafId !== null) {
                  cancelAnimationFrame(streamingPreviewRafId);
                }
                const currentAssistantId = assistantId;
                // Capture whether we should follow bottom before DOM update
                const shouldFollow = isUserNearBottom.value;
                streamingPreviewRafId = requestAnimationFrame(() => {
                  if (!isUnmounted && streamingMessageId.value === currentAssistantId) {
                    streamingDraftFields.value = fields;
                    // Scroll after preview renders, not before
                    if (shouldFollow) {
                      void nextTick().then(() => {
                        queueAutoScrollToBottom({ force: false, smooth: false });
                      });
                    }
                  }
                  streamingPreviewRafId = null;
                });
                lastExtractedFields = fields;
              }
              
              // Keep tail populated for compact display under preview
              streamTail.value = clarifyFirst ? "" : (raw.length > 280 ? raw.slice(-280) : raw);
            },
            onWarnings: (warnings) => {
              assistantMessage.warnings = warnings;
            },
          },
        );
      } catch (err) {
        if (stoppedClarifyDraft && controller.signal.aborted) {
          workflow = clarifyFirstDraftFallback();
          break;
        }
        throw err;
      }
      if (stoppedClarifyDraft) {
        workflow = clarifyFirstDraftFallback();
        break;
      }
      raw = responseText || raw;
      previousOutput = raw;
      assistantMessage.raw = raw;
      try {
        const parsedWorkflow = parseWidgetWorkflow(raw);
        if (workflowMode.value === "clarify_first" && parsedWorkflow.type === "draft") {
          workflow = clarifyFirstDraftFallback();
          break;
        }
        const validationError = validateWorkflowDraft(parsedWorkflow);
        if (validationError) throw new Error(validationError);
        workflow = parsedWorkflow;
        break;
      } catch (err) {
        lastError = err;
        if (attempt >= WIDGET_REPAIR_MAX_ATTEMPTS) throw err;
      }
    }
    if (!workflow) throw lastError instanceof Error ? lastError : new Error("Could not generate widget.");
    if (workflowMode.value === "clarify_first" && workflow.type === "draft") {
      workflow = clarifyFirstDraftFallback();
    }
    if (workflow.type === "question") {
      assistantMessage.text = workflow.question;
      assistantMessage.question = { question: workflow.question, options: workflow.options };
      pendingWorkflowQuestion.value = { messageId: assistantId, question: workflow.question, options: workflow.options };
    } else if (workflow.type === "plan" || workflow.type === "step" || workflow.type === "reflection") {
      assistantMessage.text = workflow.reflection || "AI is planning the next widget change.";
      assistantMessage.plan = workflow.plan;
      assistantMessage.reflection = workflow.reflection;
    } else if (workflow.type === "draft") {
      assistantMessage.text = adjusting.value
        ? `Here's an adjustment for ${currentWidget?.name || "this widget"}. Apply it below or ask for another change.`
        : `Here's a draft for ${workflow.widget.name || "your widget"}. Review it below or ask for changes.`;
      assistantMessage.draft = workflow.widget;
      assistantMessage.plan = workflow.plan;
      assistantMessage.reflection = workflow.reflection;
    }
    if (adjusting.value && currentWidget) {
      await appendAiThreadMessage(currentWidget, {
        role: "user",
        message_type: "user",
        content: { text },
        revision_id: currentWidget.current_revision_id ?? null,
      });
      await appendAiThreadMessage(currentWidget, {
        role: "assistant",
        message_type: workflow.type,
        content: workflowThreadContent(workflow),
        revision_id: currentWidget.current_revision_id ?? null,
      });
    }
  } catch (err) {
    if (controller.signal.aborted) {
      assistantMessage.text = raw.trim()
        ? "Cancelled. Partial output discarded — send again to retry."
        : "Cancelled before any output.";
    } else {
      console.error("[widget_generate] failed", {
        err,
        rawLength: raw.length,
        raw,
        aborted: controller.signal.aborted,
      });
      if (err instanceof ApiError) {
        // Backend/upstream failure (rate limit, LLM error, DB) — surface the real detail.
        assistantMessage.text = `AI request failed: ${err.message}`;
        if (raw.trim()) assistantMessage.raw = raw;
        error.value = err.message;
      } else if (raw.trim()) {
        // The model streamed text but it isn't a valid workflow envelope.
        assistantMessage.text = "AI returned an invalid widget workflow response. Ask it to try again.";
        assistantMessage.raw = raw;
        error.value = `Invalid widget workflow: ${err instanceof Error ? err.message : "unknown error"}`;
      } else {
        const msg = err instanceof Error ? err.message : "Could not generate widget.";
        assistantMessage.text = msg;
        error.value = msg;
      }
    }
  } finally {
    if (streamingPreviewRafId !== null) {
      cancelAnimationFrame(streamingPreviewRafId);
      streamingPreviewRafId = null;
    }
    streamingMessageId.value = null;
    streamingDraftFields.value = null;
    streamedChars.value = 0;
    streamTail.value = "";
    generating.value = false;
    if (currentAbort.value === controller) currentAbort.value = null;
    
    if (!isUnmounted) {
      await nextTick();
      queueAutoScrollToBottom({ force: false, smooth: false });
    }
  }
}

function cancelGeneration() {
  currentAbort.value?.abort();
}

function formatStreamProgress(chars: number | undefined): string {
  const n = chars || 0;
  if (workflowMode.value === "clarify_first") {
    if (n < 1024) return `Preparing clarification — ${n} characters so far`;
    const kb = (n / 1024).toFixed(1);
    return `Preparing clarification — ${kb} KB so far`;
  }
  if (n < 1024) return `Streaming widget source — ${n} characters so far`;
  const kb = (n / 1024).toFixed(1);
  return `Streaming widget source — ${kb} KB so far`;
}

function onComposerInput() {
  resizeComposer();
}

function onComposerKeydown(e: KeyboardEvent) {
  if (e.key !== "Enter" || e.shiftKey) return;
  e.preventDefault();
  void sendMessage();
}

function previousUserText(messageId: string): string {
  const idx = messages.value.findIndex((m) => m.id === messageId);
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === "user") return messages.value[i].text;
  }
  return "Regenerate this widget with a different approach.";
}

function regenerateDraft(message: ChatMessage) {
  const request = `Regenerate this widget with a stronger alternative. Original request: ${previousUserText(message.id)}`;
  void sendMessage(request);
}

function chooseWorkflowOption(option: WidgetWorkflowOption) {
  customClarificationAnswer.value = "";
  if (option.value?.workflow_mode === "build_now" || option.value?.workflow_mode === "clarify_first") {
    workflowMode.value = option.value.workflow_mode as WidgetWorkflowMode;
  }
  const value = option.value ? `\n\nOption value:\n${JSON.stringify(option.value)}` : "";
  void sendMessage(`Choose: ${option.label}${value}`);
}

function submitCustomClarificationAnswer() {
  const answer = customClarificationAnswer.value.trim();
  const question = pendingWorkflowQuestion.value;
  if (!answer || !question) return;
  customClarificationAnswer.value = "";
  void sendMessage(`Answer to "${question.question}": ${answer}`);
}

function clearConversation() {
  // Adjust mode keeps a single welcome message so the empty pane explains
  // what the chat does for an existing widget; create mode starts blank
  // and shows the recent-prompts empty state instead.
  messages.value = adjusting.value
    ? [{ id: "assistant-welcome", role: "assistant", text: welcomeText() }]
    : [];
  composer.value = "";
  pendingWorkflowQuestion.value = null;
  customClarificationAnswer.value = "";
  attachedImages.value = [];
  error.value = null;
  nextTick(resizeComposer);
}

async function saveWidgetCode() {
  const currentWidget = targetWidget.value;
  if (!currentWidget || savingCode.value || !codeDirty.value) return;
  savingCode.value = true;
  codeError.value = null;
  codeSaved.value = null;
  try {
    const updated = await withResetConfirm((opts) =>
      widgetsApi.patch(
        currentWidget.id,
        {
          html: codeHtml.value,
          js: codeJs.value.trim() ? codeJs.value : null,
          css: codeCss.value.trim() ? codeCss.value : null,
        },
        opts,
      ),
    );
    widgets.cache[currentWidget.id] = updated;
    codeHtml.value = updated.html || "";
    codeJs.value = updated.js || "";
    codeCss.value = updated.css || "";
    codeSaved.value = "Saved";
    emit("applied", currentWidget.id);
  } catch (err) {
    codeError.value = err instanceof Error ? err.message : "Could not save widget source.";
  } finally {
    savingCode.value = false;
  }
}

async function savePlacementProps() {
  if (savingProps.value || !propsDirty.value || !props.placement) return;
  savingProps.value = true;
  propsError.value = null;
  propsSaved.value = null;
  const payload = {
    placement_id: props.placement.placement_id,
    props: JSON.parse(JSON.stringify(propsDraft.value)),
  };
  try {
    if (props.onPatchPlacementProps) {
      // New path: callback returns a Promise → we can intercept the 409
      // edit_requires_reset and surface the reset-confirm modal.
      await withResetConfirm((opts) => props.onPatchPlacementProps!(payload, opts));
    } else {
      // Legacy path: fire-and-forget emit for callers that haven't migrated.
      emit("save-placement-props", payload);
    }
    propsSaved.value = "Saved";
  } catch (err) {
    propsError.value = err instanceof Error ? err.message : "Could not save properties.";
  } finally {
    savingProps.value = false;
  }
}

async function persistDraft(insert: boolean, draft: Partial<Widget>, sourceMessageId: string) {
  savingMessageId.value = sourceMessageId;
  error.value = null;
  try {
    const sourceDraftNumber = draftNumberForMessage(sourceMessageId);
    if (adjusting.value) {
      const currentWidget = targetWidget.value;
      if (!currentWidget) throw new Error("Widget is still loading.");
      if (typeof draft.html === "string") {
        const warn = validateDraftHtml(draft.html);
        if (warn) throw new Error(warn);
      }
      if (typeof draft.js === "string") {
        const warn = validateDraftJs(draft.js);
        if (warn) throw new Error(warn);
      }
      const adjustPatch: Partial<Widget> = {};
      for (const key of ["name", "kind", "description", "html", "js", "css", "props_schema", "example_props", "ai_spec", "tags", "behavior"] as const) {
        if (key in draft) (adjustPatch as Record<string, unknown>)[key] = draft[key];
      }
      const updated = await withResetConfirm((opts) =>
        widgetsApi.patch(currentWidget.id, adjustPatch, opts),
      );
      widgets.cache[currentWidget.id] = updated;
      void appendAiThreadMessage(updated, {
        role: "assistant",
        message_type: "apply",
        content: {
          text: "Applied to the widget.",
          applied_from_draft_number: sourceDraftNumber,
          applied_from_message_id: sourceMessageId,
        },
        revision_id: updated.current_revision_id ?? null,
      });
      const target = messages.value.find((m) => m.id === sourceMessageId);
      if (target) target.applied = true;
      messages.value.push({
        id: messageId("apply"),
        role: "assistant",
        text: "Applied to the widget.",
        appliedFromDraftNumber: sourceDraftNumber,
        appliedFromMessageId: sourceMessageId,
      });
      await scrollThreadToBottom();
      emit("applied", currentWidget.id);
      return;
    }
    if (!props.deckId) throw new Error("No deck selected — open the editor to generate a widget.");
    if (typeof draft.js === "string") {
      const warn = validateDraftJs(draft.js);
      if (warn) throw new Error(warn);
    }
    const widget = await widgetsApi.createInDeck(props.deckId, {
      name: draft.name,
      kind: draft.kind,
      description: draft.description,
      html: draft.html,
      js: draft.js,
      css: draft.css,
      props_schema: draft.props_schema,
      example_props: draft.example_props,
      ai_spec: draft.ai_spec,
      tags: draft.tags,
      behavior: draft.behavior,
    });
    widgets.invalidate(widget.id);
    await widgets.fetchListForDeck(props.deckId);
    await persistConversationSnapshot(widget);
    await appendAiThreadMessage(widget, {
      role: "assistant",
      message_type: "apply",
      content: {
        text: insert ? "Inserted into the slide." : "Saved to the widget library.",
        applied_from_draft_number: sourceDraftNumber,
        applied_from_message_id: sourceMessageId,
      },
      revision_id: widget.current_revision_id ?? null,
    });
    if (insert) {
      emit("pick", widget);
    } else {
      const target = messages.value.find((m) => m.id === sourceMessageId);
      if (target) target.applied = true;
      // Scroll to show the applied confirmation message
      await scrollThreadToBottom();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not save widget.";
  } finally {
    savingMessageId.value = null;
  }
}

function requestDelete(widget: WidgetSummary) {
  // First try a soft delete; backend returns 409 with usage_count if the
  // widget is currently placed on any slide. The confirmation modal handles
  // both states (unused → simple confirm; in-use → cascade warning).
  confirmDelete.value = { widget, usageCount: null };
  deleteError.value = null;
}

async function doDelete(force: boolean) {
  const target = confirmDelete.value?.widget;
  if (!target || deleting.value) return;
  deleting.value = target.id;
  deleteError.value = null;
  try {
    await widgetsApi.remove(target.id, { force });
    widgets.invalidate(target.id);
    if (props.deckId) await widgets.fetchListForDeck(props.deckId);
    emit("deleted", target.id);
    confirmDelete.value = null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const detail = (err.body as { detail?: { usage_count?: number } } | undefined)?.detail;
      const count = typeof detail?.usage_count === "number" ? detail.usage_count : null;
      confirmDelete.value = { widget: target, usageCount: count };
    } else {
      deleteError.value = err instanceof Error ? err.message : "Couldn't delete widget.";
    }
  } finally {
    deleting.value = null;
  }
}
</script>

<template>
  <div :style="{ display: 'flex', flexDirection: 'column', height: '100%' }">
    <header class="widget-panel-header">
      <span class="widget-breadcrumb">
        WIDGETS<template v-if="slideLabel"> · {{ slideLabel }}</template>
      </span>
      <button class="widget-panel-close" @click="emit('close')" title="Close">
        <Icon name="x" :size="13" />
      </button>
    </header>

    <div v-if="adjusting && availableTabs.length > 1" class="widget-tab-strip">
      <button
        v-for="t in availableTabs"
        :key="t"
        @click="tab = t"
        :class="{ active: tab === t }"
      >
        {{ tabLabel(t) }}
      </button>
    </div>

    <div v-if="tab !== 'code' && ((props.disabled && !adjusting) || widgetGenerationDisabled)" :style="{
      margin: '12px 18px',
      padding: '12px 14px',
      border: '1px dashed var(--rule-strong)',
      borderRadius: 'var(--r-md)',
      color: 'var(--ink-soft)',
      fontSize: '12px',
      fontFamily: 'var(--sans)',
    }">
      {{
        widgetGenerationDisabled
          ? "Generate widgets is disabled in Settings. Assign a model to enable this chat."
          : props.disabledReason || "This slide already has a widget — use the Adjust panel to edit it."
      }}
    </div>

    <div v-if="tab === 'generate'" class="widget-chat">
      <div ref="thread" class="widget-chat-thread" @scroll.passive="onThreadScroll">
        <!-- Empty state — only when no user messages have been sent yet
             in create mode. Adjust mode keeps its single-message welcome. -->
        <div v-if="showEmptyState" class="widget-empty-state">
          <h2 class="widget-empty-heading">
            What should we <em>build?</em>
          </h2>
          <p class="widget-empty-sub">
            Describe an interaction and I'll draft the widget. Iterate by
            replying, or drop one straight onto the slide.
          </p>
          <ol v-if="recentPrompts.length" class="widget-empty-recents">
            <li
              v-for="(prompt, idx) in recentPrompts"
              :key="prompt + idx"
              class="widget-recent-row"
              role="button"
              tabindex="0"
              @click="pickRecentPrompt(prompt)"
              @keydown.enter.prevent="pickRecentPrompt(prompt)"
              @keydown.space.prevent="pickRecentPrompt(prompt)"
            >
              <span class="widget-recent-ordinal">{{ String(idx + 1).padStart(2, "0") }}</span>
              <span class="widget-recent-text">{{ prompt }}</span>
              <span class="widget-recent-arrow" aria-hidden="true">→</span>
            </li>
          </ol>
          <p v-if="recentPrompts.length" class="widget-empty-foot">
            Drag a suggestion onto the slide to insert it, or click → to
            draft and iterate in chat.
          </p>
        </div>

        <div
          v-for="message in messages"
          :key="message.id"
          class="chat-message"
          :class="message.role"
          :data-message-id="message.id"
        >
          <div
            v-if="message.appliedFromDraftNumber !== undefined"
            class="widget-applied-reference"
            data-testid="widget-applied-reference"
          >
            <span>Applied to the widget from </span><button
              type="button"
              class="widget-applied-reference-button"
              data-testid="widget-applied-reference-button"
              @click="scrollToDraftReference(message)"
            ><b>Draft #{{ message.appliedFromDraftNumber }}</b></button>
          </div>
          <div v-else class="chat-bubble" :class="{ 'is-streaming': streamingMessageId === message.id }">
            <template v-if="streamingMessageId === message.id">
              <span class="chat-loading-grip" data-testid="chat-loading-grip" aria-hidden="true">
                <svg
                  fill="none"
                  height="18"
                  stroke="currentColor"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                  width="18"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <circle
                    v-for="(circle, index) in LOADING_GRIP_CIRCLES"
                    :key="`${circle.cx}-${circle.cy}`"
                    :cx="circle.cx"
                    :cy="circle.cy"
                    r="1"
                    :style="{ animationDelay: `${index * 70}ms` }"
                  />
                </svg>
              </span>
            </template>
            <span class="chat-bubble-text">{{ message.text }}</span>
            <template v-if="streamingMessageId === message.id">
              <span class="chat-stream-meta">
                <template v-if="streamedChars > 0">{{ formatStreamProgress(streamedChars) }}</template>
                <template v-else>Waiting for the model to start…</template>
              </span>
            </template>
          </div>
          <div
            v-if="streamingMessageId === message.id && streamTail && !streamingPreviewWidget"
            class="chat-stream-tail t-mono"
            aria-label="Streaming widget source"
          >
            {{ streamTail }}
          </div>

          <details
            v-if="message.raw && streamingMessageId !== message.id"
            class="chat-raw-output"
          >
            <summary>Show raw AI output</summary>
            <pre class="t-mono">{{ message.raw }}</pre>
          </details>

          <div v-if="message.images?.length" class="chat-image-strip">
            <img v-for="image in message.images" :key="image.id" :src="image.data_url" :alt="image.name" />
          </div>

          <div v-if="message.plan?.length || message.reflection" class="widget-workflow-meta">
            <ol v-if="message.plan?.length" class="widget-workflow-plan">
              <li v-for="(step, idx) in message.plan" :key="idx">{{ step }}</li>
            </ol>
            <p v-if="message.reflection" class="widget-workflow-reflection">{{ message.reflection }}</p>
          </div>

          <div v-if="streamingMessageId === message.id && streamingPreviewWidget && !message.draft" class="widget-preview-card is-streaming">
            <div class="widget-preview-head">
              <span class="widget-preview-kicker">
                <span v-if="streamingPreviewWidget.name !== 'Generated widget'">
                  GENERATING · {{ streamingPreviewWidget.name }}
                </span>
                <span v-else>GENERATING...</span>
                <span class="streaming-char-count">{{ streamedChars }} chars</span>
              </span>
            </div>
            
            <div class="widget-preview-frame-wrap">
              <WidgetFrame
                class="widget-preview-frame"
                :widget="streamingPreviewWidget"
                :placement-id="`streaming-preview-${message.id}`"
                :boot-props="draftPreviewProps(streamingPreviewWidget)"
                role="preview"
                :fill="true"
                :min-height="200"
              />
            </div>
            
            <div v-if="streamTail" class="streaming-tail-compact">
              <code>{{ streamTail }}</code>
            </div>
          </div>

          <div v-if="message.draft" class="widget-preview-card scale-in">
            <div class="widget-preview-head">
              <span class="widget-preview-kicker">
                DRAFT #{{ draftNumberForMessage(message.id) }} · {{ (resolvedDraft(message.draft).kind || "custom").toUpperCase() }}
                <span v-if="message.applied" class="widget-preview-applied-chip">APPLIED</span>
              </span>
              <div class="widget-preview-head-actions">
                <button
                  v-if="adjusting"
                  type="button"
                  class="widget-preview-codelink"
                  :disabled="!props.placement"
                  @click="openCodeFromDraft"
                  title="View widget source"
                >
                  &lt;/&gt; code
                </button>
                <button
                  type="button"
                  class="widget-preview-insert"
                  :disabled="savingMessageId === message.id || chatDisabled"
                  @click="persistDraft(true, message.draft, message.id)"
                >
                  + {{ savingMessageId === message.id ? (adjusting ? "applying" : "inserting") : (adjusting ? "apply" : "insert") }}
                </button>
              </div>
            </div>
            <ul
              v-if="message.warnings?.length"
              class="widget-preview-warning widget-preview-warning-list"
              data-testid="validator-warnings"
            >
              <li v-for="(w, idx) in message.warnings" :key="idx">{{ w }}</li>
            </ul>
            <div class="widget-preview-frame-wrap">
              <WidgetFrame
                class="widget-preview-frame"
                :widget="draftPreviewWidget(resolvedDraft(message.draft), message.id)"
                :placement-id="`draft-preview-${message.id}`"
                :boot-props="draftPreviewProps(resolvedDraft(message.draft))"
                role="preview"
                :fill="true"
                :min-height="200"
              />
            </div>
          </div>
        </div>

        <div
          v-if="pendingWorkflowQuestion"
          class="widget-question-panel"
          data-testid="widget-question-options"
        >
          <div class="widget-question-option-list">
            <button
              v-for="option in pendingWorkflowQuestion.options"
              :key="option.id"
              type="button"
              class="widget-question-option"
              @click="chooseWorkflowOption(option)"
            >
              {{ option.label }}
            </button>
          </div>
          <form
            class="widget-question-custom"
            data-testid="widget-question-custom-form"
            @submit.prevent="submitCustomClarificationAnswer"
          >
            <input
              v-model="customClarificationAnswer"
              class="widget-question-custom-input"
              data-testid="widget-question-custom-input"
              type="text"
              placeholder="Something else"
            />
            <button
              type="submit"
              class="widget-question-custom-send"
              :disabled="!customClarificationAnswer.trim() || chatDisabled || generating"
              title="Send custom answer"
            >
              <Icon name="arrow_right" :size="13" />
            </button>
          </form>
        </div>

        <p v-if="error" class="chat-error">{{ error }}</p>
      </div>

      <form class="widget-chat-composer" @submit.prevent="sendMessage()">
        <div
          v-if="props.selectedTarget"
          class="composer-selection-chip"
          data-testid="composer-selection-chip"
        >
          <span class="composer-selection-marker">re:</span>
          <code class="composer-selection-selector">{{ props.selectedTarget.selector }}</code>
          <span v-if="props.selectedTarget.text" class="composer-selection-text">
            "{{ props.selectedTarget.text }}"
          </span>
          <button
            type="button"
            class="composer-selection-clear"
            title="Clear selection"
            @click="emit('clear-selected-target')"
          >
            <Icon name="x" :size="11" />
          </button>
        </div>
        <input ref="imageInput" type="file" accept="image/*" multiple hidden @change="onAttachImages" />
        <div v-if="attachedImages.length" class="composer-attachments">
          <span v-for="image in attachedImages" :key="image.id" class="composer-image-chip">
            <img :src="image.data_url" :alt="image.name" />
            <button type="button" :title="`Remove ${image.name}`" @click="removeAttachedImage(image.id)">
              <Icon name="x" :size="11" />
            </button>
          </span>
        </div>
        <textarea
          ref="composerInput"
          v-model="composer"
          class="widget-chat-input"
          rows="1"
          :disabled="chatDisabled || generating"
          :placeholder="composerPlaceholder"
          @input="onComposerInput"
          @keydown="onComposerKeydown"
          @focus="composerFocused = true"
          @blur="composerFocused = false"
        />
        <div class="widget-composer-toolbar">
          <div class="widget-composer-tools">
            <button
              class="widget-tool-btn"
              type="button"
              :title="widgetModelSupportsImages ? 'Attach image' : 'Current model does not accept images'"
              :disabled="!widgetModelSupportsImages || chatDisabled || generating || attachedImages.length >= 6"
              @click="imageInput?.click()"
            >
              <Icon name="upload" :size="14" />
            </button>
            <button
              ref="workflowModeAnchor"
              type="button"
              class="widget-tool-btn widget-tool-mode"
              :class="{ active: workflowModeMenuOpen }"
              data-testid="widget-workflow-mode-trigger"
              title="AI workflow mode"
              @click="toggleWorkflowModeMenu"
            >
              <Icon name="bolt" :size="13" />
              <span>{{ workflowModeLabel }}</span>
              <Icon name="chev_down" :size="11" />
            </button>
            <button
              ref="libraryAnchor"
              type="button"
              class="widget-tool-btn widget-tool-library"
              :class="{ active: libraryOpen }"
              title="Library"
              @click="toggleLibrary"
            >
              <Icon name="widget" :size="13" />
              <span>library</span>
            </button>
          </div>
          <button
            v-if="generating"
            class="widget-chat-send widget-chat-cancel"
            type="button"
            title="Cancel"
            @click="cancelGeneration"
          >
            <Icon name="x" :size="14" />
          </button>
          <button
            v-else
            class="widget-chat-send"
            type="submit"
            :disabled="!composer.trim() || chatDisabled"
            title="Send"
          >
            <Icon name="arrow_right" :size="14" />
          </button>

        <!-- Library popover -->
        <div
          v-if="workflowModeMenuOpen"
          ref="workflowModePopover"
          class="widget-popover widget-popover-mode"
          data-testid="widget-workflow-mode-menu"
          role="menu"
          aria-label="AI workflow mode"
        >
          <button
            type="button"
            class="widget-mode-menu-item"
            :class="{ active: workflowMode === 'clarify_first' }"
            data-testid="widget-workflow-mode-clarify"
            role="menuitemradio"
            :aria-checked="workflowMode === 'clarify_first'"
            @click="setWorkflowMode('clarify_first')"
          >
            <span class="widget-mode-menu-title">Clarify first</span>
            <span class="widget-mode-menu-sub">Ask before drafting.</span>
          </button>
          <button
            type="button"
            class="widget-mode-menu-item"
            :class="{ active: workflowMode === 'build_now' }"
            data-testid="widget-workflow-mode-build"
            role="menuitemradio"
            :aria-checked="workflowMode === 'build_now'"
            @click="setWorkflowMode('build_now')"
          >
            <span class="widget-mode-menu-title">Build now</span>
            <span class="widget-mode-menu-sub">Draft when ready.</span>
          </button>
        </div>

        <div
          v-if="libraryOpen"
          ref="libraryPopover"
          class="widget-popover widget-popover-library"
          role="dialog"
          aria-label="Widget library"
        >
          <div class="widget-popover-headrow">
            <span class="widget-popover-label">LIBRARY</span>
            <button class="widget-popover-close" type="button" @click="libraryOpen = false">
              <Icon name="x" :size="11" />
            </button>
          </div>
          <input
            v-model="query"
            class="widget-popover-search"
            placeholder="Search widgets…"
          />
          <button
            class="widget-popover-copylink"
            type="button"
            :disabled="!deckId || copyPickerLoading"
            @click="openCopyPicker"
          >
            <Icon name="plus" :size="11" />
            <span>{{ showCopyPicker ? "Hide other decks" : "Copy from another deck" }}</span>
          </button>
          <div v-if="showCopyPicker" class="widget-popover-copybox">
            <p v-if="copyPickerLoading" class="widget-popover-empty">Loading…</p>
            <p v-else-if="!copyCandidates.length" class="widget-popover-empty">
              No widgets in your other decks yet.
            </p>
            <ul v-else>
              <li v-for="w in copyCandidates" :key="w.id">
                <span class="widget-popover-copyname">{{ w.name }}</span>
                <span class="t-mono widget-popover-copykind">{{ w.kind }}</span>
                <button
                  class="widget-popover-copybtn"
                  type="button"
                  :disabled="copyingWidgetId === w.id"
                  @click="copyFromAnotherDeck(w)"
                >
                  {{ copyingWidgetId === w.id ? "…" : "copy" }}
                </button>
              </li>
            </ul>
            <p v-if="copyError" class="widget-popover-error">{{ copyError }}</p>
          </div>
          <p
            v-if="widgets.loading && !widgets.summaries.length"
            class="widget-popover-empty"
          >Loading…</p>
          <p
            v-else-if="!filtered.length"
            class="widget-popover-empty"
          >No widgets in this deck yet.</p>
          <ul v-else class="widget-popover-list">
            <li v-for="w in filtered" :key="w.id" class="widget-popover-item">
              <button
                type="button"
                class="widget-popover-itembtn"
                :disabled="props.disabled"
                @click="!props.disabled && (emit('pick', w), libraryOpen = false)"
              >
                <span class="widget-popover-itemname">{{ w.name }}</span>
                <span class="widget-popover-itemkind">{{ w.description || w.kind }}</span>
              </button>
              <span class="widget-popover-itemtag t-mono">{{ w.kind }}</span>
              <button
                type="button"
                class="widget-popover-rowbtn"
                :title="`Duplicate ${w.name} in this deck`"
                :disabled="copyingWidgetId === w.id"
                @click.stop="duplicateInDeck(w)"
              >
                <Icon name="copy" :size="11" />
              </button>
              <button
                type="button"
                class="widget-popover-rowbtn widget-popover-rowbtn-danger"
                :title="`Delete ${w.name}`"
                :disabled="deleting === w.id"
                @click.stop="requestDelete(w)"
              >
                <Icon name="trash" :size="11" />
              </button>
            </li>
          </ul>
        </div>
        </div>
      </form>

      <p class="widget-footer-status">
        <template v-if="composerFocused && conversationActive">
          ↵ to send · ⇧↵ for newline
        </template>
        <template v-else>
          one widget per slide
        </template>
      </p>
    </div>

    <div v-else-if="tab === 'props'" class="widget-props-panel">
      <div class="widget-props-topbar">
        <div>
          <div class="t-kicker">Widget properties</div>
          <div class="widget-props-title">
            {{ targetWidget?.name || props.placement?.name || "Loading widget..." }}
          </div>
        </div>
      </div>
      <div class="widget-props-body">
        <PropsForm v-model="propsDraft" :schema="propsSchema" />
      </div>
      <div class="widget-props-footer">
        <p v-if="propsError" class="t-meta" :style="{ color: 'var(--err)' }">{{ propsError }}</p>
        <p v-else-if="propsSaved" class="t-meta" :style="{ color: 'var(--ink-soft)' }">{{ propsSaved }}</p>
        <p v-else-if="propsDirty" class="t-meta" :style="{ color: 'var(--ink-soft)' }">Unsaved changes — click Save to apply.</p>
        <p v-else class="t-meta" :style="{ color: 'var(--ink-soft)' }">All changes saved.</p>
        <button
          class="btn btn-primary btn-sm"
          :disabled="!propsDirty || savingProps"
          type="button"
          @click="savePlacementProps"
        >
          {{ savingProps ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </div>

    <div v-else class="widget-code-panel">
      <div class="widget-code-topbar">
        <div>
          <div class="t-kicker">Widget source</div>
          <div class="widget-code-title">
            {{ targetWidget?.name || props.placement?.name || "Loading widget..." }}
          </div>
        </div>
        <div class="widget-code-tabs" aria-label="Widget code files">
          <button
            v-for="t in (['html', 'js', 'css'] as const)"
            :key="t"
            type="button"
            :class="{ active: codeTab === t }"
            @click="codeTab = t"
          >
            {{ t.toUpperCase() }}
          </button>
        </div>
      </div>
      <p v-if="!targetWidget" class="widget-code-empty">Loading widget source…</p>
      <template v-else>
        <textarea
          v-model="currentCode"
          class="widget-code-body"
          spellcheck="false"
          :aria-label="`${codeTab.toUpperCase()} source`"
        />
        <footer class="widget-code-footer">
          <span v-if="codeError" class="widget-code-status error">{{ codeError }}</span>
          <span v-else-if="codeSaved" class="widget-code-status">{{ codeSaved }}</span>
          <span v-else-if="codeDirty" class="widget-code-status">Unsaved changes</span>
          <span v-else class="widget-code-status">No changes</span>
          <button
            class="btn btn-primary btn-sm"
            type="button"
            :disabled="savingCode || !codeDirty"
            @click="saveWidgetCode"
          >
            {{ savingCode ? "Saving..." : "Save" }}
          </button>
        </footer>
      </template>
    </div>

    <!-- Delete-from-library confirmation -->
    <div
      v-if="confirmDelete"
      class="fade-in"
      :style="{
        position: 'fixed',
        inset: 0,
        background: 'rgba(11,13,16,0.42)',
        zIndex: 90,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }"
      @click.self="confirmDelete = null"
    >
      <div
        class="slide-up"
        :style="{
          width: 'min(420px, 92vw)',
          background: 'var(--paper)',
          borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-3)',
          padding: '22px 22px 16px',
        }"
      >
        <div class="t-kicker" :style="{ marginBottom: '6px', color: 'var(--err)' }">Delete widget</div>
        <div :style="{ fontFamily: 'var(--serif)', fontSize: '20px', letterSpacing: '-0.01em', marginBottom: '10px' }">
          Delete <em>{{ confirmDelete.widget.name }}</em>?
        </div>
        <p
          v-if="confirmDelete.usageCount === null"
          :style="{ fontSize: '13px', color: 'var(--ink-soft)', lineHeight: 1.55, margin: '0 0 18px' }"
        >
          This removes the widget from your workspace library. Slides that currently use it will lose the
          embedded interaction. Past session logs are preserved (with the widget reference cleared).
        </p>
        <p
          v-else
          :style="{ fontSize: '13px', color: 'var(--ink-soft)', lineHeight: 1.55, margin: '0 0 18px' }"
        >
          This widget is currently placed on
          <strong :style="{ color: 'var(--ink)' }">{{ confirmDelete.usageCount }} slide{{ confirmDelete.usageCount === 1 ? '' : 's' }}</strong>.
          Deleting it will detach the widget from every slide and remove it from your library. This can't be undone.
        </p>
        <p v-if="deleteError" :style="{ marginTop: '0', marginBottom: '10px', color: 'var(--err)', fontSize: '12px' }">{{ deleteError }}</p>
        <div :style="{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }">
          <button class="btn btn-sm" :disabled="!!deleting" @click="confirmDelete = null">Cancel</button>
          <button
            class="btn btn-sm"
            :style="{ borderColor: 'var(--err)', color: 'var(--err)' }"
            :disabled="!!deleting"
            @click="doDelete(confirmDelete.usageCount !== null)"
          >
            <Icon name="trash" :size="13" />
            {{ deleting ? 'Deleting…' : confirmDelete.usageCount === null ? 'Delete' : `Detach & delete` }}
          </button>
        </div>
      </div>
    </div>

    <!-- Reset-confirm modal — server returned 409 edit_requires_reset because
         the widget is aggregating contributions in one or more live sessions.
         Confirm to drop the audience tally and apply the edit; cancel to roll
         back. Mirrors WIDGETS_V2.md decision log. -->
    <div
      v-if="resetConfirm"
      class="fade-in"
      data-testid="reset-confirm-modal"
      :style="{
        position: 'fixed',
        inset: 0,
        background: 'rgba(11,13,16,0.42)',
        zIndex: 90,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }"
      @click.self="!resetConfirm.pending && resetConfirm.onCancel()"
    >
      <div
        class="slide-up"
        :style="{
          width: 'min(440px, 92vw)',
          background: 'var(--paper)',
          borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-3)',
          padding: '22px 22px 16px',
        }"
      >
        <div class="t-kicker" :style="{ marginBottom: '6px', color: 'var(--err)' }">Reset audience tally</div>
        <div :style="{ fontFamily: 'var(--serif)', fontSize: '20px', letterSpacing: '-0.01em', marginBottom: '10px' }">
          This widget is live in
          <em>{{ resetConfirm.openSessionCount }} session{{ resetConfirm.openSessionCount === 1 ? '' : 's' }}</em>.
        </div>
        <p :style="{ fontSize: '13px', color: 'var(--ink-soft)', lineHeight: 1.55, margin: '0 0 18px' }">
          Saving this edit will clear the current audience aggregate
          ({{ resetConfirm.openPlacementCount }} placement{{ resetConfirm.openPlacementCount === 1 ? '' : 's' }})
          and broadcast a reset to every connected viewer. Raw responses stay in the
          session transcript.
        </p>
        <div :style="{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }">
          <button
            class="btn btn-sm"
            :disabled="resetConfirm.pending"
            @click="resetConfirm.onCancel()"
          >Cancel</button>
          <button
            class="btn btn-sm"
            data-testid="reset-confirm-button"
            :style="{ borderColor: 'var(--err)', color: 'var(--err)' }"
            :disabled="resetConfirm.pending"
            @click="resetConfirm.onConfirm()"
          >
            {{ resetConfirm.pending ? 'Resetting…' : 'Reset & save' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.widget-chat {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.widget-props-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.widget-props-topbar {
  padding: 10px 18px 12px;
  border-bottom: 1px solid var(--rule-soft);
}

.widget-props-title {
  margin-top: 3px;
  font-family: var(--serif);
  font-size: 18px;
  letter-spacing: -0.01em;
}

.widget-props-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 18px;
}

.widget-props-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 18px;
  border-top: 1px solid var(--rule-soft);
  background: var(--paper);
}

.widget-code-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.widget-code-topbar {
  padding: 10px 18px 12px;
  border-bottom: 1px solid var(--rule-soft);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.widget-code-title {
  margin-top: 3px;
  font-family: var(--serif);
  font-size: 18px;
  letter-spacing: -0.01em;
}

.widget-code-tabs {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  flex-shrink: 0;
}

.widget-code-tabs button {
  border: 0;
  border-radius: var(--r-xs);
  background: transparent;
  color: var(--ink-soft);
  padding: 5px 8px;
  font-family: var(--mono);
  font-size: 11px;
  cursor: pointer;
}

.widget-code-tabs button.active {
  background: var(--paper);
  color: var(--accent);
  border: 1px solid var(--rule);
}

.widget-code-body {
  flex: 1;
  min-height: 0;
  margin: 0;
  overflow: auto;
  padding: 16px 18px;
  background: var(--paper-2);
  color: var(--ink);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.6;
  border: 0;
  border-radius: 0;
  resize: none;
  outline: none;
  white-space: pre;
  tab-size: 2;
}

.widget-code-body:focus {
  box-shadow: inset 0 0 0 1px var(--accent);
}

.widget-code-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  border-top: 1px solid var(--rule);
  background: var(--paper);
}

.widget-code-status {
  min-width: 0;
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-code-status.error {
  color: var(--err);
}

.widget-code-empty {
  margin: 0;
  padding: 18px;
  color: var(--ink-soft);
  font-size: 12px;
  font-style: italic;
}

.widget-chat-thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-message {
  display: flex;
  flex-direction: column;
  max-width: 94%;
  gap: 8px;
}

.chat-message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.chat-message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.chat-bubble {
  border: 1px solid var(--rule);
  border-radius: 14px;
  padding: 9px 12px;
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.45;
  color: var(--ink);
  background: var(--paper);
}

.chat-message.user .chat-bubble {
  background: var(--paper-2);
  border-color: var(--rule-soft);
  color: var(--ink);
  border-bottom-right-radius: 4px;
}

.chat-message.assistant .chat-bubble {
  border-bottom-left-radius: 4px;
}

.widget-applied-reference {
  border: 1px solid var(--rule-soft);
  border-radius: var(--r-md);
  padding: 8px 11px;
  background: var(--paper);
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 12px;
  line-height: 1.35;
}

.widget-applied-reference-button {
  border: 0;
  background: transparent;
  color: var(--accent);
  font: inherit;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.widget-applied-reference-button:hover {
  color: var(--ink);
}

.chat-bubble.is-streaming {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 8px;
  row-gap: 4px;
  align-items: center;
}

.chat-stream-meta {
  grid-column: 2;
  font-size: 11px;
  letter-spacing: 0.01em;
  color: var(--ink-soft);
  font-family: var(--mono);
}

.chat-loading-grip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  color: var(--accent);
}

.chat-loading-grip circle {
  animation: chat-grip-pulse 1.1s ease-in-out infinite;
  transform-origin: center;
}

@keyframes chat-grip-pulse {
  0%, 100% {
    opacity: 1;
  }
  20%, 80% {
    opacity: 0.3;
  }
}

.chat-stream-tail {
  max-width: 100%;
  border: 1px solid var(--rule-soft);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--ink-soft);
  max-height: 96px;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-all;
  /* Top-fade so the user sees the tail without abrupt clipping. */
  mask-image: linear-gradient(to bottom, transparent 0, var(--ink) 24px);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, var(--ink) 24px);
}

.chat-raw-output {
  max-width: 100%;
  font-size: 11px;
  color: var(--ink-soft);
}

.chat-raw-output summary {
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}

.chat-raw-output pre {
  margin: 6px 0 0;
  border: 1px solid var(--rule-soft);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  padding: 8px 10px;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.45;
}

.chat-image-strip {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.chat-image-strip img {
  width: 64px;
  height: 48px;
  object-fit: cover;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
}

.widget-preview-card {
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
}

.widget-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  background: var(--paper-2);
  border-bottom: 1px solid var(--rule-soft);
}

.widget-preview-kicker {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--ink-mute);
}

.widget-preview-applied-chip {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 1px 5px;
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-sm);
  color: var(--ink-soft);
  letter-spacing: 0.08em;
}

.widget-preview-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.widget-preview-codelink {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-soft);
  background: transparent;
  border: 0;
  padding: 2px 4px;
  cursor: pointer;
}

.widget-preview-codelink:hover:not(:disabled) {
  color: var(--ink);
}

.widget-preview-codelink:disabled {
  opacity: 0.45;
  cursor: default;
}

.widget-preview-insert {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--paper);
  background: var(--ink);
  border: 1px solid var(--ink);
  padding: 4px 10px;
  border-radius: var(--r-sm);
  cursor: pointer;
  text-transform: lowercase;
  letter-spacing: 0.02em;
}

.widget-preview-insert:hover:not(:disabled) {
  background: var(--ink-soft);
  border-color: var(--ink-soft);
}

.widget-preview-insert:disabled {
  opacity: 0.5;
  cursor: default;
}

.widget-preview-warning {
  padding: 8px 12px;
  border-top: 1px solid var(--rule-soft);
  background: var(--paper-2);
  font-family: var(--sans);
  font-size: 11px;
  line-height: 1.5;
  color: var(--ink-soft);
}

.widget-preview-warning strong {
  font-family: var(--mono);
  font-weight: 500;
  color: var(--ink);
}

.widget-preview-warning-list {
  margin: 0;
  padding: 8px 12px 8px 28px;
  list-style: disc;
}

.widget-preview-warning-list li + li {
  margin-top: 4px;
}

.widget-workflow-meta {
  margin: 8px 0 0 0;
  padding: 8px 10px;
  border: 1px solid var(--rule-soft);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-soft);
}

.widget-workflow-plan {
  margin: 0;
  padding-left: 18px;
}

.widget-workflow-plan li + li {
  margin-top: 3px;
}

.widget-workflow-reflection {
  margin: 6px 0 0;
  line-height: 1.45;
}

.widget-preview-frame-wrap {
  height: 200px;
  background: var(--paper);
}

.streaming-char-count {
  margin-left: 12px;
  font-size: 11px;
  color: var(--muted);
}

.streaming-tail-compact {
  margin-top: 8px;
  padding: 8px;
  background: var(--paper-2);
  border-radius: 4px;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid var(--rule-soft);
}

.streaming-tail-compact code {
  font-family: monospace;
  color: var(--foreground);
}

.widget-preview-card.is-streaming {
  opacity: 0.9;
}

.widget-preview-frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}

.widget-chat-composer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px 4px;
  background: var(--paper);
  border-top: 1px solid var(--rule-soft);
}

.widget-question-panel {
  width: 100%;
  flex-shrink: 0;
  margin-top: auto;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--rule);
  border-radius: 14px;
  background: var(--paper);
  overflow: hidden;
}

.widget-question-option-list {
  display: flex;
  flex-direction: column;
}

.widget-question-option {
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--rule-soft);
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  padding: 10px 14px;
  font-family: var(--sans);
  font-size: 12px;
  line-height: 1.3;
  text-align: left;
  cursor: pointer;
}

.widget-question-option:hover {
  background: var(--paper-2);
}

.widget-question-custom {
  display: grid;
  grid-template-columns: 1fr 30px;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
}

.widget-question-custom-input {
  min-width: 0;
  height: 30px;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 12px;
  line-height: 1.2;
  padding: 0;
  outline: none;
}

.widget-question-custom-input:focus {
  outline: none;
}

.widget-question-custom-send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--rule-soft);
  border-radius: 50%;
  background: var(--paper);
  color: var(--ink);
  cursor: pointer;
}

.widget-question-custom-send:hover:not(:disabled) {
  background: var(--ink);
  border-color: var(--ink);
  color: var(--paper);
}

.widget-question-custom-send:disabled {
  opacity: 0.4;
  cursor: default;
}

.composer-selection-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  max-width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--bg-soft, #f3f3f3);
  font-family: var(--sans);
  font-size: 11.5px;
  color: var(--ink);
}

.composer-selection-marker {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.composer-selection-selector {
  font-family: var(--mono);
  font-size: 11px;
  background: var(--paper);
  padding: 1px 4px;
  border-radius: 3px;
}

.composer-selection-text {
  color: var(--ink-soft);
  font-style: italic;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

.composer-selection-clear {
  margin-left: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--ink-soft);
  padding: 0;
  display: inline-flex;
  align-items: center;
}

.composer-selection-clear:hover {
  color: var(--ink);
}

.widget-chat-input {
  width: 100%;
  box-sizing: border-box;
  min-height: 44px;
  max-height: 110px;
  resize: none;
  overflow-y: auto;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.4;
  padding: 10px 12px;
  outline: none;
}

.widget-chat-input:focus {
  border-color: var(--ink);
}

.widget-composer-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.widget-composer-tools {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.widget-tool-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--ink-mute);
  cursor: pointer;
}

.widget-tool-btn:hover,
.widget-tool-btn:focus-visible,
.widget-tool-btn.active {
  color: var(--ink);
  border-color: var(--rule);
  background: var(--paper-2);
  outline: none;
}

.widget-tool-btn.dotted::after {
  content: "";
  position: absolute;
  bottom: 3px;
  right: 3px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ink);
}

.widget-tool-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.widget-tool-library,
.widget-tool-mode {
  width: auto;
  padding: 0 10px;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-soft);
}

.widget-tool-library span,
.widget-tool-mode span {
  font-size: 12px;
}

.widget-tool-mode {
  padding-right: 8px;
}

.widget-chat-send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--rule);
  background: var(--paper);
  color: var(--ink);
  cursor: pointer;
  flex-shrink: 0;
}

.widget-chat-send:hover:not(:disabled) {
  background: var(--ink);
  border-color: var(--ink);
  color: var(--paper);
}

.widget-chat-send:disabled {
  opacity: 0.4;
  cursor: default;
}

.widget-chat-cancel {
  border-color: var(--err);
  color: var(--err);
}

.composer-attachments {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 2px 0;
}

.composer-image-chip {
  position: relative;
  flex: 0 0 auto;
  width: 54px;
  height: 42px;
}

.composer-image-chip img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
}

.composer-image-chip button {
  position: absolute;
  top: -5px;
  right: -5px;
  width: 18px;
  height: 18px;
  border: 1px solid var(--rule);
  border-radius: 50%;
  background: var(--paper);
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.chat-error {
  margin: 0;
  color: var(--err);
  font-family: var(--sans);
  font-size: 12px;
}

.widget-card {
  position: relative;
  width: 100%;
  text-align: left;
  border: 1px solid var(--rule);
  background: var(--paper);
  border-radius: var(--r-md);
  padding: 12px 14px;
  cursor: pointer;
  font-family: var(--sans);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.widget-card:hover:not(.disabled) {
  border-color: var(--ink);
}

.widget-card:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.widget-card.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.widget-delete {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--ink-mute);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.widget-card:hover .widget-delete,
.widget-card:focus-within .widget-delete,
.widget-delete:focus-visible {
  opacity: 1;
}

.widget-delete:hover {
  color: var(--err);
  background: var(--paper-2);
  border-color: var(--rule);
}

.widget-delete:disabled {
  opacity: 0.4;
  cursor: progress;
}

/* ---------- Minimal redesign ---------- */

.widget-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--rule-soft);
}

.widget-breadcrumb {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--ink-mute);
  text-transform: uppercase;
}

.widget-panel-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: var(--r-sm);
  color: var(--ink-mute);
  cursor: pointer;
}

.widget-panel-close:hover {
  color: var(--ink);
  background: var(--paper-2);
}

.widget-tab-strip {
  display: flex;
  gap: 2px;
  padding: 8px 14px 4px;
}

.widget-tab-strip button {
  background: transparent;
  border: 0;
  color: var(--ink-mute);
  padding: 4px 10px;
  border-radius: var(--r-sm);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
}

.widget-tab-strip button.active {
  color: var(--ink);
  background: var(--paper-2);
}

.widget-empty-state {
  padding: 28px 6px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.widget-empty-heading {
  font-family: var(--serif);
  font-size: 28px;
  letter-spacing: -0.015em;
  line-height: 1.15;
  margin: 0;
  color: var(--ink);
  font-weight: 400;
}

.widget-empty-heading em {
  font-style: italic;
}

.widget-empty-sub {
  margin: 0;
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-soft);
}

.widget-empty-recents {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--rule-soft);
}

.widget-recent-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--rule-soft);
  cursor: pointer;
  color: var(--ink);
  font-family: var(--sans);
  font-size: 13px;
}

.widget-recent-row:hover,
.widget-recent-row:focus-visible {
  background: var(--paper-2);
  outline: none;
}

.widget-recent-ordinal {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-mute);
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.widget-recent-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-recent-arrow {
  color: var(--ink-mute);
  opacity: 0;
  font-size: 14px;
  flex-shrink: 0;
}

.widget-recent-row:hover .widget-recent-arrow,
.widget-recent-row:focus-visible .widget-recent-arrow {
  opacity: 1;
  color: var(--ink);
}

.widget-empty-foot {
  margin: 14px 0 0;
  font-family: var(--sans);
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-mute);
  font-style: italic;
}

.widget-popover {
  position: absolute;
  bottom: calc(100% + 6px);
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-3);
  padding: 12px;
  z-index: 8;
  width: 260px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.widget-popover-library {
  right: 38px;
  width: 280px;
  max-height: 360px;
}

.widget-popover-mode {
  left: 34px;
  width: 220px;
  padding: 6px;
  gap: 4px;
}

.widget-mode-menu-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink);
  padding: 8px 9px;
  text-align: left;
  cursor: pointer;
}

.widget-mode-menu-item:hover,
.widget-mode-menu-item.active {
  background: var(--paper-2);
}

.widget-mode-menu-item.active .widget-mode-menu-title {
  color: var(--accent);
}

.widget-mode-menu-title {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.widget-mode-menu-sub {
  font-family: var(--sans);
  font-size: 11px;
  line-height: 1.35;
  color: var(--ink-mute);
}

.widget-popover-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.widget-popover-label {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.14em;
  color: var(--ink-mute);
  text-transform: uppercase;
}

.widget-popover-labelrow {
  display: flex;
  align-items: center;
  gap: 6px;
}

.widget-help-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--rule);
  background: var(--paper);
  color: var(--ink-mute);
  font-family: var(--mono);
  font-size: 9px;
  line-height: 1;
  cursor: help;
  user-select: none;
}

.widget-help-tip:hover,
.widget-help-tip:focus-visible {
  color: var(--ink);
  border-color: var(--ink);
  outline: none;
}

.widget-help-bubble {
  position: absolute;
  bottom: calc(100% + 6px);
  left: -4px;
  width: 220px;
  padding: 8px 10px;
  background: var(--ink);
  color: var(--paper);
  border-radius: var(--r-sm);
  box-shadow: var(--shadow-3);
  font-family: var(--sans);
  font-size: 11px;
  line-height: 1.45;
  letter-spacing: normal;
  text-transform: none;
  font-weight: 400;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
  z-index: 12;
}

.widget-help-bubble strong {
  font-weight: 600;
  color: var(--paper);
}

.widget-help-tip:hover .widget-help-bubble,
.widget-help-tip:focus-visible .widget-help-bubble {
  opacity: 1;
}

.widget-popover-headrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.widget-popover-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  background: transparent;
  border: 0;
  color: var(--ink-mute);
  cursor: pointer;
}

.widget-popover-close:hover {
  color: var(--ink);
}

.widget-popover-helper {
  margin: 0;
  font-family: var(--sans);
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-mute);
}

.widget-popover-search {
  padding: 6px 8px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink);
  outline: none;
}

.widget-popover-search:focus {
  border-color: var(--ink);
}

.widget-popover-copylink {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 0;
  padding: 2px 0;
  color: var(--ink-soft);
  font-family: var(--sans);
  font-size: 12px;
  cursor: pointer;
}

.widget-popover-copylink:hover:not(:disabled) {
  color: var(--ink);
}

.widget-popover-copylink:disabled {
  opacity: 0.45;
  cursor: default;
}

.widget-popover-copybox {
  border: 1px solid var(--rule-soft);
  border-radius: var(--r-sm);
  padding: 6px 8px;
  background: var(--paper-2);
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 140px;
  overflow-y: auto;
}

.widget-popover-copybox ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.widget-popover-copybox li {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 6px;
}

.widget-popover-copyname {
  font-family: var(--serif);
  font-size: 12px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-popover-copykind {
  font-size: 10px;
  color: var(--ink-mute);
}

.widget-popover-copybtn {
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: var(--r-xs);
  padding: 2px 8px;
  font-size: 11px;
  font-family: var(--mono);
  color: var(--ink-soft);
  cursor: pointer;
}

.widget-popover-copybtn:hover:not(:disabled) {
  color: var(--ink);
  border-color: var(--ink);
}

.widget-popover-copybtn:disabled {
  opacity: 0.5;
  cursor: default;
}

.widget-popover-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
}

.widget-popover-item {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--rule-soft);
}

.widget-popover-item:last-child {
  border-bottom: 0;
}

.widget-popover-itembtn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  background: transparent;
  border: 0;
  padding: 0;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
}

.widget-popover-itemname {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.widget-popover-itemkind {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--ink-mute);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.widget-popover-itemtag {
  font-size: 10px;
  color: var(--ink-soft);
  background: var(--paper-2);
  padding: 2px 6px;
  border-radius: var(--r-xs);
}

.widget-popover-rowbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: 0;
  color: var(--ink-mute);
  cursor: pointer;
  opacity: 0;
}

.widget-popover-item:hover .widget-popover-rowbtn,
.widget-popover-rowbtn:focus-visible {
  opacity: 1;
}

.widget-popover-rowbtn:hover {
  color: var(--ink);
}

.widget-popover-rowbtn-danger:hover {
  color: var(--err);
}

.widget-popover-rowbtn:disabled {
  opacity: 0.4;
  cursor: progress;
}

.widget-popover-empty {
  margin: 4px 0;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-mute);
  font-style: italic;
}

.widget-popover-error {
  margin: 4px 0 0;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--err);
}

.widget-footer-status {
  flex-shrink: 0;
  margin: 0;
  padding: 6px 16px 10px;
  background: var(--paper);
  text-align: center;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--ink-mute);
  text-transform: lowercase;
}
</style>
