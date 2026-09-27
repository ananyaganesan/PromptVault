import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { setAccessToken, clearAccessToken, subscribeUnauthorized } from '../../lib/api/client'
import type { LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'
import { authApi } from './api'

const sessionKey = 'promptvault.session'
const tokenKey = `${sessionKey}.token`
const userKey = `${sessionKey}.user`

function restoreUser(): UserSummary | null {
  try {
    const token = sessionStorage.getItem(tokenKey)
    const saved = sessionStorage.getItem(userKey)
    if (!token || !saved) return null
    setAccessToken(token)
    return JSON.parse(saved) as UserSummary
  } catch { return null }
}

type AuthValue = { user: UserSummary | null; restoring: boolean; login: (request: LoginRequest) => Promise<UserSummary>; register: (request: RegisterRequest) => Promise<UserSummary>; logout: () => void }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSummary | null>(restoreUser)
  const [restoring, setRestoring] = useState(() => Boolean(sessionStorage.getItem(tokenKey)))

  function clearSession() {
    clearAccessToken()
    sessionStorage.removeItem(tokenKey)
    sessionStorage.removeItem(userKey)
    setUser(null)
  }

  function persistSession(token: string, account: UserSummary) {
    setAccessToken(token)
    sessionStorage.setItem(tokenKey, token)
    sessionStorage.setItem(userKey, JSON.stringify(account))
    setUser(account)
  }

  useEffect(() => {
    const unsubscribe = subscribeUnauthorized(clearSession)
    if (!sessionStorage.getItem(tokenKey)) return unsubscribe
    const controller = new AbortController()
    authApi.me(controller.signal)
      .then((account) => {
        sessionStorage.setItem(userKey, JSON.stringify(account))
        setUser(account)
      })
      .catch(() => {
        if (!controller.signal.aborted) clearSession()
      })
      .finally(() => {
        if (!controller.signal.aborted) setRestoring(false)
      })
    return () => {
      unsubscribe()
      controller.abort()
    }
  }, [])

  const value = useMemo<AuthValue>(() => ({ user, restoring,
    async login(request) { const session = await authApi.login(request); persistSession(session.access_token, session.user); return session.user },
    async register(request) { const session = await authApi.register(request); persistSession(session.access_token, session.user); return session.user },
    logout: clearSession,
  }), [user, restoring])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('useAuth must be used inside AuthProvider'); return value }
