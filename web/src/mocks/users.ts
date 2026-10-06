import type { UserSummary } from '../types/auth'

/** Display-only examples for the optional demo workspace. These cannot authenticate. */
export const sampleUserProfiles: UserSummary[] = [
  { id: 'usr_demo_user', email: 'user@promptvault.dev', display_name: 'Jamie Chen', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_admin', email: 'admin@promptvault.dev', display_name: 'Alex Morgan', role: 'super_admin', is_active: true, created_at: '2025-01-10T09:00:00Z' },
  { id: 'usr_demo_alice', email: 'alice@promptvault.dev', display_name: 'Alice Demo', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_bob', email: 'bob@promptvault.dev', display_name: 'Bob Demo', role: 'user', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'usr_demo_inactive', email: 'inactive@promptvault.dev', display_name: 'Inactive Demo', role: 'user', is_active: false, created_at: '2025-01-15T09:00:00Z' },
]
