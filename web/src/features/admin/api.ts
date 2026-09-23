import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { AdminRunListQuery, AdminUser, AuditEvent, AuditListQuery, Budget, CreateModelPriceRequest, CreateProviderKeyRequest, MaintenanceStatus, ModelPrice, OrganizationDashboard, ProviderKeyMetadata, UpdateUserRequest, UpsertBudgetRequest } from '../../types/admin'
import type { Deployment, ReviewDeploymentRequest } from '../../types/deployments'
import type { PromptRun } from '../../types/runs'

export const adminApi = {
  dashboard: (signal?: AbortSignal) => apiClient.request<OrganizationDashboard>('/admin/dashboard', { signal }),
  pendingDeployments: (signal?: AbortSignal) => apiClient.request<Deployment[]>('/admin/deployments/pending', { signal }),
  approveDeployment: (deploymentId: Id, request: ReviewDeploymentRequest = {}) => apiClient.request<Deployment>(`/admin/deployments/${deploymentId}/approve`, { method: 'POST', body: request }),
  rejectDeployment: (deploymentId: Id, request: ReviewDeploymentRequest) => apiClient.request<Deployment>(`/admin/deployments/${deploymentId}/reject`, { method: 'POST', body: request }),
  rollback: (deploymentId: Id, request: { target_version_id: Id; note: string }) => apiClient.request<Deployment>(`/admin/deployments/${deploymentId}/rollback`, { method: 'POST', body: request }),
  listUsers: (query: { page?: number; page_size?: number; search?: string; role?: string; is_active?: boolean } = {}, signal?: AbortSignal) => apiClient.request<Page<AdminUser>>('/admin/users', { query, signal }),
  updateUser: (userId: Id, request: UpdateUserRequest) => apiClient.request<AdminUser>(`/admin/users/${userId}`, { method: 'PATCH', body: request }),
  listBudgets: (signal?: AbortSignal) => apiClient.request<Budget[]>('/admin/budgets', { signal }),
  upsertBudget: (request: UpsertBudgetRequest) => apiClient.request<Budget>('/admin/budgets', { method: 'POST', body: request }),
  listRuns: (query: AdminRunListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<PromptRun>>('/admin/runs', { query: { ...query }, signal }),
  listAudit: (query: AuditListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<AuditEvent>>('/admin/audit', { query: { ...query }, signal }),
  listModelPrices: (signal?: AbortSignal) => apiClient.request<ModelPrice[]>('/admin/model-pricing', { signal }),
  createModelPrice: (request: CreateModelPriceRequest) => apiClient.request<ModelPrice>('/admin/model-pricing', { method: 'POST', body: request }),
  maintenanceStatus: (signal?: AbortSignal) => apiClient.request<MaintenanceStatus>('/admin/maintenance', { signal }),
  refreshViews: () => apiClient.request<MaintenanceStatus>('/admin/maintenance/refresh-views', { method: 'POST' }),
  listProviderKeys: (signal?: AbortSignal) => apiClient.request<ProviderKeyMetadata[]>('/admin/provider-keys', { signal }),
  createProviderKey: (request: CreateProviderKeyRequest) => apiClient.request<ProviderKeyMetadata>('/admin/provider-keys', { method: 'POST', body: request }),
  deactivateProviderKey: (keyId: Id) => apiClient.request<ProviderKeyMetadata>(`/admin/provider-keys/${keyId}/deactivate`, { method: 'POST' }),
}
