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
    class="scale-in"
    @click="$emit('open')"
    @mouseenter="hover = true"
    @mouseleave="hover = false"
    :style="{
      background: 'var(--paper)',
      border: '1px solid ' + (hover ? 'var(--ink)' : 'var(--rule)'),
      boxShadow: hover ? 'var(--shadow-2)' : 'none',
      borderRadius: 'var(--r-lg)',
      overflow: 'hidden',
      cursor: 'pointer',
      transition: 'border-color .15s ease, box-shadow .15s ease',
      display: 'flex',
      flexDirection: 'column',
    }"
  >
    <div
      :style="{
        position: 'relative',
        aspectRatio: '320 / 200',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-2)',
      }"
    >
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
        :style="{
          position: 'absolute',
          right: '8px',
          bottom: '8px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          padding: '4px 7px',
          borderRadius: 'var(--r-sm)',
          fontFamily: 'var(--mono)',
          fontSize: '10px',
          fontWeight: 700,
          letterSpacing: '.08em',
          boxShadow: 'var(--shadow-1)',
        }"
      >
        <span
          aria-hidden="true"
          :style="{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: '#fff',
            display: 'inline-block',
            flexShrink: 0,
          }"
        />
        LIVE
      </span>
      <button
        v-show="hover"
        title="Delete deck"
        @click="onDeleteClick"
        :style="{
          position: 'absolute',
          top: '8px',
          right: '8px',
          width: '28px',
          height: '28px',
          padding: 0,
          border: '1px solid var(--rule)',
          background: 'var(--paper)',
          borderRadius: 'var(--r-sm)',
          color: 'var(--ink-soft)',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 'var(--shadow-1)',
        }"
      >
        <Icon name="trash" :size="13" />
      </button>
    </div>
    <div :style="{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }">
      <div :style="{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }">
        <h3
          :style="{
            fontFamily: 'var(--serif)',
            fontSize: '20px',
            fontWeight: 500,
            letterSpacing: '-0.015em',
            margin: 0,
            lineHeight: 1.2,
          }"
        >
          {{ props.deck.title }}
        </h3>
        <span class="t-meta" :style="{ flexShrink: 0, marginLeft: '8px' }">
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
      <div :style="{ marginTop: 'auto', paddingTop: '12px', display: 'flex', alignItems: 'center', gap: '14px' }">
        <span :style="{ display: 'inline-flex', alignItems: 'center', gap: '5px', color: 'var(--ink-soft)', fontSize: '12px' }">
          <Icon name="deck" :size="13" /> {{ props.deck.slide_count }} slides
        </span>
      </div>
    </div>
  </article>
</template>
