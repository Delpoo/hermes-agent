import type { ReadableAtom } from 'nanostores'

import { $clarifyRequests } from './clarify'
import { $connectionRequests } from './connection-request'
import {
  $approvalRequests,
  $secretRequests,
  $sudoRequests,
  $vaultCodeRequests,
  $vaultSaveLoginRequests,
  $vaultUnlockRequests
} from './prompts'
import { $setupBeatRequests } from './setup-beat'
import { $themePicks } from './theme-pick'

// A blocking prompt's OS notification (approval / question) is a request for the
// user's attention, so it must go away the moment the prompt does, whichever way
// that happens: answered in-app, answered from the toast's own buttons, expired,
// answered from another client, or the session ended. Rather than hook every one
// of those paths, watch the prompt stores: a session whose entry disappears has
// nothing left to ask, and its notification is withdrawn.

type PromptMap = ReadableAtom<Record<string, unknown>>

// Every store behind a `kind: 'input'` notification (see gateway-event/server-requests.ts).
const INPUT_STORES: readonly PromptMap[] = [
  $clarifyRequests,
  $sudoRequests,
  $secretRequests,
  $vaultUnlockRequests,
  $vaultSaveLoginRequests,
  $vaultCodeRequests,
  $connectionRequests,
  $themePicks,
  $setupBeatRequests
]

// Prompts are keyed by runtime session id (`''` = app-level prompt, no session).
const keyFor = (sessionId: string | null | undefined): string => sessionId ?? ''

/** Whether `sessionId` still has an approval parked on it. */
export const hasPendingApproval = (sessionId: string | null | undefined): boolean =>
  Boolean($approvalRequests.get()[keyFor(sessionId)])

/** Whether `sessionId` still has a question (clarify / password / MCP setup / ...) parked on it. */
export const hasPendingInputPrompt = (sessionId: string | null | undefined): boolean =>
  INPUT_STORES.some(store => Boolean(store.get()[keyFor(sessionId)]))

function dismiss(sessionId: string, kind: 'approval' | 'input'): void {
  void window.hermesDesktop?.dismissNotifications?.({ kinds: [kind], sessionId })?.catch(() => undefined)
}

/** Withdraw a session's OS notifications when its last prompt of a family goes away; returns the teardown. */
export function startNativeNotifyResolutionDismissal(): () => void {
  if (typeof window === 'undefined') {
    return () => undefined
  }

  const watch = (
    store: PromptMap,
    kind: 'approval' | 'input',
    stillPending: (sessionId: string) => boolean
  ): (() => void) =>
    store.listen((next, previous) => {
      for (const key of Object.keys(previous ?? {})) {
        // Nothing to withdraw by for an app-level prompt; the entry may also have just been
        // replaced or sit alongside another prompt of the same family.
        if (key && !(key in next) && !stillPending(key)) {
          dismiss(key, kind)
        }
      }
    })

  const stops = [
    watch($approvalRequests, 'approval', hasPendingApproval),
    ...INPUT_STORES.map(store => watch(store, 'input', hasPendingInputPrompt))
  ]

  return () => stops.forEach(stop => stop())
}
