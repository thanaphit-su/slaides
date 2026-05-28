<script setup lang="ts">
import Icon from "@/components/Icon.vue";
import type { DeckListItem } from "@/api/types";

const props = withDefaults(defineProps<{ decks: DeckListItem[]; liveDeckIds?: Set<string> }>(), {
  liveDeckIds: () => new Set<string>(),
});
const emit = defineEmits<{ (e: "open", id: string): void; (e: "delete", id: string): void }>();

function onDeleteClick(e: MouseEvent, id: string) {
  e.stopPropagation();
  emit("delete", id);
}
</script>

<template>
  <div
    :style="{
      border: '1px solid var(--rule)',
      borderRadius: 'var(--r-lg)',
      overflow: 'hidden',
      background: 'var(--paper)',
    }"
  >
    <div
      :style="{
        display: 'grid',
        gridTemplateColumns: '2.2fr 1fr 100px 40px 40px',
        gap: '14px',
        padding: '12px 18px',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        fontFamily: 'var(--sans)',
        fontSize: '11px',
        fontWeight: 600,
        color: 'var(--ink-soft)',
        textTransform: 'uppercase',
        letterSpacing: '.1em',
      }"
    >
      <span>Title</span>
      <span>Last edited</span>
      <span :style="{ textAlign: 'right' }">Slides</span>
      <span></span>
      <span></span>
    </div>
    <div
      v-for="(d, i) in props.decks"
      :key="d.id"
      data-testid="deck-list-row"
      @click="$emit('open', d.id)"
      :style="{
        display: 'grid',
        gridTemplateColumns: '2.2fr 1fr 100px 40px 40px',
        gap: '14px',
        padding: '14px 18px',
        borderBottom: i === props.decks.length - 1 ? 'none' : '1px solid var(--rule-soft)',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background .12s',
      }"
      onmouseover="this.style.background='var(--paper-2)'"
      onmouseout="this.style.background='transparent'"
    >
      <div>
        <div :style="{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }">
          <span :style="{ fontFamily: 'var(--serif)', fontSize: '18px', letterSpacing: '-0.01em', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }">
          {{ d.title }}
          </span>
          <span
            v-if="props.liveDeckIds.has(d.id)"
            class="badge-live"
            data-testid="deck-list-live-badge"
            :style="{
              flexShrink: 0,
              padding: '3px 6px',
              borderRadius: 'var(--r-xs)',
              fontFamily: 'var(--mono)',
              fontSize: '10px',
              fontWeight: 700,
              letterSpacing: '.08em',
            }"
          >
            LIVE
          </span>
        </div>
        <div :style="{ fontSize: '12px', color: 'var(--ink-soft)', marginTop: '2px' }">{{ d.subtitle || "—" }}</div>
      </div>
      <span class="t-meta">{{ new Date(d.updated_at).toLocaleString() }}</span>
      <span :style="{ textAlign: 'right', fontSize: '13px', color: 'var(--ink)' }">{{ d.slide_count }}</span>
      <span :style="{ textAlign: 'right' }">
        <button
          @click="onDeleteClick($event, d.id)"
          title="Delete deck"
          :style="{
            background: 'transparent',
            border: 'none',
            color: 'var(--ink-soft)',
            cursor: 'pointer',
            padding: '4px',
            borderRadius: 'var(--r-xs)',
            lineHeight: 0,
          }"
        >
          <Icon name="trash" :size="14" />
        </button>
      </span>
      <span :style="{ textAlign: 'right' }">
        <Icon name="arrow_right" :size="16" />
      </span>
    </div>
  </div>
</template>
