import { apiClient } from '../../lib/api/client'
import type { Page } from '../../types/api'
import type { CreateRunRequest, PersonalDashboard, PromptRun, RunListQuery } from '../../types/runs'

export interface BackendPromptRun extends Omit<PromptRun, 'output' | 'error_message'> {
  provider: string
  output_text: string | null
  error_code: string | null
}

export interface BackendPersonalDashboard extends Omit<PersonalDashboard, 'recent_runs'> {
  month: string
  timezone: string
  completed_run_count: number
  failed_run_count: number
  blocked_run_count: number
  recent_runs: BackendPromptRun[]
  refreshed_through: string
}

export const runsApi = {
  create: (request: CreateRunRequest) => apiClient.request<BackendPromptRun>('/runs', {
    method: 'POST',
    body: request,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  }),
  list: (query: RunListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<BackendPromptRun>>('/runs', { query: { ...query }, signal }),
  get: (runId: string, signal?: AbortSignal) => apiClient.request<BackendPromptRun>(`/runs/${runId}`, { signal }),
  personalDashboard: (signal?: AbortSignal) => apiClient.request<BackendPersonalDashboard>('/dashboard/me', { signal }),
}
