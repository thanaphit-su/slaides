<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/Icon.vue";

/**
 * Recursive form renderer for the SLAIDES props_schema (a JSON-Schema subset
 * — see docs/WIDGETS_V2.md). Emits `update:modelValue` with a fresh object on
 * every change. Parents own the value and decide when to persist.
 *
 * Supported keywords (matches the backend validator):
 *   type: "string" | "number" | "integer" | "boolean" | "array" | "object"
 *   enum, default, description, items, properties
 *   minLength / maxLength / minimum / maximum
 *
 * SLAIDES extension:
 *   enum.from: "<other_prop>.<key>" — the picker's options are pulled live
 *   from the current form's sibling array (e.g. correct_answer's options come
 *   from the same form's choices[].id). For nested objects and array items,
 *   "siblings" means the keys at the same level of nesting.
 */

type JsonValue = unknown;
type JsonObject = Record<string, unknown>;
type Schema = Record<string, unknown>;

const props = withDefaults(
  defineProps<{
    schema: Schema;
    modelValue: JsonObject;
    /** Internal-only: human-readable path used in error labels. */
    pathPrefix?: string;
  }>(),
  { pathPrefix: "" },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: JsonObject): void;
}>();

interface Field {
  key: string;
  schema: Schema;
  label: string;
}

const declaredProperties = computed<Record<string, Schema>>(() => {
  const direct = props.schema?.properties as Record<string, Schema> | undefined;
  if (direct && typeof direct === "object") return direct;
  // The top-level schema may itself be the properties bag (older widgets do
  // this). Treat any plain map-of-schemas as properties.
  if (props.schema && typeof props.schema === "object" && !("type" in props.schema) && !("properties" in props.schema)) {
    return props.schema as Record<string, Schema>;
  }
  return {};
});

const fields = computed<Field[]>(() =>
  Object.entries(declaredProperties.value).map(([key, sub]) => ({
    key,
    schema: (sub || {}) as Schema,
    label: humanLabel(key, sub as Schema),
  })),
);

function humanLabel(key: string, sub: Schema): string {
  const explicit = (sub?.title as string | undefined) || (sub?.label as string | undefined);
  if (explicit) return explicit;
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function setField(key: string, value: JsonValue) {
  const next: JsonObject = { ...props.modelValue, [key]: value };
  emit("update:modelValue", next);
}

function defaultForSchema(schema: Schema): JsonValue {
  if ("default" in schema) return schema.default as JsonValue;
  const t = schema.type as string | undefined;
  if (t === "string") return "";
  if (t === "number" || t === "integer") return 0;
  if (t === "boolean") return false;
  if (t === "array") return [];
  if (t === "object") return {};
  return null;
}

function resolveEnumFrom(spec: string): JsonValue[] | null {
  if (typeof spec !== "string" || !spec.includes(".")) return null;
  const [arrayKey, field] = spec.split(".", 2);
  // Siblings of an enum.from field are the other keys of the current form's
  // modelValue — at the top level they live in `props.modelValue`; inside a
  // nested object form, `modelValue` is the sub-object, which is the right
  // scope; inside an array-item form, modelValue is the item object.
  const source = props.modelValue[arrayKey];
  if (!Array.isArray(source)) return null;
  const out: JsonValue[] = [];
  for (const entry of source) {
    if (entry && typeof entry === "object" && !Array.isArray(entry) && field in entry) {
      out.push((entry as JsonObject)[field]);
    }
  }
  return out;
}

function asArray(value: JsonValue): JsonValue[] {
  return Array.isArray(value) ? value : [];
}

function setArrayItem(key: string, index: number, value: JsonValue) {
  const current = asArray(props.modelValue[key]);
  const next = current.slice();
  next[index] = value;
  setField(key, next);
}

function addArrayItem(key: string, itemSchema: Schema) {
  const current = asArray(props.modelValue[key]);
  setField(key, [...current, defaultForSchema(itemSchema)]);
}

function removeArrayItem(key: string, index: number) {
  const current = asArray(props.modelValue[key]);
  const next = current.slice();
  next.splice(index, 1);
  setField(key, next);
}

function moveArrayItem(key: string, index: number, delta: -1 | 1) {
  const current = asArray(props.modelValue[key]);
  const target = index + delta;
  if (target < 0 || target >= current.length) return;
  const next = current.slice();
  [next[index], next[target]] = [next[target], next[index]];
  setField(key, next);
}
</script>

<template>
  <div class="props-form">
    <template v-if="fields.length === 0">
      <p class="props-empty t-meta">This widget exposes no editable properties. Use "Edit code" to change its content.</p>
    </template>

    <template v-for="field in fields" :key="field.key">
      <div class="props-field">
        <label class="props-label">
          <span>{{ field.label }}</span>
          <span v-if="(field.schema as any)?.description" class="props-help t-meta">
            {{ (field.schema as any).description }}
          </span>
        </label>

        <!-- String / number / integer / boolean primitives -->
        <template v-if="(field.schema as any)?.type === 'boolean'">
          <label class="props-toggle">
            <input
              type="checkbox"
              :checked="!!modelValue[field.key]"
              @change="setField(field.key, ($event.target as HTMLInputElement).checked)"
            />
            <span class="props-toggle-label">{{ modelValue[field.key] ? 'On' : 'Off' }}</span>
          </label>
        </template>

        <template v-else-if="Array.isArray((field.schema as any)?.enum) || typeof (field.schema as any)?.['enum.from'] === 'string'">
          <select
            class="props-select"
            :value="modelValue[field.key] ?? ''"
            @change="setField(field.key, ($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>Choose…</option>
            <option
              v-for="opt in ((field.schema as any).enum || resolveEnumFrom((field.schema as any)['enum.from']) || [])"
              :key="String(opt)"
              :value="String(opt)"
            >
              {{ String(opt) }}
            </option>
          </select>
        </template>

        <template v-else-if="(field.schema as any)?.type === 'number' || (field.schema as any)?.type === 'integer'">
          <input
            class="props-input"
            type="number"
            :step="(field.schema as any).type === 'integer' ? 1 : 'any'"
            :min="(field.schema as any).minimum"
            :max="(field.schema as any).maximum"
            :value="modelValue[field.key] ?? ''"
            @input="setField(field.key, Number(($event.target as HTMLInputElement).value))"
          />
        </template>

        <template v-else-if="(field.schema as any)?.type === 'string' || !(field.schema as any)?.type">
          <textarea
            v-if="((field.schema as any)?.maxLength ?? 0) > 80 || ((field.schema as any)?.format === 'multiline')"
            class="props-textarea"
            :maxlength="(field.schema as any)?.maxLength"
            :minlength="(field.schema as any)?.minLength"
            :value="(modelValue[field.key] as string) ?? ''"
            rows="3"
            @input="setField(field.key, ($event.target as HTMLTextAreaElement).value)"
          />
          <input
            v-else
            class="props-input"
            type="text"
            :maxlength="(field.schema as any)?.maxLength"
            :minlength="(field.schema as any)?.minLength"
            :value="(modelValue[field.key] as string) ?? ''"
            @input="setField(field.key, ($event.target as HTMLInputElement).value)"
          />
        </template>

        <!-- Array of primitives or objects -->
        <template v-else-if="(field.schema as any)?.type === 'array'">
          <div class="props-array">
            <div
              v-for="(item, idx) in asArray(modelValue[field.key])"
              :key="idx"
              class="props-array-row"
            >
              <div class="props-array-row-body">
                <!-- Nested PropsForm for object items so enum.from sees the row's siblings -->
                <PropsForm
                  v-if="(field.schema as any).items?.type === 'object'"
                  :schema="(field.schema as any).items"
                  :model-value="(item as JsonObject) || {}"
                  :path-prefix="`${pathPrefix}${field.key}[${idx}].`"
                  @update:model-value="setArrayItem(field.key, idx, $event)"
                />
                <!-- Primitive item: render an inline input -->
                <input
                  v-else
                  class="props-input"
                  type="text"
                  :value="String(item ?? '')"
                  @input="setArrayItem(field.key, idx, ($event.target as HTMLInputElement).value)"
                />
              </div>
              <div class="props-array-row-actions">
                <button class="btn btn-ghost btn-sm" type="button" :disabled="idx === 0" :title="`Move ${field.label} ${idx + 1} up`" @click="moveArrayItem(field.key, idx, -1)">
                  <Icon name="chevron_up" :size="12" />
                </button>
                <button class="btn btn-ghost btn-sm" type="button" :disabled="idx === asArray(modelValue[field.key]).length - 1" :title="`Move ${field.label} ${idx + 1} down`" @click="moveArrayItem(field.key, idx, 1)">
                  <Icon name="chevron_down" :size="12" />
                </button>
                <button class="btn btn-ghost btn-sm" type="button" :title="`Remove ${field.label} ${idx + 1}`" @click="removeArrayItem(field.key, idx)">
                  <Icon name="x" :size="12" />
                </button>
              </div>
            </div>
            <button
              class="btn btn-sm props-array-add"
              type="button"
              @click="addArrayItem(field.key, (field.schema as any).items || {})"
            >
              <Icon name="plus" :size="12" /> Add {{ field.label.toLowerCase() }}
            </button>
          </div>
        </template>

        <!-- Nested object -->
        <template v-else-if="(field.schema as any)?.type === 'object'">
          <div class="props-nested">
            <PropsForm
              :schema="field.schema"
              :model-value="(modelValue[field.key] as JsonObject) || {}"
              :path-prefix="`${pathPrefix}${field.key}.`"
              @update:model-value="setField(field.key, $event)"
            />
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.props-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.props-empty {
  margin: 0;
  color: var(--ink-soft);
}

.props-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.props-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  color: var(--ink);
  letter-spacing: 0.01em;
}

.props-help {
  font-weight: 400;
  color: var(--ink-soft);
}

.props-input,
.props-textarea,
.props-select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper);
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
}

.props-textarea {
  resize: vertical;
  min-height: 60px;
}

.props-input:focus-visible,
.props-textarea:focus-visible,
.props-select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

.props-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.props-toggle-label {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 11px;
}

.props-array {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px dashed var(--rule);
  border-radius: var(--r-sm);
  padding: 8px;
  background: var(--paper-2);
}

.props-array-row {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.props-array-row-body {
  flex: 1;
  min-width: 0;
}

.props-array-row-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.props-array-add {
  align-self: flex-start;
}

.props-nested {
  border-left: 2px solid var(--rule);
  padding-left: 10px;
}
</style>
