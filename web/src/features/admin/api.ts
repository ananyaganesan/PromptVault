import { apiClient } from '../../lib/api/client'
import type { Id, Page } from '../../types/api'
import type { AdminRunListQuery, AuditListQuery } from '../../types/admin'
import type { BackendPromptRun } from '../runs/api'

export interface BackendAdminUser {
  id: Id
  email: string
  display_name: string
  role: 'user' | 'admin' | 'super_admin'
  is_approved?: boolean
  is_active: boolean
  project_count: number
  created_at: string
  updated_at: string
}

export interface BackendAdminDashboard {
  month: string
  timezone: string
  user_count: number
  active_user_count: number
  project_count: number
  prompt_count: number
  run_count: number
  completed_run_count: number
  failed_run_count: number
  blocked_run_count: number
  total_spend: string
  pending_approval_count: number
  spend_by_model: Array<{ provider: string; model: string; run_count: number; cost: string }>
  cost_trend: Array<{ date: string; cost: string; run_count: number }>
  top_spenders: Array<{ user_id: Id; display_name: string; cost: string }>
  refreshed_through: string
}

export interface BackendBudget {
  id: Id
  user_id: Id | null
  project_id: Id | null
  monthly_limit: string
  timezone: string
  created_by: Id | null
  created_at: string
  updated_at: string
}

export interface BackendProviderKey {
  id: Id
  provider: string
  alias: string
  created_by: Id
  created_at: string
  deactivated_at: string | null
}

export interface BackendModelPricing {
  id: Id
  provider: string
  model: string
  input_price_per_million: string
  output_price_per_million: string
  effective_from: string
  effective_to: string | null
  created_by: Id | null
  created_at: string
}

export interface BackendAuditEvent {
  id: number
  actor_user_id: Id | null
  action: string
  entity_type: string
  entity_id: Id | null
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  request_id: string | null
  created_at: string
}

export interface BackendMaintenanceStatus {
  database: string
  materialized_views: Array<{ name: string; is_populated: boolean; refreshed_through: string | null }>
  run_partitions: Array<{ name: string; range_expression: string }>
  maintenance_jobs: Array<{ name: string; status: 'never_run' | 'completed'; last_completed_at: string | null }>
  active_provider_key_count: number
  pending_deployment_count: number
  checked_at: string
}

export const adminApi = {
  dashboard: (signal?: AbortSignal) => apiClient.request<BackendAdminDashboard>('/admin/dashboard', { signal }),
  listUsers: (query: { page?: number; page_size?: number; search?: string; role?: 'user' | 'admin' | 'super_admin'; is_active?: boolean } = {}, signal?: AbortSignal) => apiClient.request<Page<BackendAdminUser>>('/admin/users', { query, signal }),
  updateUser: (userId: Id, request: { role?: 'user' | 'admin' | 'super_admin'; is_active?: boolean; is_approved?: boolean }) => apiClient.request<BackendAdminUser>(`/admin/users/${userId}`, { method: 'PATCH', body: request }),
  listBudgets: (query: { page?: number; page_size?: number } = {}, signal?: AbortSignal) => apiClient.request<Page<BackendBudget>>('/admin/budgets', { query, signal }),
  createBudget: (request: { user_id?: Id; project_id?: Id; monthly_limit: string; timezone: string }) => apiClient.request<BackendBudget>('/admin/budgets', { method: 'POST', body: request }),
  updateBudget: (budgetId: Id, request: { monthly_limit: string; timezone?: string }) => apiClient.request<BackendBudget>(`/admin/budgets/${budgetId}`, { method: 'PATCH', body: request }),
  listRuns: (query: AdminRunListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<BackendPromptRun>>('/admin/runs', { query: { ...query }, signal }),
  listAudit: (query: AuditListQuery = {}, signal?: AbortSignal) => apiClient.request<Page<BackendAuditEvent>>('/admin/audit', { query: { ...query }, signal }),
  listModelPrices: (query: { page?: number; page_size?: number } = {}, signal?: AbortSignal) => apiClient.request<Page<BackendModelPricing>>('/admin/model-pricing', { query, signal }),
  createModelPrice: (request: { provider: string; model: string; input_price_per_million: string; output_price_per_million: string; effective_from: string }) => apiClient.request<BackendModelPricing>('/admin/model-pricing', { method: 'POST', body: request }),
  maintenanceStatus: (signal?: AbortSignal) => apiClient.request<BackendMaintenanceStatus>('/admin/maintenance', { signal }),
  refreshViews: () => apiClient.request<{ status: string; views: string[]; completed_at: string }>('/admin/maintenance/refresh-views', { method: 'POST' }),
  listProviderKeys: (query: { page?: number; page_size?: number } = {}, signal?: AbortSignal) => apiClient.request<Page<BackendProviderKey>>('/admin/provider-keys', { query, signal }),
  createProviderKey: (request: { provider: string; alias: string; secret: string }) => apiClient.request<BackendProviderKey>('/admin/provider-keys', { method: 'POST', body: request }),
  deactivateProviderKey: (keyId: Id) => apiClient.request<void>(`/admin/provider-keys/${keyId}`, { method: 'DELETE' }),
}
