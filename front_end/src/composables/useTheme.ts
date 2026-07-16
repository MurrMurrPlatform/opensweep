import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'
export type ColorScheme = 'indigo' | 'rose' | 'violet' | 'teal' | 'sage' | 'amber' | 'coral' | 'slate'

const STORAGE_KEY = 'opensweep:theme'

const theme = ref<ThemeMode>((localStorage.getItem(`${STORAGE_KEY}:mode`) as ThemeMode) || preferred())
const scheme = ref<ColorScheme>((localStorage.getItem(`${STORAGE_KEY}:scheme`) as ColorScheme) || 'indigo')

function preferred(): ThemeMode {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply() {
  document.documentElement.setAttribute('data-theme', theme.value)
  document.documentElement.setAttribute('data-scheme', scheme.value)
}

watch(theme, (val) => { localStorage.setItem(`${STORAGE_KEY}:mode`, val); apply() }, { immediate: true })
watch(scheme, (val) => { localStorage.setItem(`${STORAGE_KEY}:scheme`, val); apply() }, { immediate: true })

export function useTheme() {
  return {
    theme,
    scheme,
    toggle: () => { theme.value = theme.value === 'light' ? 'dark' : 'light' },
    setTheme: (t: ThemeMode) => { theme.value = t },
    setScheme: (s: ColorScheme) => { scheme.value = s },
  }
}
