import { afterEach, expect, it, vi } from 'vitest'

import { clearClarifyRequest, setClarifyRequest } from './clarify'
import { setNativeNotifyAttentionWhileFocused } from './native-notifications'
import { startNativeNotifyDismissal } from './native-notify-dismissal'
import { clearAllPrompts, setApprovalRequest } from './prompts'
import { $activeSessionId } from './session'

afterEach(() => {
  setNativeNotifyAttentionWhileFocused(false)
  clearAllPrompts()
  clearClarifyRequest()
  $activeSessionId.set(null)
  vi.restoreAllMocks()
})

it("withdraws a session's OS notifications once the user is looking at it, never while away", () => {
  const dismissNotifications = vi.fn(async () => 0)
  Object.assign(window, { hermesDesktop: { ...window.hermesDesktop, dismissNotifications } })
  const focused = vi.spyOn(document, 'hasFocus').mockReturnValue(false)
  const stop = startNativeNotifyDismissal()

  // Switching sessions while the window is in the background is not seeing it.
  $activeSessionId.set('runtime-1')
  expect(dismissNotifications).not.toHaveBeenCalled()

  focused.mockReturnValue(true)
  window.dispatchEvent(new Event('focus'))
  expect(dismissNotifications).toHaveBeenCalledWith({ sessionId: 'runtime-1' })

  $activeSessionId.set('runtime-2')
  expect(dismissNotifications).toHaveBeenLastCalledWith({ sessionId: 'runtime-2' })

  stop()
  $activeSessionId.set('runtime-3')
  expect(dismissNotifications).toHaveBeenCalledTimes(2)
})

it('in attention mode keeps the viewed session\'s pending approval/question notifications, closing the rest', () => {
  const dismissNotifications = vi.fn(async (_payload: { sessionId: string; kinds?: string[] }) => 0)
  Object.assign(window, { hermesDesktop: { ...window.hermesDesktop, dismissNotifications } })
  vi.spyOn(document, 'hasFocus').mockReturnValue(true)
  const stop = startNativeNotifyDismissal()
  setNativeNotifyAttentionWhileFocused(true)

  // Nothing pending: the PR behavior (everything about the session closes).
  $activeSessionId.set('runtime-1')
  expect(dismissNotifications).toHaveBeenLastCalledWith({ sessionId: 'runtime-1' })

  setApprovalRequest({ command: 'ls', description: 'd', requestId: 'r1', sessionId: 'runtime-2' })
  $activeSessionId.set('runtime-2')
  const approvalCall = dismissNotifications.mock.calls.at(-1)![0]
  expect(approvalCall.sessionId).toBe('runtime-2')
  expect(approvalCall.kinds).not.toContain('approval')
  expect(approvalCall.kinds).toContain('input')
  expect(approvalCall.kinds).toContain('turnDone')

  setClarifyRequest({
    questions: [{ choices: null, multiSelect: false, qid: 'a', question: 'q?' }],
    requestId: 'q1',
    sessionId: 'runtime-3'
  })
  $activeSessionId.set('runtime-3')
  const inputCall = dismissNotifications.mock.calls.at(-1)![0]
  expect(inputCall.kinds).not.toContain('input')
  expect(inputCall.kinds).toContain('approval')

  // With the pref off the PR behavior is untouched even for a pending prompt.
  setNativeNotifyAttentionWhileFocused(false)
  $activeSessionId.set('runtime-2')
  expect(dismissNotifications).toHaveBeenLastCalledWith({ sessionId: 'runtime-2' })

  stop()
})
