<script setup lang="ts">
import { Toaster } from '@/components/ui/sonner'
</script>

<template>
  <div class="grid min-h-screen place-items-center bg-background p-4 text-foreground">
    <router-view />
    <Toaster :rich-colors="true" close-button />
  </div>
</template>
