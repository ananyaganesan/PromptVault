import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
  const currentToken = useRef(savedToken)
  const [user, setUser] = useState<UserSummary | null>(null)
  const [restoring, setRestoring] = useState(Boolean(savedToken))

  useEffect(() => subscribeUnauthorized(() => {
    currentToken.current = null
    clearAccessToken()
    sessionStorage.removeItem(apiSessionKey)
    setUser(null)
    setRestoring(false)
  }), [])

  useEffect(() => {
    if (!savedToken) return
    const controller = new AbortController()
    const isCurrent = () => !controller.signal.aborted && currentToken.current === savedToken
    authApi.me(controller.signal)
      .then((account) => { if (isCurrent()) setUser(frontendUser(account)) })
      .catch(() => {
        if (isCurrent()) {
          currentToken.current = null
          clearAccessToken()
          sessionStorage.removeItem(apiSessionKey)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && (currentToken.current === savedToken || currentToken.current === null)) {
          setRestoring(false)
        }
      })
    return () => controller.abort()
  }, [savedToken])

  const value = useMemo<AuthValue>(() => ({
    user,
    restoring,
    async login(request) {
      const session = await authApi.login(request)
      if (!session.access_token) throw new Error('The server did not return a session token.')
      const account = frontendUser(session.user)
      currentToken.current = session.access_token
      saveApiToken(session.access_token)
      setUser(account)
      setRestoring(false)
      return account
    },
    async register(request) {
      const session = await authApi.register(request)
      if (!session.access_token) throw new Error('The server did not return a session token.')
      const account = frontendUser(session.user)
      currentToken.current = session.access_token
      saveApiToken(session.access_token)
      setUser(account)
      setRestoring(false)
      return account
    },
    logout() {
      currentToken.current = null
      clearAccessToken()
      sessionStorage.removeItem(apiSessionKey)
      setUser(null)
      setRestoring(false)
    },
  }), [user, restoring])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
