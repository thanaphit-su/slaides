<script setup lang="ts">
import { computed } from "vue";
import type { Component } from "vue";
import {
  Astroid,
  ArrowLeft,
  ArrowRight,
  Bolt,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleHelp,
  Copy,
  Download,
  Edit3,
  Eye,
  FileText,
  Grid2X2,
  LayoutGrid,
  LayoutDashboard,
  List,
  Lock,
  LogOut,
  Minus,
  Moon,
  PanelTop,
  Plus,
  Search,
  Settings,
  SquarePen,
  Sun,
  SwatchBook,
  Trash,
  Upload,
  User,
  Users,
  X,
} from "@lucide/vue";

const props = withDefaults(
  defineProps<{ name: string; size?: number; stroke?: string; strokeWidth?: number }>(),
  { size: 18, stroke: "currentColor", strokeWidth: 1.4 },
);

const ICONS: Record<string, Component> = {
  astroid: Astroid,
  bolt: Bolt,
  plus: Plus,
  minus: Minus,
  x: X,
  chev_right: ChevronRight,
  chevron_right: ChevronRight,
  chev_left: ChevronLeft,
  chevron_left: ChevronLeft,
  chev_down: ChevronDown,
  chevron_down: ChevronDown,
  chev_up: ChevronUp,
  chevron_up: ChevronUp,
  sun: Sun,
  moon: Moon,
  user: User,
  users: Users,
  settings: Settings,
  gear: Settings,
  search: Search,
  deck: PanelTop,
  widget: LayoutGrid,
  grid: Grid2X2,
  list: List,
  arrow_right: ArrowRight,
  arrow_left: ArrowLeft,
  logout: LogOut,
  upload: Upload,
  download: Download,
  lock: Lock,
  copy: Copy,
  eye: Eye,
  check: Check,
  dot: Circle,
  trash: Trash,
  theme: SwatchBook,
  edit: Edit3,
  md: FileText,
  dashboard: LayoutDashboard,
  pen: SquarePen,
};

const icon = computed<Component>(() => ICONS[props.name] || CircleHelp);
const iconFill = computed(() => (props.name === "dot" ? props.stroke : "none"));
const iconStrokeWidth = computed(() => (props.name === "dot" ? 0 : props.strokeWidth));
</script>

<template>
  <component
    :is="icon"
    :size="props.size"
    :color="props.stroke"
    :stroke-width="iconStrokeWidth"
    :fill="iconFill"
  />
</template>
