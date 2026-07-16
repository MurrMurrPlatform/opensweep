<script setup lang="ts">
// Global ⌘K command palette: navigate anywhere, switch workspace, flip
// theme/sounds — all from the keyboard. Mounted once in ShellLayout.
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { FolderGit2, Moon, Sun, Volume2, VolumeX, Check } from 'lucide-vue-next'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command'
import { paletteOpen } from '@/composables/useCommandPalette'
import { useNavSections } from '@/composables/useNavSections'
import { useWorkspaceSwitch } from '@/composables/useWorkspaceSwitch'
import { useTheme } from '@/composables/useTheme'
import { soundsEnabled, toggleSounds } from '@/lib/notifySound'
import { useRepositoryStore } from '@/stores/repositoryStore'
import { useUiStore } from '@/stores/uiStore'

const router = useRouter()
const ui = useUiStore()
const repos = useRepositoryStore()
const { sections } = useNavSections()
const { currentSlug, selectWorkspace } = useWorkspaceSwitch()
const { theme, toggle: toggleTheme } = useTheme()

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    paletteOpen.value = !paletteOpen.value
    if (paletteOpen.value && !repos.loaded) repos.fetchAll()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

/** Run an action and dismiss the palette. */
function run(action: () => void) {
  paletteOpen.value = false
  action()
}
</script>

<template>
  <CommandDialog v-model:open="paletteOpen">
    <CommandInput placeholder="Type a command or search…" />
    <CommandList>
      <CommandEmpty>No results found.</CommandEmpty>

      <template v-for="section in sections" :key="section.label ?? 'root'">
        <CommandGroup :heading="section.label ?? undefined">
          <CommandItem
            v-for="item in section.items"
            :key="item.to"
            :value="`${section.label} ${item.label}`"
            :disabled="Boolean(item.scoped) && !ui.currentRepoSlug"
            @select="run(() => router.push(item.to))"
          >
            <component :is="item.icon" class="text-muted-foreground" />
            <span>{{ item.label }}</span>
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
      </template>

      <CommandGroup v-if="repos.list.length" heading="Switch workspace">
        <CommandItem
          v-for="repo in repos.list"
          :key="repo.slug"
          :value="`workspace ${repo.name}`"
          @select="run(() => selectWorkspace(repo.slug))"
        >
          <FolderGit2 class="text-muted-foreground" />
          <span class="min-w-0 flex-1 truncate">{{ repo.name }}</span>
          <Check v-if="repo.slug === currentSlug" class="text-primary" />
        </CommandItem>
      </CommandGroup>
      <CommandSeparator v-if="repos.list.length" />

      <CommandGroup heading="Preferences">
        <CommandItem value="toggle theme dark light mode" @select="run(toggleTheme)">
          <Sun v-if="theme === 'dark'" class="text-muted-foreground" />
          <Moon v-else class="text-muted-foreground" />
          <span>{{ theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode' }}</span>
        </CommandItem>
        <CommandItem value="toggle notification sounds mute" @select="run(toggleSounds)">
          <Volume2 v-if="!soundsEnabled" class="text-muted-foreground" />
          <VolumeX v-else class="text-muted-foreground" />
          <span>{{ soundsEnabled ? 'Mute notification sounds' : 'Unmute notification sounds' }}</span>
          <CommandShortcut>{{ soundsEnabled ? 'On' : 'Off' }}</CommandShortcut>
        </CommandItem>
      </CommandGroup>
    </CommandList>
  </CommandDialog>
</template>
