<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { workspaceApi } from "@/api/workspace";
import { llmApi } from "@/api/llm";
import { useSessionStore } from "@/stores/session";
import Icon from "@/components/Icon.vue";
import type { InterpretQuickOption, LlmCapability, LlmModelConfig, Workspace, WorkspacePatch } from "@/api/types";

const props = defineProps<{
  open: boolean;
  userName?: string | null;
  userEmail?: string | null;
  canStartSession?: boolean;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "start-session"): void;
  (e: "sign-out"): void;
  (e: "saved", workspace: Workspace): void;
}>();

const tab = ref<"session" | "llm" | "display" | "account">("llm");
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const status = ref<string | null>(null);
const error = ref<string | null>(null);
const clearKey = ref(false);
const advancedModelId = ref<string | null>(null);
const session = useSessionStore();

const defaultInterpretQuickOptions: InterpretQuickOption[] = [
  { label: "AI", instruction: "in plain English" },
  { label: "Simple definition", instruction: "show a simple definition" },
  { label: "Why it matters", instruction: "explain why this matters for this slide" },
];

const capabilities: Array<{ key: LlmCapability; title: string; description: string }> = [
  {
    key: "inline_write",
    title: "Inline content writing",
    description: "Continue or rewrite paragraphs from a prompt.",
  },
  {
    key: "interpret",
    title: "Interpret on selected text",
    description: "Explain or translate selected slide text.",
  },
  {
    key: "widget_generate",
    title: "Generate widgets (HTML/JS)",
    description: "Draft a working widget from a prompt.",
  },
];

const form = reactive({
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  models: [
    {
      id: "gpt-4.1-mini",
      supports_image_input: false,
    },
  ] as LlmModelConfig[],
  capabilityModels: {
    inline_write: "gpt-4.1-mini",
    interpret: "gpt-4.1-mini",
    widget_generate: "gpt-4.1-mini",
  } as Record<LlmCapability, string | null>,
  interpretQuickOptions: defaultInterpretQuickOptions.map((option) => ({ ...option })) as InterpretQuickOption[],
  keyConfigured: false,
  logLlmPromptsForTranscript: false,
});

const advancedModel = computed(() => form.models.find((model) => model.id === advancedModelId.value) || null);

function defaultModel(id = "gpt-4.1-mini"): LlmModelConfig {
  return {
    id,
    supports_image_input: false,
    max_context_window: null,
    max_output_tokens: null,
    temperature: null,
    top_p: null,
    frequency_penalty: null,
    presence_penalty: null,
  };
}

function cleanNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cleanModel(model: LlmModelConfig): LlmModelConfig {
  return {
    id: model.id.trim(),
    supports_image_input: !!model.supports_image_input,
    max_context_window: cleanNumber(model.max_context_window),
    max_output_tokens: cleanNumber(model.max_output_tokens),
    temperature: cleanNumber(model.temperature),
    top_p: cleanNumber(model.top_p),
    frequency_penalty: cleanNumber(model.frequency_penalty),
    presence_penalty: cleanNumber(model.presence_penalty),
  };
}

function cleanInterpretQuickOptions(options: InterpretQuickOption[]): InterpretQuickOption[] {
  return options
    .map((option) => ({
      label: option.label.trim(),
      instruction: option.instruction.trim(),
    }))
    .filter((option) => option.label && option.instruction)
    .slice(0, 3);
}

function applyCapabilityDefaults(primaryModelId: string, ws?: Workspace) {
  for (const cap of capabilities) {
    const assigned = ws?.llm_capability_models?.[cap.key];
    if (assigned === null) form.capabilityModels[cap.key] = null;
    else form.capabilityModels[cap.key] = assigned || primaryModelId;
  }
}

function applyWorkspace(ws: Workspace) {
  form.baseUrl = ws.llm_base_url || "https://api.openai.com/v1";
  const models = (ws.llm_models?.length ? ws.llm_models : [defaultModel(ws.llm_model || "gpt-4.1-mini")])
    .map(cleanModel)
    .filter((model) => model.id);
  form.models = models.length ? models : [defaultModel()];
  applyCapabilityDefaults(form.models[0].id, ws);
  const quickOptions = cleanInterpretQuickOptions(ws.interpret_quick_options || []);
  form.interpretQuickOptions = (quickOptions.length ? quickOptions : defaultInterpretQuickOptions)
    .map((option) => ({ ...option }));
  form.keyConfigured = ws.llm_key_configured;
  form.logLlmPromptsForTranscript = ws.log_llm_prompts_for_transcript ?? false;
  form.apiKey = "";
  clearKey.value = false;
  advancedModelId.value = null;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    applyWorkspace(await workspaceApi.get());
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load settings.";
  } finally {
    loading.value = false;
  }
}

async function save() {
  const saved = await saveWorkspace();
  if (saved) status.value = "Saved.";
}

async function saveWorkspace(): Promise<Workspace | null> {
  saving.value = true;
  error.value = null;
  status.value = null;
  try {
    const models = form.models.map(cleanModel).filter((model) => model.id);
    if (!models.length) throw new Error("Add at least one model id.");
    const ids = new Set<string>();
    for (const model of models) {
      if (ids.has(model.id)) throw new Error(`Duplicate model id: ${model.id}`);
      ids.add(model.id);
    }
    const capabilityModels = Object.fromEntries(
      capabilities.map((cap) => {
        const modelId = form.capabilityModels[cap.key];
        return [cap.key, modelId && ids.has(modelId) ? modelId : null];
      }),
    ) as Record<LlmCapability, string | null>;
    const patch: WorkspacePatch = {
      llm_base_url: form.baseUrl,
      llm_model: models[0].id,
      llm_models: models,
      llm_capability_models: capabilityModels,
      llm_caps: Object.fromEntries(capabilities.map((cap) => [cap.key, capabilityModels[cap.key] !== null])),
      interpret_quick_options: cleanInterpretQuickOptions(form.interpretQuickOptions),
      log_llm_prompts_for_transcript: form.logLlmPromptsForTranscript,
    };
    if (form.apiKey.trim() || clearKey.value) patch.llm_api_key = form.apiKey.trim();
    const saved = await workspaceApi.patch(patch);
    applyWorkspace(saved);
    session.setInterpretQuickOptions(saved.interpret_quick_options || []);
    emit("saved", saved);
    return saved;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not save settings.";
    return null;
  } finally {
    saving.value = false;
  }
}

async function startSessionFromSettings() {
  const saved = await saveWorkspace();
  if (!saved) return;
  emit("start-session");
}

async function testConnection() {
  testing.value = true;
  error.value = null;
  status.value = null;
  try {
    await save();
    const text = await llmApi.completeText({
      purpose: "interpret",
      prompt: "Reply with exactly OK.",
      context: { check: "settings_test" },
    });
    status.value = `Connection OK: ${text.slice(0, 80) || "stream completed"}`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "LLM test failed.";
  } finally {
    testing.value = false;
  }
}

function addModel() {
  let suffix = form.models.length + 1;
  let id = "new-model";
  while (form.models.some((model) => model.id === id)) {
    suffix += 1;
    id = `new-model-${suffix}`;
  }
  form.models.push(defaultModel(id));
  advancedModelId.value = id;
}

function removeModel(modelId: string) {
  if (form.models.length <= 1) {
    error.value = "At least one model is required.";
    return;
  }
  const idx = form.models.findIndex((model) => model.id === modelId);
  if (idx === -1) return;
  form.models.splice(idx, 1);
  const fallback = form.models[0]?.id || null;
  for (const cap of capabilities) {
    if (form.capabilityModels[cap.key] === modelId) form.capabilityModels[cap.key] = fallback;
  }
  if (advancedModelId.value === modelId) advancedModelId.value = null;
}

function onModelIdInput(model: LlmModelConfig, nextId: string) {
  const previous = model.id;
  model.id = nextId;
  for (const cap of capabilities) {
    if (form.capabilityModels[cap.key] === previous) form.capabilityModels[cap.key] = nextId;
  }
  if (advancedModelId.value === previous) advancedModelId.value = nextId;
}

function setCapabilityModel(key: LlmCapability, raw: string) {
  form.capabilityModels[key] = raw || null;
}

function addInterpretQuickOption() {
  if (form.interpretQuickOptions.length >= 3) return;
  form.interpretQuickOptions.push({ label: "", instruction: "" });
}

function removeInterpretQuickOption(index: number) {
  form.interpretQuickOptions.splice(index, 1);
}

function resetInterpretQuickOptions() {
  form.interpretQuickOptions = defaultInterpretQuickOptions.map((option) => ({ ...option }));
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      status.value = null;
      error.value = null;
      void load();
    }
  },
  { immediate: true },
);

watch(tab, () => {
  status.value = null;
  error.value = null;
});
</script>

<template>
  <div
    v-if="props.open"
    class="settings-backdrop fade-in"
    @click.self="emit('close')"
  >
    <aside class="settings-drawer slide-in-right">
      <header class="settings-header">
        <div>
          <div class="t-kicker" style="margin-bottom: 4px">Settings</div>
          <div class="settings-title">How SLAIDES behaves.</div>
        </div>
        <button class="btn btn-ghost btn-sm" @click="emit('close')" title="Close">
          <Icon name="x" :size="14" />
        </button>
      </header>

      <nav class="settings-tabs">
        <button
          v-for="[key, label] in [
            ['session', 'Session'],
            ['llm', 'LLM'],
            ['display', 'Display'],
            ['account', 'Account'],
          ] as const"
          :key="key"
          @click="tab = key"
          :class="{ active: tab === key }"
        >
          {{ label }}
        </button>
      </nav>

      <main class="settings-body">
        <div v-if="loading" class="t-meta">Loading settings...</div>

        <template v-else>
          <section v-if="tab === 'session'" class="settings-stack">
            <div class="settings-block">
              <h3>Publish & start a session</h3>
              <p>Take this deck live. Audience members join by code or share link.</p>
              <button
                class="btn btn-primary"
                :disabled="!props.canStartSession || saving"
                style="width: 100%; justify-content: center"
                @click="startSessionFromSettings"
              >
                <span class="live-dot" />
                {{ saving ? "Saving..." : "Start session" }}
              </button>
            </div>
            <div class="settings-block">
              <h3>Recordings & transcripts</h3>
              <p>Transcript toggles are part of milestone 5. Interaction logs are already captured for live sessions.</p>
            </div>
            <div class="settings-block">
              <h3>AI interpretation quick options</h3>
              <p>Participants see up to three shortcuts after selecting slide or widget text.</p>
              <div class="quick-options-list">
                <div
                  v-for="(option, index) in form.interpretQuickOptions"
                  :key="index"
                  class="quick-option-row"
                >
                  <label>
                    <span class="field-label">Button label</span>
                    <input
                      v-model="option.label"
                      class="input"
                      maxlength="32"
                      placeholder="Define"
                    />
                  </label>
                  <label>
                    <span class="field-label">Prompt instruction</span>
                    <input
                      v-model="option.instruction"
                      class="input"
                      maxlength="240"
                      placeholder="show a simple definition"
                    />
                  </label>
                  <button
                    class="btn btn-ghost btn-sm quick-option-remove"
                    type="button"
                    title="Remove option"
                    @click="removeInterpretQuickOption(index)"
                  >
                    <Icon name="trash" :size="13" />
                  </button>
                </div>
              </div>
              <div class="quick-option-actions">
                <button
                  class="btn btn-sm"
                  type="button"
                  :disabled="form.interpretQuickOptions.length >= 3"
                  @click="addInterpretQuickOption"
                >
                  <Icon name="plus" :size="13" />
                  Add option
                </button>
                <button class="btn btn-ghost btn-sm" type="button" @click="resetInterpretQuickOptions">
                  Reset defaults
                </button>
              </div>
              <small class="settings-hint">Leave all options empty to use the built-in defaults during sessions.</small>
            </div>
            <div class="settings-actions">
              <button class="btn" :disabled="saving || testing" @click="save">
                <Icon name="check" :size="14" />
                {{ saving ? "Saving..." : "Save session settings" }}
              </button>
            </div>

            <p v-if="status" class="status-text">{{ status }}</p>
            <p v-if="error" class="error-text">{{ error }}</p>
          </section>

          <section v-if="tab === 'llm'" class="settings-stack">
            <div class="settings-block">
              <h3>OpenAI-compatible endpoint</h3>
              <p>Keys stay on the server. Browser calls go through the SLAIDES LLM proxy.</p>
              <label class="field-label">Base URL</label>
              <input v-model="form.baseUrl" class="input mono-input" placeholder="https://api.openai.com/v1" />
              <label class="field-label field-gap">API key</label>
              <input
                v-model="form.apiKey"
                class="input mono-input"
                type="password"
                :placeholder="form.keyConfigured && !clearKey ? 'Saved key configured - enter a new key to replace it' : 'sk-...'"
              />
              <button
                v-if="form.keyConfigured && !clearKey"
                class="btn btn-ghost btn-sm"
                style="margin-top: 8px"
                @click="clearKey = true; form.apiKey = ''"
              >
                Clear saved key
              </button>
            </div>

            <div class="settings-block">
              <h3>Model library</h3>
              <p>Add any model id accepted by the configured endpoint.</p>
              <div class="model-list">
                <div v-for="model in form.models" :key="model.id" class="model-card">
                  <div class="model-fields">
                    <label>
                      <span class="field-label">Model id</span>
                      <input
                        class="input mono-input"
                        :value="model.id"
                        placeholder="gpt-4.1-mini"
                        @input="onModelIdInput(model, ($event.target as HTMLInputElement).value)"
                      />
                    </label>
                  </div>
                  <div class="model-actions">
                    <span class="model-flags">
                      <Icon v-if="model.supports_image_input" name="eye" :size="13" />
                      {{ model.supports_image_input ? "Supports image input" : "Text input only" }}
                    </span>
                    <div>
                      <button class="btn btn-sm" type="button" @click="advancedModelId = model.id">
                        <Icon name="gear" :size="13" />
                        Advanced
                      </button>
                      <button class="btn btn-ghost btn-sm" type="button" title="Remove model" @click="removeModel(model.id)">
                        <Icon name="trash" :size="13" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <button class="btn btn-sm" type="button" @click="addModel">
                <Icon name="plus" :size="13" />
                Add model
              </button>
            </div>

            <div class="settings-block">
              <h3>What the LLM can do</h3>
              <p>Assign a model to each capability, or pick None to disable it.</p>
              <label v-for="cap in capabilities" :key="cap.key" class="cap-row">
                <span>
                  <strong>{{ cap.title }}</strong>
                  <small>{{ cap.description }}</small>
                </span>
                <select
                  class="cap-select"
                  :value="form.capabilityModels[cap.key] || ''"
                  @change="setCapabilityModel(cap.key, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">None</option>
                  <option v-for="model in form.models" :key="model.id" :value="model.id">
                    {{ model.id }}
                  </option>
                </select>
              </label>
            </div>

            <div class="settings-block">
              <h3>Transcript privacy</h3>
              <label class="cap-row">
                <span>
                  <strong>Log LLM prompts for transcript</strong>
                  <small>When enabled, selected text and prompts are encrypted and stored for transcript replay.</small>
                </span>
                <Toggle v-model="form.logLlmPromptsForTranscript" />
              </label>
            </div>

            <div class="settings-actions">
              <button class="btn" :disabled="saving || testing" @click="save">
                <Icon name="check" :size="14" />
                {{ saving ? "Saving..." : "Save" }}
              </button>
              <button class="btn btn-primary" :disabled="saving || testing" @click="testConnection">
                {{ testing ? "Testing..." : "Test connection" }}
              </button>
            </div>

            <p v-if="status" class="status-text">{{ status }}</p>
            <p v-if="error" class="error-text">{{ error }}</p>

            <div v-if="advancedModel" class="advanced-panel scale-in">
              <header class="advanced-header">
                <div>
                  <div class="t-kicker" style="margin-bottom: 4px">Advanced</div>
                  <div class="advanced-title">Model parameters</div>
                  <p>Leave anything blank to use the endpoint's default.</p>
                </div>
                <button class="btn btn-ghost btn-sm" type="button" @click="advancedModelId = null" title="Close">
                  <Icon name="x" :size="14" />
                </button>
              </header>
              <div class="advanced-body">
                <div class="advanced-model-pill">{{ advancedModel.id }}</div>

                <label class="check-row">
                  <input v-model="advancedModel.supports_image_input" type="checkbox" />
                  <span>
                    <strong>Supports image input</strong>
                    <small>Shows image attachment controls for widget generation.</small>
                  </span>
                </label>

                <div class="advanced-grid">
                  <label>
                    <span class="field-label">Max context window (tokens)</span>
                    <input v-model.number="advancedModel.max_context_window" class="input mono-input" type="number" min="1" placeholder="128000" />
                  </label>
                  <label>
                    <span class="field-label">Max output tokens</span>
                    <input v-model.number="advancedModel.max_output_tokens" class="input mono-input" type="number" min="1" placeholder="4096" />
                  </label>
                  <label>
                    <span class="field-label">Temperature</span>
                    <input v-model.number="advancedModel.temperature" class="input mono-input" type="number" min="0" max="2" step="0.01" placeholder="e.g. 0.7" />
                  </label>
                  <label>
                    <span class="field-label">Top-p</span>
                    <input v-model.number="advancedModel.top_p" class="input mono-input" type="number" min="0" max="1" step="0.01" placeholder="e.g. 1.0" />
                  </label>
                  <label>
                    <span class="field-label">Frequency penalty</span>
                    <input v-model.number="advancedModel.frequency_penalty" class="input mono-input" type="number" min="-2" max="2" step="0.01" placeholder="Endpoint default" />
                  </label>
                  <label>
                    <span class="field-label">Presence penalty</span>
                    <input v-model.number="advancedModel.presence_penalty" class="input mono-input" type="number" min="-2" max="2" step="0.01" placeholder="Endpoint default" />
                  </label>
                </div>
              </div>
              <footer class="advanced-footer">
                <span class="t-mono">changes save with settings</span>
                <button class="btn btn-primary btn-sm" type="button" @click="advancedModelId = null">Done</button>
              </footer>
            </div>
          </section>

          <section v-if="tab === 'display'" class="settings-stack">
            <div class="settings-block">
              <h3>Display</h3>
              <p>Dark mode and editor density persistence are coming in a later release.</p>
            </div>
          </section>

          <section v-if="tab === 'account'" class="settings-stack">
            <div class="settings-block">
              <h3>Signed in as</h3>
              <div class="account-row">
                <span class="avatar">{{ (props.userName || props.userEmail || "A").slice(0, 1).toUpperCase() }}</span>
                <span>
                  <strong>{{ props.userName || "Instructor" }}</strong>
                  <small>{{ props.userEmail || "unknown" }}</small>
                </span>
              </div>
            </div>
            <button class="btn danger-btn" @click="emit('sign-out')">Sign out</button>
          </section>
        </template>
      </main>
    </aside>
  </div>
</template>

<style scoped>
.settings-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(11, 13, 16, 0.42);
  display: flex;
  justify-content: flex-end;
}

.settings-drawer {
  width: min(460px, 100vw);
  height: 100%;
  background: var(--paper);
  border-left: 1px solid var(--rule);
  box-shadow: var(--shadow-4);
  display: flex;
  flex-direction: column;
}

.settings-header {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.settings-title {
  font-family: var(--serif);
  font-size: 22px;
  letter-spacing: 0;
}

.settings-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 14px 0;
}

.settings-tabs button {
  border: none;
  background: transparent;
  color: var(--ink-soft);
  padding: 6px 10px;
  border-radius: var(--r-sm);
  font-family: var(--sans);
  font-weight: 600;
  font-size: 12px;
}

.settings-tabs button.active {
  background: var(--paper-2);
  color: var(--ink);
}

.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 22px 24px;
}

.settings-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.settings-block {
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 14px;
  background: var(--paper);
}

.settings-block h3 {
  margin: 0 0 4px;
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 500;
}

.settings-block p {
  margin: 0 0 12px;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.45;
}

.field-gap {
  margin-top: 12px;
}

.mono-input {
  font-family: var(--mono);
  font-size: 12px;
}

.model-list {
  display: grid;
  gap: 10px;
  margin-bottom: 10px;
}

.model-card {
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 12px;
  background: var(--paper-2);
}

.model-fields {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.model-actions {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.model-actions > div,
.model-flags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.model-flags {
  min-width: 0;
  color: var(--ink-soft);
  font-size: 12px;
}

.quick-options-list {
  display: grid;
  gap: 10px;
  margin-bottom: 10px;
}

.quick-option-row {
  display: grid;
  grid-template-columns: 0.58fr 1fr auto;
  align-items: end;
  gap: 8px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper-2);
  padding: 10px;
}

.quick-option-remove {
  width: 32px;
  height: 32px;
  padding: 0;
  justify-content: center;
  color: var(--err);
}

.quick-option-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.settings-hint {
  display: block;
  margin-top: 10px;
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.35;
}

.cap-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 0;
  border-top: 1px solid var(--rule-soft);
}

.cap-row:first-of-type {
  border-top: none;
}

.cap-row span {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.cap-row strong,
.account-row strong {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
}

.cap-row small,
.account-row small {
  font-size: 12px;
  color: var(--ink-soft);
}

.cap-select {
  flex: 0 0 150px;
  min-width: 0;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
  color: var(--ink);
  padding: 7px 30px 7px 10px;
  font-family: var(--sans);
  font-size: 12px;
}

.settings-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.advanced-panel {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 95;
  width: min(460px, 100vw);
  height: 100%;
  background: var(--paper);
  border-left: 1px solid var(--rule);
  box-shadow: var(--shadow-4);
  display: flex;
  flex-direction: column;
}

.advanced-header {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  gap: 18px;
}

.advanced-header p {
  margin: 4px 0 0;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.4;
}

.advanced-title {
  font-family: var(--serif);
  font-size: 22px;
}

.advanced-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px 84px;
}

.advanced-model-pill {
  display: inline-flex;
  max-width: 100%;
  border: 1px solid var(--accent);
  border-radius: 999px;
  color: var(--accent);
  padding: 5px 10px;
  font-family: var(--mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.check-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: 12px;
  margin: 20px 0;
}

.check-row input {
  margin-top: 2px;
}

.check-row span {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.check-row strong {
  font-size: 13px;
}

.check-row small {
  color: var(--ink-soft);
  font-size: 12px;
}

.advanced-grid {
  display: grid;
  gap: 12px;
}

.advanced-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  border-top: 1px solid var(--rule);
  background: var(--paper);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 22px;
  color: var(--ink-soft);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--live);
}

.status-text,
.error-text {
  margin: 14px 0 0;
  font-size: 12px;
  font-family: var(--sans);
}

.status-text {
  color: var(--ok);
}

.error-text {
  color: var(--err);
}

.account-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: var(--ink);
  color: var(--paper);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--serif);
  font-size: 18px;
}

.danger-btn {
  justify-content: center;
  color: var(--err);
  border-color: var(--err);
}

@media (max-width: 560px) {
  .model-fields {
    grid-template-columns: 1fr;
  }

  .cap-row {
    align-items: stretch;
    flex-direction: column;
  }

  .cap-select {
    flex-basis: auto;
    width: 100%;
  }

  .quick-option-row {
    grid-template-columns: 1fr;
  }

  .quick-option-remove {
    width: 100%;
  }
}
</style>
