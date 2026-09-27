import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { setAccessToken, clearAccessToken } from '../../lib/api/client'
import { demoUsers } from '../../mocks/users'
import type { LoginRequest, RegisterRequest, UserSummary } from '../../types/auth'

const sessionKey = 'promptvault.demo.session'
function restoreUser(): UserSummary | null {
  try {
    const id = sessionStorage.getItem(sessionKey)
    const saved = sessionStorage.getItem(`${sessionKey}.user`)
    const known = demoUsers.find((candidate) => candidate.id === id)
    const account = known ? (known.is_active ? known : null) : (saved ? JSON.parse(saved) as UserSummary : null)
    if (!account) return null
    setAccessToken(`demo-${account.id}`)
    return { id: account.id, email: account.email, display_name: account.display_name, role: account.role, is_active: account.is_active, created_at: account.created_at }
  } catch { return null }
}
type AuthValue = { user: UserSummary | null; login: (request: LoginRequest) => Promise<UserSummary>; register: (request: RegisterRequest) => Promise<UserSummary>; logout: () => void }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserSummary | null>(restoreUser)
  const value = useMemo<AuthValue>(() => ({ user,
    async login(request) { const match = demoUsers.find((candidate) => candidate.email === request.email.toLowerCase() && candidate.password === request.password); if (!match || !match.is_active) throw new Error('Incorrect email address, password, or inactive account.'); const account: UserSummary = { id: match.id, email: match.email, display_name: match.display_name, role: match.role, is_active: match.is_active, created_at: match.created_at }; setAccessToken(`demo-${account.id}`); sessionStorage.setItem(sessionKey, account.id); sessionStorage.setItem(`${sessionKey}.user`, JSON.stringify(account)); setUser(account); return account },
    async register(request) { const email = request.email.trim().toLowerCase(); const displayName = request.display_name.trim(); if (!displayName || !/^\S+@\S+\.\S+$/.test(email) || request.password.length < 8) throw new Error('Enter a name, valid email, and password of at least 8 characters.'); if (demoUsers.some((candidate) => candidate.email === email)) throw new Error('An account with this email already exists.'); const account: UserSummary = { id: `usr-${crypto.randomUUID()}`, email, display_name: displayName, role: 'user', is_active: true, created_at: new Date().toISOString() }; demoUsers.push({ ...account, password: request.password }); setAccessToken(`demo-${account.id}`); sessionStorage.setItem(sessionKey, account.id); sessionStorage.setItem(`${sessionKey}.user`, JSON.stringify(account)); setUser(account); return account },
    logout() { clearAccessToken(); sessionStorage.removeItem(sessionKey); sessionStorage.removeItem(`${sessionKey}.user`); setUser(null) },
  }), [user])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('useAuth must be used inside AuthProvider'); return value }
