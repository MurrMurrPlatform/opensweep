<script setup lang="ts">
// A structured question the agent asked via `opensweep_platform_ask_user`.
// Rendered as a compact strip directly above the composer: option chips
// answer in one click; the free-text input handles everything else.
// Answering marks the question answered (metadata) AND delivers the answer
// into the conversation as a follow-up message.
import { ref } from 'vue'
import { CircleHelp, SendHorizontal } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ThreadEventDTO } from '@/types/api'

const props = defineProps<{ question: ThreadEventDTO }>()
const emit = defineEmits<{ (e: 'answer', text: string): void }>()

const freeText = ref('')
const busy = ref(false)

const options = Array.isArray(props.question.options)
  ? (props.question.options as string[])
  : []

function answer(text: string) {
  if (busy.value || !text.trim()) return
  busy.value = true
  emit('answer', text.trim())
}
</script>

<template>
  <div class="space-y-2 border-t bg-primary/5 px-4 py-3">
    <div class="flex items-start gap-2">
      <CircleHelp class="mt-0.5 size-4 shrink-0 text-primary" />
      <div class="min-w-0">
        <p class="text-sm">{{ String(question.question ?? '') }}</p>
        <p v-if="question.context" class="mt-0.5 text-xs text-muted-foreground">
          {{ String(question.context) }}
        </p>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-1.5 pl-6">
      <Button
        v-for="opt in options"
        :key="opt"
        size="sm"
        variant="outline"
        class="h-7 text-xs"
        :disabled="busy"
        @click="answer(opt)"
      >
        {{ opt }}
      </Button>
      <div class="flex min-w-48 flex-1 items-center gap-1.5">
        <Input
          v-model="freeText"
          class="h-7 text-xs"
          :placeholder="options.length ? 'Or answer in your own words…' : 'Type your answer…'"
          @keydown.enter.exact.prevent="answer(freeText)"
        />
        <Button
          size="sm"
          variant="ghost"
          class="h-7 shrink-0 px-2"
          :disabled="busy || !freeText.trim()"
          @click="answer(freeText)"
        >
          <SendHorizontal class="size-3.5" />
        </Button>
      </div>
    </div>
  </div>
</template>
