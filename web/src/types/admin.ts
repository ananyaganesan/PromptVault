import type { Id, IsoDateString, Money, PageQuery } from './api'
import type { UserRole, UserSummary } from './auth'
import type { RunListQuery } from './runs'

export interface AdminUser extends UserSummary {
  project_count: number
  last_active_at: IsoDateString | null
}

export interface UpdateUserRequest {
  role?: UserRole
  is_active?: boolean
}

export interface Budget {
  id: Id
  target_type: 'user' | 'project'
  target_id: Id
  target_name: string
  monthly_limit: Money
  monthly_spend: Money
  period_start: IsoDateString
  period_end: IsoDateString
}

export interface UpsertBudgetRequest {
  target_type: 'user' | 'project'
  target_id: Id
  monthly_limit: Money
}

export interface ModelPrice {
  id: Id
  provider: string
  model: string
  token_type: 'input' | 'output' | 'combined'
  price_per_million_tokens: Money
  effective_from: IsoDateString
  effective_to: IsoDateString | null
}

export interface CreateModelPriceRequest {
  provider: string
  model: string
  input_price_per_million: Money
  output_price_per_million: Money
  effective_from: IsoDateString
}

export interface AuditEvent {
  id: Id
  actor_id: Id | null
  actor_name: string | null
  action: string
  resource_type: string
  resource_id: Id | null
  request_id: string | null
  created_at: IsoDateString
}

export interface AuditListQuery extends PageQuery {
  action?: string
  actor_id?: Id
  from?: IsoDateString
  to?: IsoDateString
}

export interface OrganizationDashboard {
  monthly_spend: Money
  run_count: number
  active_user_count: number
  pending_approval_count: number
  spend_by_model: Array<{ model: string; cost: Money; percentage: number }>
}

export interface MaintenanceStatus {
  api_status: 'healthy' | 'degraded' | 'unavailable'
  database_status: 'healthy' | 'degraded' | 'unavailable'
  partition_count: number
  last_view_refresh_at: IsoDateString | null
}

export interface AdminRunListQuery extends RunListQuery {
  user_id?: Id
}

export interface ProviderKeyMetadata {
  id: Id
  provider: string
  label: string
  created_at: IsoDateString
  deactivated_at: IsoDateString | null
}

export interface CreateProviderKeyRequest {
  provider: string
  label: string
  secret: string
}
