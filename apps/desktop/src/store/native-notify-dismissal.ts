import { attentionWhileFocusedEnabled, isAttentionKind, NATIVE_NOTIFICATION_KINDS } from './native-notifications'
import { hasPendingApproval, hasPendingInputPrompt } from './native-notify-resolution'
import { $activeSessionId } from './session'

// An OS notification is a request for attention. Once the user is looking at
// the session it is about (the window is focused and that chat is on screen),
// the request is answered: "Approval needed" for a prompt already approved
// in-app, or "Response ready" for a reply already read, must not linger in
// Notification/Action Center until the user swipes each one away.

function userIsLooking(): boolean {
  if (typeof document === 'undefined' || document.hidden) {
    return false
  }

  return typeof document.hasFocus !== 'function' || document.hasFocus()
}

/** In attention mode, approvals / questions the chat still waits on keep their notification: seeing the
 *  chat is not answering it (the notification is withdrawn when the prompt resolves instead). Returns
 *  the kinds that may be withdrawn, or undefined for "all of them". */
function dismissibleKinds(sessionId: string): string[] | undefined {
  if (!attentionWhileFocusedEnabled()) {
    return undefined
  }

  const pending = new Set<string>()

  if (hasPendingApproval(sessionId)) {
    pending.add('approval')
  }

  if (hasPendingInputPrompt(sessionId)) {
    pending.add('input')
  }

  return pending.size ? NATIVE_NOTIFICATION_KINDS.filter(kind => !isAttentionKind(kind) || !pending.has(kind)) : undefined
}

/** Withdraw the active session's OS notifications when the user is looking at it. */
export function dismissSeenSessionNotifications(): void {
  const sessionId = $activeSessionId.get()

  if (sessionId && userIsLooking()) {
    const kinds = dismissibleKinds(sessionId)

    void window.hermesDesktop?.dismissNotifications?.({ sessionId, ...(kinds ? { kinds } : {}) })?.catch(() => undefined)
  }
}

/** Track session switches and window returns; returns the teardown. */
export function startNativeNotifyDismissal(): () => void {
  if (typeof window === 'undefined') {
    return () => undefined
  }

  const unsubscribe = $activeSessionId.listen(() => dismissSeenSessionNotifications())
  window.addEventListener('focus', dismissSeenSessionNotifications)
  document.addEventListener('visibilitychange', dismissSeenSessionNotifications)

  return () => {
    unsubscribe()
    window.removeEventListener('focus', dismissSeenSessionNotifications)
    document.removeEventListener('visibilitychange', dismissSeenSessionNotifications)
  }
}
