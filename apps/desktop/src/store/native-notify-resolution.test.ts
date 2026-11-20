import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { clearClarifyRequest, setClarifyRequest } from './clarify'
import { startNativeNotifyResolutionDismissal } from './native-notify-resolution'
import { clearAllPrompts, clearApprovalRequest, setApprovalRequest, setSudoRequest } from './prompts'

const dismissNotifications = vi.fn(async () => 1)
const desktopWindow = window as unknown as { hermesDesktop?: Window['hermesDesktop'] }
const initialHermesDesktop = desktopWindow.hermesDesktop
let stop: () => void

const approval = (sessionId: string, requestId = 'req-1') => ({
  command: 'rm -rf build',
  description: 'dangerous command',
  requestId,
  sessionId
})

const question = (sessionId: string, requestId = 'q-1') => ({
  questions: [{ choices: null, multiSelect: false, qid: 'a', question: 'Which one?' }],
  requestId,
  sessionId
})

beforeEach(() => {
  dismissNotifications.mockClear()
  desktopWindow.hermesDesktop = { dismissNotifications } as unknown as Window['hermesDesktop']
  clearAllPrompts()
  stop = startNativeNotifyResolutionDismissal()
})

afterEach(() => {
  stop()
  clearAllPrompts()
  clearClarifyRequest()

  if (initialHermesDesktop) {
    desktopWindow.hermesDesktop = initialHermesDesktop
  } else {
    delete desktopWindow.hermesDesktop
  }
})

it('withdraws the approval notification when the prompt is answered in-app or from the toast (same store path)', () => {
  setApprovalRequest(approval('runtime-1'))
  expect(dismissNotifications).not.toHaveBeenCalled()

  clearApprovalRequest('runtime-1', 'req-1')
  expect(dismissNotifications).toHaveBeenCalledTimes(1)
  expect(dismissNotifications).toHaveBeenCalledWith({ kinds: ['approval'], sessionId: 'runtime-1' })
})

it('withdraws it when the session ends or the prompts are reset, and ignores other sessions', () => {
  setApprovalRequest(approval('runtime-1'))
  setApprovalRequest(approval('runtime-2'))

  clearAllPrompts('runtime-1')
  expect(dismissNotifications).toHaveBeenCalledTimes(1)
  expect(dismissNotifications).toHaveBeenLastCalledWith({ kinds: ['approval'], sessionId: 'runtime-1' })

  clearAllPrompts()
  expect(dismissNotifications).toHaveBeenCalledTimes(2)
  expect(dismissNotifications).toHaveBeenLastCalledWith({ kinds: ['approval'], sessionId: 'runtime-2' })
})

it('keeps the notification while a queued approval is still pending, then withdraws it', () => {
  setApprovalRequest(approval('runtime-1', 'req-1'))
  setApprovalRequest(approval('runtime-1', 'req-2'))

  clearApprovalRequest('runtime-1', 'req-1')
  expect(dismissNotifications).not.toHaveBeenCalled()

  clearApprovalRequest('runtime-1', 'req-2')
  expect(dismissNotifications).toHaveBeenCalledWith({ kinds: ['approval'], sessionId: 'runtime-1' })
})

it('withdraws the input notification when a question is answered, skipped or expires', () => {
  setClarifyRequest(question('runtime-1'))
  expect(dismissNotifications).not.toHaveBeenCalled()

  clearClarifyRequest('q-1', 'runtime-1')
  expect(dismissNotifications).toHaveBeenCalledTimes(1)
  expect(dismissNotifications).toHaveBeenCalledWith({ kinds: ['input'], sessionId: 'runtime-1' })
})

it('does not touch the approval notification when only a question resolves, and vice versa', () => {
  setApprovalRequest(approval('runtime-1'))
  setClarifyRequest(question('runtime-1'))

  clearClarifyRequest('q-1', 'runtime-1')
  expect(dismissNotifications).toHaveBeenCalledTimes(1)
  expect(dismissNotifications).toHaveBeenLastCalledWith({ kinds: ['input'], sessionId: 'runtime-1' })

  clearApprovalRequest('runtime-1')
  expect(dismissNotifications).toHaveBeenCalledTimes(2)
  expect(dismissNotifications).toHaveBeenLastCalledWith({ kinds: ['approval'], sessionId: 'runtime-1' })
})

it('keeps the input notification while another input prompt (sudo) is still parked on the session', () => {
  setClarifyRequest(question('runtime-1'))
  setSudoRequest({ requestId: 'sudo-1', sessionId: 'runtime-1' })

  clearClarifyRequest('q-1', 'runtime-1')
  expect(dismissNotifications).not.toHaveBeenCalled()
})

it('stops watching after teardown', () => {
  setApprovalRequest(approval('runtime-1'))
  stop()
  clearApprovalRequest('runtime-1')
  expect(dismissNotifications).not.toHaveBeenCalled()
})
