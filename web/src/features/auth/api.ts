import { apiClient } from '../../lib/api/client'
import type { ApiAuthSession, ApiUserSummary, LoginRequest, RegisterRequest } from '../../types/auth'

export const authApi = {
  register: (request: RegisterRequest, signal?: AbortSignal) => apiClient.request<ApiAuthSession>('/auth/register', { method: 'POST', body: request, auth: false, signal }),
  login: (request: LoginRequest, signal?: AbortSignal) => apiClient.request<ApiAuthSession>('/auth/login', { method: 'POST', body: request, auth: false, signal }),
  logout: () => apiClient.request<void>('/auth/logout', { method: 'POST' }),
  me: (signal?: AbortSignal) => apiClient.request<ApiUserSummary>('/auth/me', { signal }),
  updateProfile: (display_name: string) => apiClient.request<ApiUserSummary>('/auth/me', { method: 'PATCH', body: { display_name } }),
  requestPasswordReset: (email: string) => apiClient.request<void>('/auth/password-reset', { method: 'POST', body: { email }, auth: false }),
  confirmPasswordReset: (token: string, password: string) => apiClient.request<void>('/auth/password-reset/confirm', { method: 'POST', body: { token, password }, auth: false }),
}
