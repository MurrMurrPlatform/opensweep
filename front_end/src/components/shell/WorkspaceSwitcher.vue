<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Check, ChevronsUpDown, FolderGit2, GitBranch } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useRepositoryStore } from '@/stores/repositoryStore'
import { useWorkspaceSwitch } from '@/composables/useWorkspaceSwitch'

const router = useRouter()
const repos = useRepositoryStore()
const { currentSlug, selectWorkspace } = useWorkspaceSwitch()

onMounted(() => { if (!repos.loaded) repos.fetchAll() })

const currentRepo = computed(() => (currentSlug.value ? repos.findBySlug(currentSlug.value) : undefined))
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="outline" size="sm" class="max-w-[16rem] justify-start gap-2 font-medium">
        <GitBranch class="size-4 shrink-0 text-muted-foreground" />
        <span v-if="!currentSlug" class="truncate text-muted-foreground">Select workspace…</span>
        <span v-else class="truncate">{{ currentRepo?.name || currentSlug }}</span>
        <ChevronsUpDown class="size-3.5 shrink-0 text-muted-foreground" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-64">
      <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
      <DropdownMenuItem
        v-for="repo in repos.list"
        :key="repo.slug"
        class="gap-2"
        @select="selectWorkspace(repo.slug)"
      >
        <FolderGit2 class="size-4 text-muted-foreground" />
        <span class="min-w-0 flex-1 truncate">{{ repo.name }}</span>
        <Check v-if="repo.slug === currentSlug" class="size-4" />
      </DropdownMenuItem>
      <DropdownMenuItem v-if="!repos.list.length" disabled>
        No repositories connected yet
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @select="router.push({ name: 'repositories' })">
        Manage workspaces…
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
