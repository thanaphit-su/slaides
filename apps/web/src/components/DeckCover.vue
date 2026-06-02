<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: string | null;
    title?: string | null;
    subtitle?: string | null;
    kicker?: string | null;
    markdown?: string | null;
  }>(),
  { variant: "fieldnotes" },
);

function stripMarkdown(value: string): string {
  return value
    .replace(/^#{1,6}\s+/, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^\d+\.\s+/, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();
}

function wrapText(value: string, maxChars: number, maxLines: number): string[] {
  const words = stripMarkdown(value).split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
      if (lines.length === maxLines) break;
    } else {
      current = next;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[.,;:!?]+$/, "")}...`;
  }
  return lines;
}

const preview = computed(() => {
  const markdown = props.markdown?.trim() || "";
  if (!markdown) return null;
  const lines = markdown.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const headingIndex = lines.findIndex((line) => /^#\s+/.test(line));
  const title = headingIndex >= 0
    ? stripMarkdown(lines[headingIndex])
    : stripMarkdown(lines.find((line) => !line.startsWith(":::")) || props.title || "Untitled");
  const body = lines
    .slice(headingIndex >= 0 ? headingIndex + 1 : 1)
    .filter((line) => !/^#{1,6}\s+/.test(line))
    .filter((line) => !line.startsWith(":::"))
    .map(stripMarkdown)
    .filter(Boolean)
    .join(" ");
  return {
    kicker: props.kicker || "First slide",
    titleLines: wrapText(title || props.title || "Untitled", 19, 3),
    bodyLines: wrapText(body || props.subtitle || "", 42, 2),
  };
});
</script>

<template>
  <div style="width: 100%; height: 100%">
    <svg
      v-if="preview"
      viewBox="0 0 320 200"
      style="width: 100%; height: 100%; display: block"
    >
      <rect width="320" height="200" fill="#fdfcf9" />
      <text x="22" y="28" font-family="Inter, sans-serif" font-size="8.5" font-weight="700" fill="#1f3a8a" letter-spacing="2">
        {{ preview.kicker.toUpperCase().slice(0, 34) }}
      </text>
      <text
        v-for="(line, index) in preview.titleLines"
        :key="`title-${index}`"
        x="22"
        :y="62 + index * 27"
        font-family="Newsreader, serif"
        font-size="24"
        fill="#0b0d10"
        :font-style="index === preview.titleLines.length - 1 && preview.titleLines.length > 1 ? 'italic' : 'normal'"
      >
        {{ line }}
      </text>
      <line x1="22" :y1="148 - Math.max(0, 2 - preview.titleLines.length) * 14" x2="48" :y2="148 - Math.max(0, 2 - preview.titleLines.length) * 14" stroke="#0b0d10" stroke-width="1.2" />
      <text
        v-for="(line, index) in preview.bodyLines"
        :key="`body-${index}`"
        x="22"
        :y="166 + index * 14"
        font-family="Inter, sans-serif"
        font-size="9.5"
        fill="#4b525b"
      >
        {{ line }}
      </text>
    </svg>
    <svg
      v-else-if="props.variant === 'fieldnotes' || !props.variant"
      viewBox="0 0 320 200"
      style="width: 100%; height: 100%; display: block"
    >
      <rect width="320" height="200" fill="#fdfcf9" />
      <text x="22" y="60" font-family="Newsreader, serif" font-size="22" fill="#0b0d10" font-style="italic">A line is the</text>
      <text x="22" y="86" font-family="Newsreader, serif" font-size="22" fill="#0b0d10">smallest possible</text>
      <text x="22" y="112" font-family="Newsreader, serif" font-size="22" fill="#1f3a8a" font-style="italic">brain you can build.</text>
      <line x1="22" y1="130" x2="48" y2="130" stroke="#0b0d10" stroke-width="1.2" />
      <text x="22" y="148" font-family="Inter, sans-serif" font-size="9" fill="#4b525b">15 MIN · 4 INTERACTIVES</text>
    </svg>
    <svg
      v-else-if="props.variant === 'onboarding'"
      viewBox="0 0 320 200"
      style="width: 100%; height: 100%; display: block"
    >
      <rect width="320" height="200" fill="#f6f6f1" />
      <rect x="22" y="40" width="80" height="6" fill="#1f3a8a" />
      <text x="22" y="86" font-family="Newsreader, serif" font-size="26" fill="#0b0d10">Welcome to</text>
      <text x="22" y="116" font-family="Newsreader, serif" font-size="26" fill="#0b0d10" font-style="italic">cohort fourteen.</text>
      <text x="22" y="150" font-family="Inter, sans-serif" font-size="10" fill="#4b525b">DAY ONE PLAYBOOK</text>
    </svg>
    <svg
      v-else-if="props.variant === 'allhands'"
      viewBox="0 0 320 200"
      style="width: 100%; height: 100%; display: block"
    >
      <rect width="320" height="200" fill="#0b0d10" />
      <text x="22" y="60" font-family="Inter, sans-serif" font-size="10" fill="#8bb0ff" letter-spacing="2">Q3 — ALL HANDS</text>
      <text x="22" y="100" font-family="Newsreader, serif" font-size="28" fill="#fdfcf9">Plain talk</text>
      <text x="22" y="128" font-family="Newsreader, serif" font-size="28" fill="#fdfcf9" font-style="italic">about the quarter.</text>
      <line x1="22" y1="150" x2="60" y2="150" stroke="#8bb0ff" stroke-width="1.2" />
    </svg>
    <svg
      v-else-if="props.variant === 'crit'"
      viewBox="0 0 320 200"
      style="width: 100%; height: 100%; display: block"
    >
      <rect width="320" height="200" fill="#f7f6f2" />
      <rect x="22" y="22" width="160" height="60" fill="#fdfcf9" stroke="#0b0d10" stroke-width="1" />
      <rect x="32" y="32" width="50" height="6" fill="#cfccc4" />
      <rect x="32" y="44" width="80" height="6" fill="#cfccc4" />
      <rect x="32" y="56" width="60" height="6" fill="#cfccc4" />
      <text x="22" y="116" font-family="Newsreader, serif" font-size="22" fill="#0b0d10">A 45-minute</text>
      <text x="22" y="142" font-family="Newsreader, serif" font-size="22" fill="#0b0d10" font-style="italic">generative critique.</text>
    </svg>
    <div
      v-else
      style="
        width: 100%;
        height: 100%;
        background: var(--paper-2);
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: var(--serif);
        color: var(--ink-soft);
      "
    >
      Untitled cover
    </div>
  </div>
</template>
