import type { RouteLocationRaw } from 'vue-router'
import { toast } from 'vue-sonner'
import router from '@/router'
import { playUiError, playUiSuccess } from '@/lib/notifySound'

export type ToastTone = 'default' | 'success' | 'error' | 'warn'

/** Optional in-toast navigation affordance ("View run →" etc.). */
export interface ToastAction {
  label: string
  to: RouteLocationRaw
}

function sonnerOptions(message?: string, action?: ToastAction, durationMs?: number) {
  return {
    description: message,
    duration: durationMs,
    action: action
      ? { label: action.label, onClick: () => router.push(action.to) }
      : undefined,
  }
}

/**
 * Thin facade over vue-sonner keeping the historical OpenSweep toast API:
 * `toast.success(title, message?, action?)` etc. The <Toaster /> in the
 * shell layout renders the actual toasts.
 */
export function useToast() {
  return {
    info: (title: string, message?: string, action?: ToastAction) =>
      toast.info(title, sonnerOptions(message, action, 4000)),
    success: (title: string, message?: string, action?: ToastAction) => {
      playUiSuccess()
      return toast.success(title, sonnerOptions(message, action, action ? 6000 : 4000))
    },
    error: (title: string, message?: string, action?: ToastAction) => {
      playUiError()
      return toast.error(title, sonnerOptions(message, action, action ? 8000 : 6000))
    },
    warn: (title: string, message?: string, action?: ToastAction) =>
      toast.warning(title, sonnerOptions(message, action, 5000)),
  }
}
