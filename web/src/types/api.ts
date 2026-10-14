export type IsoDateString = string
export type Money = string
export type Id = string

export type ApiErrorCode = 'validation_error' | 'unauthorized' | 'invalid_credentials' | 'invalid_reset_token' | 'invalid_verification_token' | 'email_unverified' | 'email_delivery_unavailable' | 'forbidden' | 'not_found' | 'conflict' | 'already_reviewed' | 'duplicate_email' | 'inactive_user' | 'invalid_token' | 'token_expired' | 'budget_exceeded' | 'concurrency_limit' | 'execution_in_progress' | 'execution_outcome_unknown' | 'idempotency_conflict' | 'model_not_available' | 'model_not_free' | 'provider_quota_exceeded' | 'provider_error' | 'provider_timeout' | 'provider_not_configured' | 'provider_configuration_error' | 'invalid_variables' | 'pricing_not_configured' | 'rate_limited' | 'internal_error'

export interface ApiErrorEnvelope {
  code: ApiErrorCode
  message: string
  field_errors?: Record<string, string[]> | null
  request_id?: string
}

export interface PageQuery {
  page?: number
  page_size?: number
  sort?: string
  direction?: 'asc' | 'desc'
}

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export type QueryValue = string | number | boolean | undefined | null
export type QueryParams = Record<string, QueryValue>
