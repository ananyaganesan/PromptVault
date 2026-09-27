import { apiClient } from '../../lib/api/client'
import type { AuthSession, LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'

type BackendUser = Omit<UserSummary, 'role'> & { role: 'user' | 'admin' }
type BackendSession = Omit<AuthSession, 'user'> & { user: BackendUser }

function normalizeUser(user: BackendUser): UserSummary {
  return { ...user, role: user.role === 'admin' ? 'super_admin' : 'user' }
}

export const authApi = {
  async register(request: RegisterRequest, signal?: AbortSignal): Promise<AuthSession> {
    const session = await apiClient.request<BackendSession>('/auth/register', { method: 'POST', body: request, auth: false, signal })
    return { ...session, user: normalizeUser(session.user) }
  },
  async login(request: LoginRequest, signal?: AbortSignal): Promise<AuthSession> {
    const session = await apiClient.request<BackendSession>('/auth/login', { method: 'POST', body: request, auth: false, signal })
    return { ...session, user: normalizeUser(session.user) }
  },
  async me(signal?: AbortSignal): Promise<UserSummary> {
    return normalizeUser(await apiClient.request<BackendUser>('/auth/me', { signal }))
  },
}
