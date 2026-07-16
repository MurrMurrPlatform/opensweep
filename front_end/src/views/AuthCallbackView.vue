<script setup lang="ts">
// OIDC redirect target (services/auth.ts). Exchanges the code, then restores
// the path the user originally navigated to.
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2 } from 'lucide-vue-next'
import { completeSignIn } from '@/services/auth'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const router = useRouter()
const error = ref('')

onMounted(async () => {
  try {
    const returnTo = await completeSignIn()
    router.replace(returnTo)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <Card class="w-full max-w-md">
    <CardContent class="p-8 text-center">
      <template v-if="error">
        <p class="text-base font-semibold tracking-tight">Sign-in failed</p>
        <p class="mt-2 break-words text-sm text-muted-foreground">{{ error }}</p>
        <Button as="a" href="/" variant="outline" size="sm" class="mt-6">Try again</Button>
      </template>
      <div v-else class="flex flex-col items-center gap-3">
        <Loader2 class="size-6 animate-spin text-muted-foreground" />
        <p class="text-sm text-muted-foreground">Signing you in…</p>
      </div>
    </CardContent>
  </Card>
</template>
