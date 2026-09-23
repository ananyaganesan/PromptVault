import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { clearAccessToken, setAccessToken } from '../../lib/api/client'
import { demoUsers } from '../../mocks/users'
import type { ApiUserSummary, LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'
import { authApi } from './api'

export type AuthMode = 'api' | 'demo'
const defaultMode: AuthMode = import.meta.env.VITE_USE_MOCK_AUTH === 'true' ? 'demo' : 'api'
const sessionKey = 'promptvault.demo.session'
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

function restoreDemoUser(): UserSummary | null {
  try {
    const id = sessionStorage.getItem(sessionKey)
    const saved = sessionStorage.getItem(`${sessionKey}.user`)
    const known = demoUsers.find((candidate) => candidate.id === id)
    const account = known ? (known.is_active ? known : null) : (saved ? JSON.parse(saved) as UserSummary : null)
    if (!account) return null
    setAccessToken(`demo-${account.id}`)
    return { id: account.id, email: account.email, display_name: account.display_name, role: account.role, is_active: account.is_active, created_at: account.created_at }
  } catch {
    return null
  }
}

function frontendUser(user: ApiUserSummary): UserSummary {
  return { ...user, role: user.role === 'admin' ? 'super_admin' : 'user' }
}

type AuthValue = {
  mode: AuthMode
  user: UserSummary | null
  restoring: boolean
  login: (request: LoginRequest) => Promise<UserSummary>
  register: (request: RegisterRequest) => Promise<UserSummary>
  logout: () => void
}
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children, mode = defaultMode }: { children: ReactNode; mode?: AuthMode }) {
  const [savedToken] = useState(() => mode === 'api' ? restoreApiToken() : null)
  const [user, setUser] = useState<UserSummary | null>(() => mode === 'demo' ? restoreDemoUser() : null)
  const [restoring, setRestoring] = useState(Boolean(savedToken))

  useEffect(() => {
    if (mode !== 'api' || !savedToken) return
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
  }, [mode, savedToken])

  const value = useMemo<AuthValue>(() => ({
    mode,
    user,
    restoring,
    async login(request) {
      if (mode === 'api') {
        const session = await authApi.login(request)
        const account = frontendUser(session.user)
        saveApiToken(session.access_token)
        setUser(account)
        return account
      }
      const match = demoUsers.find((candidate) => candidate.email === request.email.trim().toLowerCase())
      if (!match) throw new Error('Email address not found.')
      if (match.password !== request.password) throw new Error('Incorrect password.')
      if (!match.is_active) throw new Error('User account is inactive.')
      const account: UserSummary = { id: match.id, email: match.email, display_name: match.display_name, role: match.role, is_active: match.is_active, created_at: match.created_at }
      setAccessToken(`demo-${account.id}`)
      sessionStorage.setItem(sessionKey, account.id)
      sessionStorage.setItem(`${sessionKey}.user`, JSON.stringify(account))
      setUser(account)
      return account
    },
    async register(request) {
      if (mode === 'api') {
        const session = await authApi.register(request)
        const account = frontendUser(session.user)
        saveApiToken(session.access_token)
        setUser(account)
        return account
      }
      const email = request.email.trim().toLowerCase()
      const displayName = request.display_name.trim()
      if (!displayName || !/^\S+@\S+\.\S+$/.test(email) || request.password.length < 12) throw new Error('Enter a name, valid email, and password of at least 12 characters.')
      if (demoUsers.some((candidate) => candidate.email === email)) throw new Error('An account with this email already exists.')
      const account: UserSummary = { id: `usr-${crypto.randomUUID()}`, email, display_name: displayName, role: 'user', is_active: true, created_at: new Date().toISOString() }
      demoUsers.push({ ...account, password: request.password })
      setAccessToken(`demo-${account.id}`)
      sessionStorage.setItem(sessionKey, account.id)
      sessionStorage.setItem(`${sessionKey}.user`, JSON.stringify(account))
      setUser(account)
      return account
    },
    logout() {
      clearAccessToken()
      sessionStorage.removeItem(apiSessionKey)
      sessionStorage.removeItem(sessionKey)
      sessionStorage.removeItem(`${sessionKey}.user`)
      setUser(null)
    },
  }), [mode, user, restoring])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
