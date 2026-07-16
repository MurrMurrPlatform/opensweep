<script setup lang="ts">
import { Palette } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTheme, type ColorScheme } from '@/composables/useTheme'

const { scheme, setScheme } = useTheme()

const schemes: { value: ColorScheme; hsl: string }[] = [
  { value: 'indigo', hsl: '239 84% 67%' },
  { value: 'rose',   hsl: '330 81% 60%' },
  { value: 'violet', hsl: '263 70% 66%' },
  { value: 'teal',   hsl: '173 80% 40%' },
  { value: 'sage',   hsl: '160 84% 31%' },
  { value: 'amber',  hsl: '28 92% 44%' },
  { value: 'coral',  hsl: '8 78% 60%' },
  { value: 'slate',  hsl: '220 23% 50%' },
]
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon-sm" title="Accent color">
        <Palette class="size-4" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-40">
      <DropdownMenuLabel>Accent color</DropdownMenuLabel>
      <DropdownMenuRadioGroup
        :model-value="scheme"
        @update:model-value="setScheme($event as ColorScheme)"
      >
        <DropdownMenuRadioItem v-for="s in schemes" :key="s.value" :value="s.value" class="gap-2 capitalize">
          <span class="size-3.5 rounded-pill" :style="{ background: `hsl(${s.hsl})` }" />
          {{ s.value }}
        </DropdownMenuRadioItem>
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
