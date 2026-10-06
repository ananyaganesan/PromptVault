export type IsoDateString = string
export type Money = string
export type Id = string

export type ApiErrorCode = 'validation_error' | 'unauthorized' | 'invalid_credentials' | 'invalid_reset_token' | 'email_delivery_unavailable' | 'forbidden' | 'not_found' | 'conflict' | 'duplicate_email' | 'inactive_user' | 'invalid_token' | 'token_expired' | 'budget_exceeded' | 'provider_error' | 'internal_error'

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
