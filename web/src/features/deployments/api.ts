import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { BackendVersion } from '../projects/workspace-data'
import type { BackendPromptRun } from '../runs/api'
import type { CreateApiTokenRequest } from '../../types/deployments'

export type BackendDeploymentEnvironment = 'dev' | 'staging' | 'prod'
export type BackendDeploymentStatus = 'pending' | 'active' | 'rejected' | 'cancelled' | 'superseded' | 'rolled_back'

export interface BackendDeployment {
  id: Id
  project_id: Id
  prompt_id: Id
  prompt_key: string
  version_id: Id
  version_number: number
  environment: BackendDeploymentEnvironment
  status: BackendDeploymentStatus
  request_note: string | null
  review_note: string | null
  rollback_reason: string | null
  rollback_of_id: Id | null
  requested_by: { id: Id; display_name: string }
  reviewed_by: { id: Id; display_name: string } | null
  requested_at: string
  reviewed_at: string | null
  activated_at: string | null
}

export interface BackendDeploymentDetail extends BackendDeployment {
  timeline: Array<{
    id: Id
    version_id: Id
    version_number: number
    status: BackendDeploymentStatus
    requested_at: string
    reviewed_at: string | null
    activated_at: string | null
  }>
}

export interface BackendApiToken {
  id: Id
  project_id: Id
  name: string
  token_prefix: string
  created_by: Id
  created_at: string
  expires_at: string | null
  revoked_at: string | null
}

export interface BackendCreatedApiToken extends BackendApiToken { token: string }

export interface BackendDeploymentQuery {
  project_id?: Id
  prompt_id?: Id
  environment?: BackendDeploymentEnvironment
  status?: BackendDeploymentStatus
  page?: number
  page_size?: number
}

export const deploymentsApi = {
  list: (query: BackendDeploymentQuery = {}, signal?: AbortSignal) => apiClient.request<Page<BackendDeployment>>('/deployments', { query: { ...query }, signal }),
  get: (deploymentId: Id, signal?: AbortSignal) => apiClient.request<BackendDeploymentDetail>(`/deployments/${deploymentId}`, { signal }),
  create: (request: { version_id: Id; environment: BackendDeploymentEnvironment; request_note?: string }) => apiClient.request<BackendDeployment>('/deployments', { method: 'POST', body: request }),
  cancel: (deploymentId: Id) => apiClient.request<BackendDeployment>(`/deployments/${deploymentId}/cancel`, { method: 'POST' }),
}

export interface BackendDeploymentReviewDetail {
  deployment: BackendDeployment
  requested_version: BackendVersion
  active_version: BackendVersion | null
  recent_runs: BackendPromptRun[]
}

export const adminDeploymentsApi = {
  reviewDetail: (deploymentId: Id, signal?: AbortSignal) => apiClient.request<BackendDeploymentReviewDetail>(`/admin/deployments/${deploymentId}`, { signal }),
  pending: (page = 1, signal?: AbortSignal) => apiClient.request<Page<BackendDeployment>>('/admin/deployments/pending', { query: { page, page_size: 100 }, signal }),
  approve: (deploymentId: Id, reviewNote?: string) => apiClient.request<BackendDeployment>(`/admin/deployments/${deploymentId}/approve`, { method: 'POST', body: { review_note: reviewNote } }),
  reject: (deploymentId: Id, reviewNote: string) => apiClient.request<BackendDeployment>(`/admin/deployments/${deploymentId}/reject`, { method: 'POST', body: { review_note: reviewNote } }),
  rollback: (promptId: Id, targetVersionId: Id, reason: string) => apiClient.request<BackendDeployment>(`/admin/prompts/${promptId}/rollback`, { method: 'POST', body: { target_version_id: targetVersionId, reason } }),
}

export const apiTokensApi = {
  list: (page = 1, signal?: AbortSignal) => apiClient.request<Page<BackendApiToken>>('/api-tokens', { query: { page, page_size: 100 }, signal }),
  create: (request: CreateApiTokenRequest) => apiClient.request<BackendCreatedApiToken>('/api-tokens', { method: 'POST', body: request }),
  revoke: (tokenId: Id) => apiClient.request<void>(`/api-tokens/${tokenId}`, { method: 'DELETE' }),
}
