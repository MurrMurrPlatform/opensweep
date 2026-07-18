<script setup lang="ts">
// Copies a ready-made checkout command so trying an agent branch is one paste.
// Prefers `gh pr checkout`; falls back to a fetch + worktree combo that never
// disturbs the developer's current checkout.
import { computed } from 'vue'
import { Copy } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  branch?: string
  prNumber?: number | null
}>()

const toast = useToast()

const command = computed(() => {
  if (props.prNumber) return `gh pr checkout ${props.prNumber}`
  if (props.branch) {
    const slug = props.branch.replace(/\//g, '-')
    return `git fetch origin ${props.branch} && git worktree add ../$(basename $(git rev-parse --show-toplevel))--${slug} ${props.branch}`
  }
  return ''
})

async function copy() {
  if (!command.value) return
  await navigator.clipboard.writeText(command.value)
  toast.success('Checkout command copied', 'Paste it in your terminal to test this branch.')
}
</script>

<template>
  <Button v-if="command" variant="outline" size="sm" @click="copy">
    <Copy /> Test locally
  </Button>
</template>
