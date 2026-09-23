import { adminApi } from '../admin/api'
import { apiTokensApi, deploymentsApi } from './api'
import { projectStore, promptStore, versionStore } from '../projects/workspace-data'
import type { Id, Page } from '../../types/api'
import type { ApiTokenMetadata, CreateApiTokenRequest, CreatedApiToken, CreateDeploymentRequest, Deployment, DeploymentListQuery, DeploymentStatus, ReviewDeploymentRequest } from '../../types/deployments'
import type { UserSummary } from '../../types/auth'
import { auditStore } from '../admin/audit-store'

const useDemoDeployments = import.meta.env.VITE_USE_MOCK_DEPLOYMENTS !== 'false'
const now = () => new Date().toISOString()
const seed: Deployment[] = [
  { id: 'deployment-pending', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, environment: 'production', status: 'pending_approval', note: 'Add order context to checkout responses.', requested_by: 'usr_demo_user', requested_by_name: 'Jamie Chen', reviewed_by: null, reviewed_at: null, review_note: null, created_at: '2025-08-28T11:00:00Z' },
  { id: 'deployment-production', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v2', version_number: 2, environment: 'production', status: 'active', note: 'Previous stable production version.', requested_by: 'usr_demo_admin', requested_by_name: 'Alex Morgan', reviewed_by: 'usr_demo_admin', reviewed_at: '2025-08-24T12:00:00Z', review_note: 'Approved', created_at: '2025-08-24T11:00:00Z' },
  { id: 'deployment-staging', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, environment: 'staging', status: 'active', note: 'Staging validation.', requested_by: 'usr_demo_user', requested_by_name: 'Jamie Chen', reviewed_by: null, reviewed_at: null, review_note: null, created_at: '2025-08-28T10:45:00Z' },
]
let deployments = seed
let tokens: ApiTokenMetadata[] = []
let revision = 0
const listeners = new Set<() => void>()
const notify = () => { revision += 1; listeners.forEach((listener) => listener()) }
export const deploymentStore = { subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, getSnapshot() { return revision } }

function requireUser(user: UserSummary | null): UserSummary { if (!user) throw new Error('Sign in to continue.'); return user }
function requireAdmin(user: UserSummary | null): UserSummary { const actor = requireUser(user); if (actor.role !== 'super_admin') throw new Error('Super Admin access is required.'); return actor }
function versionInfo(versionId: Id) {
  const version = Object.values(versionStore).flat().find((item) => item.id === versionId)
  const prompt = promptStore.find((item) => item.id === version?.prompt_id)
  const project = projectStore.find((item) => item.id === prompt?.project_id)
  if (!version || !prompt || !project) throw new Error('Select a valid prompt version.')
  return { version, prompt, project }
}
function uniqueId(prefix: string) { return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }

export const deploymentService = {
  async list(query: DeploymentListQuery = {}): Promise<Page<Deployment>> {
    if (!useDemoDeployments) return deploymentsApi.list(query)
    const items = deployments.filter((item) => (!query.project_id || item.project_id === query.project_id) && (!query.environment || item.environment === query.environment) && (!query.status || item.status === query.status))
    const page = query.page ?? 1; const pageSize = query.page_size ?? 25
    return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize }
  },
  async get(id: Id): Promise<Deployment | undefined> {
    if (!useDemoDeployments) { const page = await deploymentsApi.list({ page_size: 100 }); return page.items.find((item) => item.id === id) }
    return deployments.find((item) => item.id === id)
  },
  async create(request: CreateDeploymentRequest, user: UserSummary | null): Promise<Deployment> {
    const actor = requireUser(user)
    if (!useDemoDeployments) return deploymentsApi.create(request)
    const { version, prompt, project } = versionInfo(request.version_id)
    if (!['development', 'staging', 'production'].includes(request.environment)) throw new Error('Select a valid environment.')
    const status: DeploymentStatus = request.environment === 'production' ? 'pending_approval' : 'active'
    if (status === 'active') deployments = deployments.map((item) => item.prompt_id === prompt.id && item.environment === request.environment && item.status === 'active' ? { ...item, status: 'superseded' } : item)
    const item: Deployment = { id: uniqueId('deployment'), project_id: project.id, project_name: project.name, prompt_id: prompt.id, prompt_key: prompt.key, version_id: version.id, version_number: version.version_number, environment: request.environment, status, note: request.note?.trim() || null, requested_by: actor.id, requested_by_name: actor.display_name, reviewed_by: null, reviewed_at: null, review_note: null, created_at: now() }
    deployments = [item, ...deployments]; notify(); auditStore.record('deployment.requested', 'deployment', item.id, actor); return item
  },
  async cancel(id: Id, user: UserSummary | null): Promise<Deployment> {
    const actor = requireUser(user)
    if (!useDemoDeployments) return deploymentsApi.cancel(id)
    const item = deployments.find((entry) => entry.id === id)
    if (!item) throw new Error('Deployment not found.')
    if (item.requested_by !== actor.id) throw new Error('Only the requester can cancel this deployment.')
    if (item.status !== 'pending_approval') throw new Error('Only pending requests can be cancelled.')
    const updated = { ...item, status: 'cancelled' as const }
    deployments = deployments.map((entry) => entry.id === id ? updated : entry); notify(); auditStore.record('deployment.cancelled', 'deployment', id, actor); return updated
  },
  async pending(user: UserSummary | null): Promise<Deployment[]> {
    requireAdmin(user)
    return useDemoDeployments ? deployments.filter((item) => item.status === 'pending_approval') : adminApi.pendingDeployments()
  },
  async review(id: Id, action: 'approve' | 'reject', request: ReviewDeploymentRequest, user: UserSummary | null): Promise<Deployment> {
    const actor = requireAdmin(user)
    if (!useDemoDeployments) return action === 'approve' ? adminApi.approveDeployment(id, request) : adminApi.rejectDeployment(id, request)
    const item = deployments.find((entry) => entry.id === id)
    if (!item) throw new Error('Deployment not found.')
    if (item.status !== 'pending_approval') throw new Error('This request has already been reviewed.')
    if (action === 'reject' && !request.note?.trim()) throw new Error('Add a reason before rejecting.')
    if (action === 'approve') deployments = deployments.map((entry) => entry.prompt_id === item.prompt_id && entry.environment === item.environment && entry.status === 'active' ? { ...entry, status: 'superseded' } : entry)
    const updated: Deployment = { ...item, status: action === 'approve' ? 'active' : 'rejected', reviewed_by: actor.id, reviewed_at: now(), review_note: request.note?.trim() || null }
    deployments = deployments.map((entry) => entry.id === id ? updated : entry); notify(); auditStore.record(action === 'approve' ? 'deployment.approved' : 'deployment.rejected', 'deployment', id, actor); return updated
  },
  async rollback(activeId: Id, targetVersionId: Id, note: string, user: UserSummary | null): Promise<Deployment> {
    const actor = requireAdmin(user)
    if (!note.trim()) throw new Error('A rollback reason is required.')
    if (!useDemoDeployments) return adminApi.rollback(activeId, { target_version_id: targetVersionId, note })
    const active = deployments.find((item) => item.id === activeId)
    const { version } = versionInfo(targetVersionId)
    if (!active || active.status !== 'active') throw new Error('Select an active deployment.')
    if (version.prompt_id !== active.prompt_id || version.id === active.version_id) throw new Error('Select an earlier version of this prompt.')
    deployments = deployments.map((item) => item.id === activeId ? { ...item, status: 'superseded' } : item)
    const item: Deployment = { ...active, id: uniqueId('rollback'), version_id: version.id, version_number: version.version_number, status: 'active', note: note.trim(), requested_by: actor.id, requested_by_name: actor.display_name, reviewed_by: actor.id, reviewed_at: now(), review_note: `Rollback from v${active.version_number}`, created_at: now() }
    deployments = [item, ...deployments]; notify(); auditStore.record('deployment.rolled_back', 'deployment', item.id, actor); return item
  },
}

function generateSecret(): string { const bytes = new Uint8Array(24); crypto.getRandomValues(bytes); return `pv_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}` }
export const tokenService = {
  async list(): Promise<ApiTokenMetadata[]> { return useDemoDeployments ? [...tokens] : apiTokensApi.list() },
  async issue(request: CreateApiTokenRequest, user: UserSummary | null): Promise<CreatedApiToken> {
    const actor = requireUser(user)
    if (!useDemoDeployments) return apiTokensApi.create(request)
    const project = projectStore.find((item) => item.id === request.project_id)
    if (!project || !request.name.trim()) throw new Error('Token name and project are required.')
    const metadata: ApiTokenMetadata = { id: uniqueId('token'), name: request.name.trim(), project_id: project.id, project_name: project.name, created_at: now(), last_used_at: null, revoked_at: null }
    tokens = [metadata, ...tokens]; notify(); auditStore.record('token.issued', 'api_token', metadata.id, actor)
    return { ...metadata, token: generateSecret() }
  },
  async revoke(id: Id, user: UserSummary | null): Promise<void> {
    const actor = requireUser(user)
    if (!useDemoDeployments) return apiTokensApi.revoke(id)
    const token = tokens.find((item) => item.id === id)
    if (!token) throw new Error('Token not found.')
    if (token.revoked_at) throw new Error('This token is already revoked.')
    tokens = tokens.map((item) => item.id === id ? { ...item, revoked_at: now() } : item); notify(); auditStore.record('token.revoked', 'api_token', id, actor)
  },
}
