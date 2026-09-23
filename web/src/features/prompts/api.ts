import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { CreatePromptRequest, Prompt, PromptListQuery, PromptSummary } from '../../types/prompts'
import type { CreateVersionRequest, PromptVersion } from '../../types/versions'

export const promptsApi = {
  listForProject: (projectId: Id, query: PromptListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<PromptSummary>>(`/projects/${projectId}/prompts`, { query: { ...query }, signal }),
  create: (projectId: Id, request: CreatePromptRequest) => apiClient.request<Prompt>(`/projects/${projectId}/prompts`, { method: 'POST', body: request }),
  get: (promptId: Id, signal?: AbortSignal) => apiClient.request<Prompt>(`/prompts/${promptId}`, { signal }),
  listVersions: (promptId: Id, signal?: AbortSignal) => apiClient.request<PromptVersion[]>(`/prompts/${promptId}/versions`, { signal }),
  createVersion: (promptId: Id, request: CreateVersionRequest) => apiClient.request<PromptVersion>(`/prompts/${promptId}/versions`, { method: 'POST', body: request }),
}
