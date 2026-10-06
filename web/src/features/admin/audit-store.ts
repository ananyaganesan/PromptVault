import type { AuditEvent } from '../../types/admin'
import type { UserSummary } from '../../types/auth'

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000).toISOString()
const seedEvents: AuditEvent[] = [
  { id: 'demo-audit-1', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'deployment.approved', resource_type: 'deployment', resource_id: 'deployment-production', request_id: 'demo-req-101', created_at: hoursAgo(2) },
  { id: 'demo-audit-2', actor_id: 'usr_demo_user', actor_name: 'Jamie Chen', action: 'deployment.requested', resource_type: 'deployment', resource_id: 'deployment-pending', request_id: 'demo-req-102', created_at: hoursAgo(5) },
  { id: 'demo-audit-3', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'budget.updated', resource_type: 'budget', resource_id: 'checkout', request_id: 'demo-req-103', created_at: hoursAgo(18) },
  { id: 'demo-audit-4', actor_id: 'usr_demo_user', actor_name: 'Jamie Chen', action: 'token.issued', resource_type: 'api_token', resource_id: 'demo-token-checkout-prod', request_id: 'demo-req-104', created_at: hoursAgo(30) },
  { id: 'demo-audit-5', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'user.updated', resource_type: 'user', resource_id: 'usr_demo_bob', request_id: 'demo-req-105', created_at: hoursAgo(52) },
  { id: 'demo-audit-6', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'provider_key.created', resource_type: 'provider_key', resource_id: 'provider-key-demo', request_id: 'demo-req-106', created_at: hoursAgo(75) },
  { id: 'demo-audit-7', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'model_price.created', resource_type: 'model_price', resource_id: 'price-mock', request_id: 'demo-req-107', created_at: hoursAgo(118) },
  { id: 'demo-audit-8', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'maintenance.views_refreshed', resource_type: 'maintenance', resource_id: 'views', request_id: 'demo-req-108', created_at: hoursAgo(144) },
  { id: 'demo-audit-9', actor_id: 'usr_demo_admin', actor_name: 'Alex Morgan', action: 'token.revoked', resource_type: 'api_token', resource_id: 'demo-token-checkout-legacy', request_id: 'demo-req-109', created_at: hoursAgo(240) },
]
let events: AuditEvent[] = [...seedEvents]
let revision = 0
const listeners = new Set<() => void>()
export const auditStore = {
  subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) },
  getSnapshot() { return revision },
  getEvents() { return events },
  record(action: string, resourceType: string, resourceId: string, actor: UserSummary) {
    events = [{ id: `audit-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, actor_id: actor.id, actor_name: actor.display_name, action, resource_type: resourceType, resource_id: resourceId, request_id: null, created_at: new Date().toISOString() }, ...events]
    revision += 1; listeners.forEach((listener) => listener())
  },
}
