import type { UserSummary } from '../types/auth'

export const demoCredentials = {
  user: { email: 'user@promptvault.dev', password: 'User@123' },
  superAdmin: { email: 'admin@promptvault.dev', password: 'Admin@123' },
} as const

export const demoUsers: Array<UserSummary & { password: string }> = [
  { id: 'usr_demo_user', email: demoCredentials.user.email, password: demoCredentials.user.password, display_name: 'Jamie Chen', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_admin', email: demoCredentials.superAdmin.email, password: demoCredentials.superAdmin.password, display_name: 'Alex Morgan', role: 'super_admin', is_active: true, created_at: '2025-01-10T09:00:00Z' },
]
