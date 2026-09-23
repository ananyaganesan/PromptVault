import { apiClient } from '../../lib/api/client'
import type { AuthSession, LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'

export const authApi = {
  register: (request: RegisterRequest, signal?: AbortSignal) => apiClient.request<AuthSession>('/auth/register', { method: 'POST', body: request, auth: false, signal }),
  login: (request: LoginRequest, signal?: AbortSignal) => apiClient.request<AuthSession>('/auth/login', { method: 'POST', body: request, auth: false, signal }),
  me: (signal?: AbortSignal) => apiClient.request<UserSummary>('/auth/me', { signal }),
}
