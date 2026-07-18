<script setup lang="ts">
import type { ContextMenuSeparatorProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { ContextMenuSeparator, useForwardProps } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<ContextMenuSeparatorProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <ContextMenuSeparator
    v-bind="forwardedProps"
    :class="cn('-mx-1 my-1 h-px bg-border', props.class)"
  />
</template>
