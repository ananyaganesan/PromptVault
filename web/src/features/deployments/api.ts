import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { ApiTokenMetadata, CreateApiTokenRequest, CreatedApiToken, CreateDeploymentRequest, Deployment, DeploymentListQuery } from '../../types/deployments'

export const deploymentsApi = {
  list: (query: DeploymentListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<Deployment>>('/deployments', { query: { ...query }, signal }),
  create: (request: CreateDeploymentRequest) => apiClient.request<Deployment>('/deployments', { method: 'POST', body: request }),
  cancel: (deploymentId: Id) => apiClient.request<Deployment>(`/deployments/${deploymentId}/cancel`, { method: 'POST' }),
}

export const apiTokensApi = {
  list: (signal?: AbortSignal) => apiClient.request<ApiTokenMetadata[]>('/api-tokens', { signal }),
  create: (request: CreateApiTokenRequest) => apiClient.request<CreatedApiToken>('/api-tokens', { method: 'POST', body: request }),
  revoke: (tokenId: Id) => apiClient.request<void>(`/api-tokens/${tokenId}`, { method: 'DELETE' }),
}
