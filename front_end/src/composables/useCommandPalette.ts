import { ref } from 'vue'

/** Global open state for the ⌘K command palette (mounted once in the shell). */
export const paletteOpen = ref(false)

export function openCommandPalette(): void {
  paletteOpen.value = true
}
