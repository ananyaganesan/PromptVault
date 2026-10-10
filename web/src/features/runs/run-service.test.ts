import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../../lib/api/client'
import * as liveRefresh from '../../lib/live-refresh'
import type { ApiErrorCode } from '../../types/api'
import { runsApi, type BackendPromptRun } from './api'
import { runService, runStore } from './run-service'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))

const request = { version_id: 'version-1', variables: { message: 'Hello' } }
const recorded: BackendPromptRun = {
  id: 'run-1', user_id: 'user-1', project_id: 'project-1', prompt_id: 'prompt-1',
  prompt_key: 'reply', version_id: 'version-1', version_number: 1,
  provider: 'mock', model: 'deterministic-v1', status: 'completed',
  input_variables: request.variables, output_text: 'Hello', prompt_tokens: 1,
  completion_tokens: 1, latency_ms: 25, cost: '0', error_code: null,
  created_at: '2026-10-10T10:00:00Z',
}

afterEach(() => vi.restoreAllMocks())

describe('live run outcome freshness', () => {
  it.each(['completed', 'failed', 'blocked'] as const)('refreshes a returned %s run', async (status) => {
    const create = vi.spyOn(runsApi, 'create').mockResolvedValue({ ...recorded, status })
    const refresh = vi.spyOn(liveRefresh, 'refreshLiveData')
    const before = runStore.getSnapshot()

    expect((await runService.create(request)).status).toBe(status)

    expect(create).toHaveBeenCalledWith(request)
    expect(runStore.getSnapshot()).toBe(before + 1)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it.each<[number, ApiErrorCode]>([
    [502, 'provider_error'], [504, 'provider_timeout'], [409, 'budget_exceeded'],
  ])('refreshes recorded execution error %i/%s without inventing a run or replacing its error', async (status, code) => {
    const error = new ApiClientError(status, { code, message: 'Original execution message', request_id: 'request-1' })
    vi.spyOn(runsApi, 'create').mockRejectedValue(error)
    const refresh = vi.spyOn(liveRefresh, 'refreshLiveData')
    const before = runStore.getSnapshot()
    const rows = [...runStore.getRuns()]
    const listener = vi.fn()
    const unsubscribe = runStore.subscribe(listener)
    try {
      await expect(runService.create(request)).rejects.toBe(error)
      expect(runStore.getSnapshot()).toBe(before + 1)
      expect(listener).toHaveBeenCalledTimes(1)
      expect(refresh).toHaveBeenCalledTimes(1)
      expect(runStore.getRuns()).toEqual(rows)
      expect(error.requestId).toBe('request-1')
    } finally { unsubscribe() }
  })

  it.each([
    new TypeError('Failed to fetch'),
    new ApiClientError(422, { code: 'validation_error', message: 'Request is invalid', field_errors: { 'body.variables': ['Too large'] } }),
    new ApiClientError(422, { code: 'invalid_variables', message: 'Variables must match' }),
    new ApiClientError(409, { code: 'pricing_not_configured', message: 'Model pricing is not configured' }),
    new ApiClientError(401, { code: 'unauthorized', message: 'Authentication required' }),
    new ApiClientError(500, { code: 'internal_error', message: 'An unexpected error occurred' }),
    new ApiClientError(502, { code: 'internal_error', message: 'Gateway failed' }),
    new ApiClientError(500, { code: 'provider_error', message: 'Unconfirmed execution failure' }),
  ])('does not claim persistence for $message', async (error) => {
    vi.spyOn(runsApi, 'create').mockRejectedValue(error)
    const refresh = vi.spyOn(liveRefresh, 'refreshLiveData')
    const before = runStore.getSnapshot()
    const rows = [...runStore.getRuns()]

    await expect(runService.create(request)).rejects.toBe(error)

    expect(runStore.getSnapshot()).toBe(before)
    expect(refresh).not.toHaveBeenCalled()
    expect(runStore.getRuns()).toEqual(rows)
  })
})
