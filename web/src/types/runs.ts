import type { Id, IsoDateString, Money, PageQuery } from './api'

export type RunStatus = 'completed' | 'blocked' | 'failed'

export interface PromptRun {
  id: Id
  project_id: Id
  prompt_id: Id
  prompt_key: string
  version_id: Id
  version_number: number
  user_id: Id
  status: RunStatus
  output: string | null
  input_variables: Record<string, string>
  prompt_tokens: number | null
  completion_tokens: number | null
  latency_ms: number | null
  cost: Money
  model: string
  created_at: IsoDateString
  error_message?: string | null
}

export interface CreateRunRequest {
  version_id: Id
  variables: Record<string, string>
}

export interface RunListQuery extends PageQuery {
  search?: string
  project_id?: Id
  prompt_id?: Id
  status?: RunStatus
  from?: IsoDateString
  to?: IsoDateString
}

export interface CostTrendPoint {
  date: string
  cost: Money
  run_count: number
}

export interface PersonalDashboard {
  project_count: number
  prompt_count: number
  monthly_spend: Money
  monthly_budget: Money | null
  pending_approval_count: number
  run_count: number
  cost_trend: CostTrendPoint[]
  recent_runs: PromptRun[]
}
