import { apiClient } from '../../lib/api/client'
import type { ApiAuthSession, ApiUserSummary, LoginRequest, RegisterRequest } from '../../types/auth'

export const authApi = {
  register: (request: RegisterRequest, signal?: AbortSignal) => apiClient.request<ApiAuthSession>('/api/v1/auth/register', { method: 'POST', body: request, auth: false, signal }),
  login: (request: LoginRequest, signal?: AbortSignal) => apiClient.request<ApiAuthSession>('/api/v1/auth/login', { method: 'POST', body: request, auth: false, signal }),
  me: (signal?: AbortSignal) => apiClient.request<ApiUserSummary>('/api/v1/auth/me', { signal }),
}
