import { apiClient } from '../../lib/api/client'
import type { Page } from '../../types/api'
import type { CreateRunRequest, PersonalDashboard, PromptRun, RunListQuery } from '../../types/runs'

export const runsApi = {
  create: (request: CreateRunRequest) => apiClient.request<PromptRun>('/runs', { method: 'POST', body: request }),
  list: (query: RunListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<PromptRun>>('/runs', { query: { ...query }, signal }),
  personalDashboard: (signal?: AbortSignal) => apiClient.request<PersonalDashboard>('/dashboard/me', { signal }),
}
