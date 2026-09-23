import type { AuditEvent } from '../../types/admin'
import type { UserSummary } from '../../types/auth'

let events: AuditEvent[] = []
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
