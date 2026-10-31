import { apiClient } from '../../lib/api/client'
import type { ApiAuthSession, ApiUserSummary, LoginRequest, PendingVerificationResponse, RegisterRequest } from '../../types/auth'

export const authApi = {
  register: (request: RegisterRequest, signal?: AbortSignal) => apiClient.request<PendingVerificationResponse>('/auth/register', { method: 'POST', body: request, auth: false, signal }),
  login: (request: LoginRequest, signal?: AbortSignal) => apiClient.request<ApiAuthSession>('/auth/login', { method: 'POST', body: request, auth: false, signal }),
  logout: () => apiClient.request<void>('/auth/logout', { method: 'POST' }),
  me: (signal?: AbortSignal) => apiClient.request<ApiUserSummary>('/auth/me', { signal }),
  updateProfile: (display_name: string) => apiClient.request<ApiUserSummary>('/auth/me', { method: 'PATCH', body: { display_name } }),
  closeAccount: (password: string) => apiClient.request<void>('/auth/account', { method: 'DELETE', body: { password }, preserveSessionOnInvalidCredentials: true }),
  requestPasswordReset: (email: string) => apiClient.request<void>('/auth/password-reset', { method: 'POST', body: { email }, auth: false }),
  confirmPasswordReset: (token: string, password: string) => apiClient.request<void>('/auth/password-reset/confirm', { method: 'POST', body: { token, password }, auth: false }),
  confirmEmailVerification: (token: string) => apiClient.request<void>('/auth/email-verification/confirm', { method: 'POST', body: { token }, auth: false }),
  resendEmailVerification: (email: string) => apiClient.request<void>('/auth/email-verification/resend', { method: 'POST', body: { email }, auth: false }),
}
