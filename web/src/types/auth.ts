import type { Id, IsoDateString } from './api'

export type UserRole = 'user' | 'super_admin'

export interface UserSummary {
  id: Id
  email: string
  display_name: string
  role: UserRole
  is_active: boolean
  created_at: IsoDateString
}

export interface AuthSession {
  user: UserSummary
  access_token: string
  token_type: 'bearer'
}

export interface RegisterRequest {
  display_name: string
  email: string
  password: string
}

export interface LoginRequest {
  email: string
  password: string
}
