<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import Icon from "@/components/Icon.vue";
import { useThemeMode, type ThemeMode } from "@/theme/useThemeMode";

const props = defineProps<{
  userName?: string | null;
  userEmail?: string | null;
}>();

const emit = defineEmits<{
  (e: "sign-out"): void;
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const theme = useThemeMode();

const displayName = computed(() => props.userName?.trim() || "Guest");
const displayEmail = computed(() => props.userEmail?.trim() || "Live session");
const avatarLetter = computed(() => displayName.value.slice(0, 1).toUpperCase() || "T");
const themeOptions: { value: ThemeMode; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function onDocumentClick(event: MouseEvent): void {
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (root.value?.contains(target)) return;
  open.value = false;
}

function signOut(): void {
  open.value = false;
  emit("sign-out");
}

onMounted(() => {
  document.addEventListener("click", onDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
});
</script>

<template>
  <div ref="root" class="account-menu-wrap">
    <button
      type="button"
      class="account-avatar"
      data-testid="account-avatar-button"
      :aria-expanded="open"
      aria-haspopup="menu"
      :aria-label="`Account menu for ${displayName}`"
      @click.stop="open = !open"
    >
      {{ avatarLetter }}
    </button>

    <div v-if="open" class="account-menu" data-testid="account-menu" role="menu" @click.stop>
      <div class="account-menu-identity">
        <span class="account-avatar account-avatar-large">{{ avatarLetter }}</span>
        <div>
          <strong>{{ displayName }}</strong>
          <small>{{ displayEmail }}</small>
        </div>
      </div>

      <div class="account-menu-theme">
        <span>Theme</span>
        <div class="account-theme-options" role="radiogroup" aria-label="Theme mode">
          <button
            v-for="option in themeOptions"
            :key="option.value"
            type="button"
            class="account-theme-option"
            :class="{ active: theme.mode.value === option.value }"
            :aria-checked="theme.mode.value === option.value"
            :data-testid="`account-theme-${option.value}`"
            role="radio"
            @click="theme.setMode(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <button
        type="button"
        class="account-menu-item danger"
        data-testid="account-menu-signout"
        role="menuitem"
        @click="signOut"
      >
        <Icon name="logout" :size="14" />
        Sign out
      </button>
    </div>
  </div>
</template>

<style scoped>
.account-menu-wrap {
  position: relative;
}

.account-avatar {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: var(--ink);
  color: var(--paper);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-family: var(--serif);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.account-avatar:hover,
.account-avatar:focus-visible {
  background: var(--ink-soft);
  outline: none;
}

.account-avatar-large {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  cursor: default;
}

.account-avatar-large:hover {
  background: var(--ink);
}

.account-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 70;
  width: 246px;
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: var(--shadow-3);
  padding: 6px;
}

.account-menu-identity {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 4px;
}

.account-menu-identity strong,
.account-menu-identity small {
  display: block;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-menu-identity strong {
  color: var(--ink);
  font-family: var(--sans);
  font-size: 13px;
}

.account-menu-identity small {
  margin-top: 2px;
  color: var(--ink-soft);
  font-size: 11px;
}

.account-menu-theme {
  display: grid;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 4px;
}

.account-menu-theme > span {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.account-theme-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  overflow: hidden;
  border: 1px solid var(--rule);
  border-radius: var(--r-sm);
  background: var(--paper-2);
}

.account-theme-option {
  min-width: 0;
  border: 0;
  border-right: 1px solid var(--rule);
  background: transparent;
  color: var(--ink-soft);
  padding: 6px 4px;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.account-theme-option:last-child {
  border-right: 0;
}

.account-theme-option:hover,
.account-theme-option:focus-visible {
  color: var(--ink);
  background: var(--paper);
  outline: none;
}

.account-theme-option.active {
  background: var(--ink);
  color: var(--paper);
}

.account-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink);
  padding: 8px;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.account-menu-item:hover,
.account-menu-item:focus-visible {
  background: var(--paper-2);
  outline: none;
}

.account-menu-item.danger {
  color: var(--err);
}
</style>
