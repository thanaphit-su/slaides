<script setup lang="ts">
import { computed, ref } from "vue";
import Icon from "@/components/Icon.vue";
import DeckCover from "@/components/DeckCover.vue";
import type { DeckListItem } from "@/api/types";

const props = withDefaults(defineProps<{ deck: DeckListItem; live?: boolean }>(), {
  live: false,
});
const emit = defineEmits<{ (e: "open"): void; (e: "delete"): void }>();

const hover = ref(false);
const firstSlideSubheader = computed(() => truncate(firstH2(props.deck.preview_markdown || "")));

function firstH2(markdown: string): string {
  const line = markdown.split(/\r?\n/).find((value) => /^##(?!#)\s+/.test(value.trim()));
  if (!line) return "";
  return line.trim().replace(/^##(?!#)\s+/, "").trim();
}

function truncate(value: string): string {
  const max = 39;
  if (value.length <= max) return value;
  return `${value.slice(0, max).trimEnd()}...`;
}

function onDeleteClick(e: MouseEvent) {
  e.stopPropagation();
  emit("delete");
}
</script>

<template>
  <article
    class="deck-card scale-in"
    @click="$emit('open')"
    @mouseenter="hover = true"
    @mouseleave="hover = false"
    :class="{ hover }"
  >
    <div class="deck-card-cover">
      <DeckCover
        :variant="props.deck.cover"
        :title="props.deck.title"
        :subtitle="props.deck.subtitle"
        :kicker="props.deck.preview_kicker"
        :markdown="props.deck.preview_markdown"
      />
      <span
        v-if="props.live"
        class="badge-live"
        data-testid="deck-card-live-badge"
      >
        <span aria-hidden="true" />
        LIVE
      </span>
      <button
        v-show="hover"
        title="Delete deck"
        class="deck-card-delete"
        @click="onDeleteClick"
      >
        <Icon name="trash" :size="13" />
      </button>
    </div>
    <div class="deck-card-body">
      <div class="deck-card-title-row">
        <h3>
          {{ props.deck.title }}
        </h3>
        <span class="t-meta deck-card-date">
          {{ new Date(props.deck.updated_at).toLocaleDateString() }}
        </span>
      </div>
      <p
        data-testid="deck-card-first-slide-subheader"
        :title="firstSlideSubheader"
        :style="{
          fontFamily: 'var(--serif)',
          fontSize: '14px',
          color: 'var(--ink-soft)',
          fontWeight: 400,
          margin: 0,
          lineHeight: 1.5,
          minHeight: '21px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }"
      >
        {{ firstSlideSubheader }}
      </p>
      <div class="deck-card-meta-row">
        <span class="deck-card-count">
          <Icon name="deck" :size="13" /> {{ props.deck.slide_count }} slides
        </span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.deck-card {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--r-lg);
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  display: flex;
  flex-direction: column;
}

:global(.dark) .deck-card {
  background: var(--paper-2);
  border-color: var(--rule-strong);
}

.deck-card.hover {
  border-color: var(--ink);
  box-shadow: var(--shadow-2);
}

:global(.dark) .deck-card.hover {
  border-color: var(--accent);
}

.deck-card-cover {
  position: relative;
  aspect-ratio: 320 / 200;
  border-bottom: 1px solid var(--rule);
  background: var(--paper-2);
}

:global(.dark) .deck-card-cover {
  border-bottom-color: var(--rule-strong);
  background: var(--paper-3);
}

.badge-live {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 7px;
  border-radius: var(--r-sm);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  box-shadow: var(--shadow-1);
}

.badge-live span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--paper);
  display: inline-block;
  flex-shrink: 0;
}

.deck-card-delete {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--rule);
  background: var(--paper);
  border-radius: var(--r-sm);
  color: var(--ink-soft);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-1);
}

.deck-card-delete:hover {
  color: var(--err);
  border-color: var(--err);
}

.deck-card-body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.deck-card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.deck-card-title-row h3 {
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: 0;
  margin: 0;
  line-height: 1.2;
  color: var(--ink);
}

.deck-card-date {
  flex-shrink: 0;
  margin-left: 8px;
}

.deck-card-meta-row {
  margin-top: auto;
  padding-top: 12px;
  display: flex;
  align-items: center;
  gap: 14px;
}

.deck-card-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--ink-soft);
  font-size: 12px;
}
</style>
