<script setup lang="ts">
import { computed } from "vue";
import Icon from "@/components/Icon.vue";
import type { RandomAudienceResults, RandomAudienceSpec, SessionSlide } from "@/api/types";

const props = defineProps<{
  slide: SessionSlide;
  role: "presenter" | "audience";
  inverted?: boolean;
}>();

const spec = computed(() => props.slide.spec as unknown as RandomAudienceSpec);
const results = computed(() => {
  const raw = props.slide.results as unknown as Partial<RandomAudienceResults>;
  return {
    requested_count: Number(raw.requested_count ?? spec.value.count ?? 1),
    eligible_count: Number(raw.eligible_count ?? 0),
    picked: Array.isArray(raw.picked) ? raw.picked : [],
  };
});

function labelFor(pick: { display_name: string | null; anon: boolean }, index: number): string {
  if (pick.display_name && !pick.anon) return pick.display_name;
  return `Audience ${index + 1}`;
}

function refSuffix(ref: string): string {
  return ref ? ref.slice(0, 8) : "unknown";
}
</script>

<template>
  <div class="random-slide" :class="{ inverted }">
    <div class="random-inner">
      <div class="kicker">Random audience</div>
      <h2 class="title">Picked audience members</h2>
      <p class="summary">
        Requested {{ results.requested_count }} from {{ results.eligible_count }} active audience
        {{ results.eligible_count === 1 ? "member" : "members" }}.
      </p>

      <section v-if="role === 'presenter'" class="picked-list" aria-label="Picked audience members">
        <article v-for="(pick, index) in results.picked" :key="pick.participant_ref" class="picked-card">
          <span class="picked-number">{{ String(index + 1).padStart(2, "0") }}</span>
          <div>
            <strong>{{ labelFor(pick, index) }}</strong>
            <small>{{ pick.anon ? "anonymous" : "audience" }} · {{ refSuffix(pick.participant_ref) }}</small>
          </div>
        </article>
        <div v-if="!results.picked.length" class="empty-state">
          <Icon name="users" :size="18" />
          <span>No active audience members were available to pick.</span>
        </div>
      </section>

      <section v-else class="audience-waiting">
        <Icon name="users" :size="18" />
        <span>The presenter is running a room activity.</span>
      </section>
    </div>
  </div>
</template>

<style scoped>
.random-slide {
  min-height: 100%;
  padding: clamp(56px, 9vh, 112px) clamp(24px, 8vw, 96px);
  background: var(--paper);
  color: var(--ink);
}
.random-slide.inverted {
  background: var(--ink);
  color: var(--paper);
}
.random-inner {
  max-width: 760px;
  margin: 0 auto;
}
.kicker {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 18px;
}
.random-slide.inverted .kicker {
  color: #9db5ff;
}
.title {
  margin: 0;
  font-family: var(--serif);
  font-size: clamp(36px, 6vw, 62px);
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0;
}
.summary {
  margin: 18px 0 30px;
  color: var(--ink-soft);
  font-family: var(--serif);
  font-size: 18px;
}
.random-slide.inverted .summary {
  color: rgba(253, 252, 249, 0.7);
}
.picked-list {
  display: grid;
  gap: 10px;
}
.picked-card,
.empty-state,
.audience-waiting {
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  padding: 16px 18px;
}
.random-slide.inverted .picked-card,
.random-slide.inverted .empty-state,
.random-slide.inverted .audience-waiting {
  border-color: rgba(253, 252, 249, 0.22);
  background: rgba(253, 252, 249, 0.06);
}
.picked-number {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--accent);
}
.picked-card strong {
  display: block;
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 600;
}
.picked-card small,
.empty-state,
.audience-waiting {
  color: var(--ink-soft);
  font-size: 13px;
}
.random-slide.inverted .picked-card small,
.random-slide.inverted .empty-state,
.random-slide.inverted .audience-waiting {
  color: rgba(253, 252, 249, 0.68);
}
</style>
