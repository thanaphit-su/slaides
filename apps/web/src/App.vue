<script setup lang="ts">
import { RouterView } from "vue-router";
import { useThemeMode } from "@/theme/useThemeMode";

useThemeMode();
</script>

<template>
  <RouterView />
</template>
