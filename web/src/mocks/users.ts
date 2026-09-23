import type { UserSummary } from '../types/auth'

export const demoCredentials = {
  user: { email: 'user@promptvault.dev', password: 'UserDemo2026!' },
  alice: { email: 'alice@promptvault.dev', password: 'AliceDemo2026!' },
  bob: { email: 'bob@promptvault.dev', password: 'BobDemo2026!' },
  superAdmin: { email: 'admin@promptvault.dev', password: 'AdminDemo2026!' },
  inactive: { email: 'inactive@promptvault.dev', password: 'InactiveDemo2026!' },
} as const

export const demoUsers: Array<UserSummary & { password: string }> = [
  { id: 'usr_demo_user', email: demoCredentials.user.email, password: demoCredentials.user.password, display_name: 'Jamie Chen', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_admin', email: demoCredentials.superAdmin.email, password: demoCredentials.superAdmin.password, display_name: 'Alex Morgan', role: 'super_admin', is_active: true, created_at: '2025-01-10T09:00:00Z' },
  { id: 'usr_demo_alice', email: demoCredentials.alice.email, password: demoCredentials.alice.password, display_name: 'Alice Demo', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_bob', email: demoCredentials.bob.email, password: demoCredentials.bob.password, display_name: 'Bob Demo', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_inactive', email: demoCredentials.inactive.email, password: demoCredentials.inactive.password, display_name: 'Inactive Demo', role: 'user', is_active: false, created_at: '2025-01-15T09:00:00Z' },
]
