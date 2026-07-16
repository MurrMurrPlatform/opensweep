<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Bot, MessageSquare, Send, Trash2 } from 'lucide-vue-next'
import { useCommentStore } from '@/stores/commentStore'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { formatRelativeTime } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import CommentBody from '@/components/comments/CommentBody.vue'
import OpenSweepThinkingBubble from '@/components/comments/OpenSweepThinkingBubble.vue'
import MentionComposer from '@/components/comments/MentionComposer.vue'
import type { CommentDTO, CommentSubjectType } from '@/types/api'

/**
 * Reusable discussion thread for any data item. List is ascending by
 * created_at (server order); the composer supports @opensweep summons and
 * data-item mentions; own comments can be deleted (with confirm).
 */
interface Props {
  subjectType: CommentSubjectType
  subjectUid: string
  title?: string
  repositoryUid?: string
}
const props = withDefaults(defineProps<Props>(), { title: 'Discussion' })

const comments = useCommentStore()
const currentUser = useCurrentUserStore()
const toast = useToast()

const items = ref<CommentDTO[]>([])
const loading = ref(true)
const draft = ref('')
const submitting = ref(false)
const deletingUid = ref<string | null>(null)
const deleteOpen = ref(false)
const pendingDelete = ref<CommentDTO | null>(null)

const canSubmit = computed(() => draft.value.trim().length > 0 && !submitting.value)

async function load() {
  loading.value = true
  try {
    items.value = await comments.fetchFor(props.subjectType, props.subjectUid)
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Couldn’t load comments', msg)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  void restorePending()
})
watch(() => props.subjectUid, () => {
  void load()
  void restorePending()
})

// ── @opensweep thinking bubbles ──────────────────────────────────────────────────
// One bubble per in-flight reply run. Restored from the pending endpoint on
// mount (survives reloads); watched live over the run WS; the poll interval
// is only the fallback when the socket can't connect.

const pendingRunUids = ref<string[]>([])
let pendingPoll: ReturnType<typeof setInterval> | null = null

async function restorePending() {
  try {
    const pending = await comments.fetchPendingOpenSweepRuns(props.subjectType, props.subjectUid)
    pendingRunUids.value = pending.map((p) => p.run_uid)
  } catch {
    // The bubble is a nicety — the thread must load even if this fails.
  }
}

function dropPending(runUid: string) {
  pendingRunUids.value = pendingRunUids.value.filter((uid) => uid !== runUid)
  if (!pendingRunUids.value.length) stopPendingPoll()
}

async function onOpenSweepReplied(runUid: string) {
  await load()
  dropPending(runUid)
}

function stopPendingPoll() {
  if (pendingPoll !== null) {
    clearInterval(pendingPoll)
    pendingPoll = null
  }
}

/** WS fallback: refresh the thread + pending set every 5s until nothing is
 *  in flight anymore. */
function startPendingPoll() {
  if (pendingPoll !== null) return
  pendingPoll = setInterval(async () => {
    await load()
    await restorePending()
    if (!pendingRunUids.value.length) stopPendingPoll()
  }, 5000)
}

onBeforeUnmount(stopPendingPoll)

async function submit() {
  const body = draft.value.trim()
  if (!body || submitting.value) return
  submitting.value = true
  try {
    const created = await comments.create({
      subject_type: props.subjectType,
      subject_uid: props.subjectUid,
      body,
    })
    items.value = [...items.value, created]
    draft.value = ''
    if (created.triggered_run_uid) {
      // The thinking bubble below the thread is the summon feedback.
      pendingRunUids.value = [...pendingRunUids.value, created.triggered_run_uid]
    } else if (/@opensweep\b/i.test(body)) {
      toast.error(
        'OpenSweep not dispatched',
        'The comment was saved, but no run could be started — check LLM providers.',
      )
    }
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Comment failed', msg)
  } finally {
    submitting.value = false
  }
}

function isOwn(comment: CommentDTO): boolean {
  return comment.author_uid === currentUser.uid
}

function authorName(comment: CommentDTO): string {
  return comment.author_name || comment.author_uid
}

function initials(comment: CommentDTO): string {
  const name = authorName(comment).trim()
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function removeComment(comment: CommentDTO) {
  if (deletingUid.value) return
  pendingDelete.value = comment
  deleteOpen.value = true
}

async function confirmRemoveComment() {
  const comment = pendingDelete.value
  if (!comment) return
  deleteOpen.value = false
  deletingUid.value = comment.uid
  try {
    await comments.remove(comment.uid)
    items.value = items.value.filter((c) => c.uid !== comment.uid)
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Delete failed', msg)
  } finally {
    deletingUid.value = null
  }
}
</script>

<template>
  <Card>
    <CardHeader class="p-6 pb-0">
      <CardTitle class="flex items-center gap-2 text-base">
        <MessageSquare class="size-4 text-muted-foreground" />
        {{ title }}
        <span class="text-xs font-normal text-muted-foreground">· {{ items.length }}</span>
      </CardTitle>
    </CardHeader>
    <CardContent class="p-6 pt-4">
      <div v-if="loading && !items.length" class="text-sm text-muted-foreground">Loading comments…</div>
      <div v-else-if="!items.length" class="text-sm text-muted-foreground">
        No comments yet — start the discussion below. Mention
        <span class="font-medium text-foreground">@opensweep</span> to summon the agent.
      </div>
      <ul v-else class="space-y-3">
        <li
          v-for="c in items"
          :key="c.uid"
          class="-mx-2 flex gap-3 rounded-lg p-2"
          :class="c.author_kind === 'opensweep' ? 'bg-primary/5' : ''"
        >
          <Avatar class="mt-0.5 size-8 shrink-0">
            <AvatarFallback
              class="text-xs"
              :class="c.author_kind === 'opensweep' ? 'bg-primary/15 text-primary' : ''"
            >
              <Bot v-if="c.author_kind === 'opensweep'" class="size-4" />
              <template v-else>{{ initials(c) }}</template>
            </AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 text-xs">
              <span class="font-medium" :class="c.author_kind === 'opensweep' ? 'text-primary' : 'text-foreground'">
                {{ c.author_kind === 'opensweep' ? 'OpenSweep' : authorName(c) }}
              </span>
              <RouterLink
                v-if="c.author_kind === 'opensweep' && c.source_run_uid && currentUser.isPlatformAdmin"
                :to="{ name: 'run-detail', params: { uid: c.source_run_uid } }"
                class="text-muted-foreground hover:underline"
              >view run</RouterLink>
              <span class="text-muted-foreground" :title="c.created_at">{{ formatRelativeTime(c.created_at) }}</span>
              <button
                v-if="isOwn(c)"
                type="button"
                class="ml-auto inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
                :disabled="deletingUid === c.uid"
                title="Delete comment"
                @click="removeComment(c)"
              >
                <Trash2 class="size-3.5" />
              </button>
            </div>
            <div class="mt-1 text-sm leading-relaxed">
              <CommentBody :body="c.body" />
            </div>
          </div>
        </li>
      </ul>

      <!-- In-flight @opensweep replies -->
      <ul v-if="pendingRunUids.length" class="mt-3 space-y-3">
        <OpenSweepThinkingBubble
          v-for="uid in pendingRunUids"
          :key="uid"
          :run-uid="uid"
          @replied="onOpenSweepReplied(uid)"
          @settled="load()"
          @unavailable="startPendingPoll()"
          @dismiss="dropPending(uid)"
        />
      </ul>

      <!-- Composer -->
      <div class="mt-4 space-y-2 border-t pt-4">
        <MentionComposer
          v-model="draft"
          :rows="3"
          placeholder="Write a comment… type @ to mention OpenSweep or another item (Cmd/Ctrl+Enter to submit)"
          :disabled="submitting"
          :repository-uid="repositoryUid"
          @submit="submit"
        />
        <div class="flex justify-end">
          <Button size="sm" :loading="submitting" :disabled="!canSubmit" @click="submit">
            <Send /> Comment
          </Button>
        </div>
      </div>
    </CardContent>

    <AlertDialog v-model:open="deleteOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete comment</AlertDialogTitle>
          <AlertDialogDescription>Delete this comment?</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="confirmRemoveComment"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </Card>
</template>
