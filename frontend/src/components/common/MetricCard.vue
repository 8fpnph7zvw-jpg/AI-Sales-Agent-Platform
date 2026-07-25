<script setup lang="ts">
import type { Component } from "vue";

defineProps<{
  label: string;
  value: string | number;
  hint?: string;
  icon: Component;
  tone?: "blue" | "violet" | "green" | "amber";
}>();
</script>

<template>
  <article class="metric-card" :class="`metric-card--${tone || 'blue'}`">
    <div class="metric-card__icon"><el-icon><component :is="icon" /></el-icon></div>
    <div>
      <p class="metric-card__label">{{ label }}</p>
      <strong>{{ value }}</strong>
      <span v-if="hint">{{ hint }}</span>
    </div>
  </article>
</template>
