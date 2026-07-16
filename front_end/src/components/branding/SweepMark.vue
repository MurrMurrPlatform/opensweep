<script setup lang="ts">
// Inlined (not <img>) so the mark inherits currentColor and re-tints
// with the active theme.
import markMarkup from '@/assets/sweep_logo.svg?raw'
</script>

<template>
  <span class="sweep-mark" v-html="markMarkup" />
</template>

<style scoped>
.sweep-mark {
  display: inline-flex;
}
.sweep-mark :deep(svg) {
  display: block;
  height: 100%;
  width: auto;
  aspect-ratio: 1;
}
</style>
