import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { clearAccessToken, setAccessToken, subscribeUnauthorized } from '../../lib/api/client'
import type { ApiUserSummary, LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'
import { authApi } from './api'
const apiSessionKey = 'promptvault.api.session'

function restoreApiToken(): string | null {
  try {
    const token = sessionStorage.getItem(apiSessionKey)
    setAccessToken(token)
    return token
  } catch {
    return null
  }
}

function saveApiToken(token: string) {
  setAccessToken(token)
  sessionStorage.setItem(apiSessionKey, token)
}

function frontendUser(user: ApiUserSummary): UserSummary {
  return { ...user, role: user.role === 'admin' ? 'super_admin' : 'user' }
}

type AuthValue = {
  user: UserSummary | null
  restoring: boolean
  login: (request: LoginRequest) => Promise<UserSummary>
  register: (request: RegisterRequest) => Promise<UserSummary>
  logout: () => void
}
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [savedToken] = useState(restoreApiToken)
  const [user, setUser] = useState<UserSummary | null>(null)
  const [restoring, setRestoring] = useState(Boolean(savedToken))

  useEffect(() => subscribeUnauthorized(() => {
    clearAccessToken()
    sessionStorage.removeItem(apiSessionKey)
    setUser(null)
    setRestoring(false)
  }), [])

  useEffect(() => {
    if (!savedToken) return
    const controller = new AbortController()
    authApi.me(controller.signal)
      .then((account) => { if (!controller.signal.aborted) setUser(frontendUser(account)) })
      .catch(() => {
        if (!controller.signal.aborted) {
          clearAccessToken()
          sessionStorage.removeItem(apiSessionKey)
        }
      })
      .finally(() => { if (!controller.signal.aborted) setRestoring(false) })
    return () => controller.abort()
  }, [savedToken])

  const value = useMemo<AuthValue>(() => ({
    user,
    restoring,
    async login(request) {
      const session = await authApi.login(request)
      if (!session.access_token) throw new Error('The server did not return a session token.')
      const account = frontendUser(session.user)
      saveApiToken(session.access_token)
      setUser(account)
      return account
    },
    async register(request) {
      const session = await authApi.register(request)
      if (!session.access_token) throw new Error('The server did not return a session token.')
      const account = frontendUser(session.user)
      saveApiToken(session.access_token)
      setUser(account)
      return account
    },
    logout() {
      clearAccessToken()
      sessionStorage.removeItem(apiSessionKey)
      setUser(null)
    },
  }), [user, restoring])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
