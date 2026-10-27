import { refreshLiveData } from '../../lib/live-refresh'
import { readAllPages } from '../../lib/api/pagination'
import { adminDeploymentsApi, apiTokensApi, deploymentsApi, type BackendApiToken, type BackendDeployment, type BackendDeploymentDetail, type BackendDeploymentEnvironment, type BackendDeploymentStatus } from './api'
import { projectStore, promptStore, versionStore, adaptVersion } from '../projects/workspace-data'
import type { Id, Page } from '../../types/api'
import type { ApiTokenMetadata, CreateApiTokenRequest, CreatedApiToken, CreateDeploymentRequest, Deployment, DeploymentListQuery, DeploymentStatus, ReviewDeploymentRequest } from '../../types/deployments'
import type { UserSummary } from '../../types/auth'
import { auditStore } from '../admin/audit-store'
import { runService, adaptRun } from '../runs/run-service'
import { useDemoData } from '../../lib/runtime'

const useDemoDeployments = useDemoData
const now = () => new Date().toISOString()
const seed: Deployment[] = [
  { id: 'deployment-pending', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, environment: 'production', status: 'pending_approval', note: 'Add order context to checkout responses.', requested_by: 'usr_demo_user', requested_by_name: 'Jamie Chen', reviewed_by: null, reviewed_at: null, review_note: null, created_at: '2025-08-28T11:00:00Z' },
  { id: 'deployment-production', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v2', version_number: 2, environment: 'production', status: 'active', note: 'Previous stable production version.', requested_by: 'usr_demo_admin', requested_by_name: 'Alex Morgan', reviewed_by: 'usr_demo_admin', reviewed_at: '2025-08-24T12:00:00Z', review_note: 'Approved', created_at: '2025-08-24T11:00:00Z' },
  { id: 'deployment-staging', project_id: 'checkout', project_name: 'Checkout Assistant', prompt_id: 'checkout-reply', prompt_key: 'checkout-reply', version_id: 'checkout-v3', version_number: 3, environment: 'staging', status: 'active', note: 'Staging validation.', requested_by: 'usr_demo_user', requested_by_name: 'Jamie Chen', reviewed_by: null, reviewed_at: null, review_note: null, created_at: '2025-08-28T10:45:00Z' },
]
let deployments = seed
let tokens: ApiTokenMetadata[] = useDemoDeployments ? [
  { id: 'demo-token-checkout-prod', name: 'Checkout production', project_id: 'checkout', project_name: 'Checkout Assistant', token_prefix: 'pv_live_checkout', created_at: '2026-09-18T09:20:00Z', expires_at: null, revoked_at: null },
  { id: 'demo-token-growth-preview', name: 'Growth preview', project_id: 'growth', project_name: 'Growth Tools', token_prefix: 'pv_live_growth', created_at: '2026-09-24T11:10:00Z', expires_at: '2026-12-31T00:00:00Z', revoked_at: null },
  { id: 'demo-token-checkout-legacy', name: 'Legacy checkout client', project_id: 'checkout', project_name: 'Checkout Assistant', token_prefix: 'pv_live_legacy', created_at: '2026-08-12T08:00:00Z', expires_at: null, revoked_at: '2026-09-15T10:00:00Z' },
] : []
let revision = 0
const listeners = new Set<() => void>()
const notify = () => { revision += 1; listeners.forEach((listener) => listener()); refreshLiveData() }
export const deploymentStore = { subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, getSnapshot() { return revision } }

function requireUser(user: UserSummary | null): UserSummary { if (!user) throw new Error('Sign in to continue.'); return user }
function requireReviewer(user: UserSummary | null): UserSummary { const actor = requireUser(user); if (!['admin', 'super_admin'].includes(actor.role)) throw new Error('Admin access is required.'); return actor }
function versionInfo(versionId: Id) {
  const version = Object.values(versionStore).flat().find((item) => item.id === versionId)
  const prompt = promptStore.find((item) => item.id === version?.prompt_id)
  const project = projectStore.find((item) => item.id === prompt?.project_id)
  if (!version || !prompt || !project) throw new Error('Select a valid prompt version.')
  return { version, prompt, project }
}
function uniqueId(prefix: string) { return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }

const toBackendEnvironment = (environment: DeploymentListQuery['environment']): BackendDeploymentEnvironment | undefined =>
  environment === 'development' ? 'dev' : environment === 'production' ? 'prod' : environment
const fromBackendEnvironment = (environment: BackendDeploymentEnvironment): Deployment['environment'] =>
  environment === 'dev' ? 'development' : environment === 'prod' ? 'production' : environment
const toBackendStatus = (status: DeploymentListQuery['status']): BackendDeploymentStatus | undefined =>
  status === 'pending_approval' ? 'pending' : status
const fromBackendStatus = (status: BackendDeploymentStatus): DeploymentStatus =>
  status === 'pending' ? 'pending_approval' : status

export function adaptBackendDeployment(item: BackendDeployment | BackendDeploymentDetail): Deployment {
  return {
    id: item.id,
    validation_id: item.validation_id,
    ...('validation' in item ? { validation: item.validation } : {}),
    project_id: item.project_id,
    project_name: projectStore.find((project) => project.id === item.project_id)?.name ?? item.project_id,
    prompt_id: item.prompt_id,
    prompt_key: item.prompt_key,
    version_id: item.version_id,
    version_number: item.version_number,
    environment: fromBackendEnvironment(item.environment),
    status: fromBackendStatus(item.status),
    note: item.request_note ?? item.rollback_reason,
    requested_by: item.requested_by.id,
    requested_by_name: item.requested_by.display_name,
    reviewed_by: item.reviewed_by?.id ?? null,
    reviewed_at: item.reviewed_at,
    review_note: item.review_note,
    created_at: item.requested_at,
    requested_at: item.requested_at,
    activated_at: item.activated_at,
    rollback_of_id: item.rollback_of_id,
    rollback_reason: item.rollback_reason,
    ...('timeline' in item ? { timeline: item.timeline.map((event) => ({ ...event, status: fromBackendStatus(event.status) })) } : {}),
  }
}

export function adaptBackendToken(item: BackendApiToken, projectName?: string): ApiTokenMetadata {
  return {
    id: item.id,
    name: item.name,
    project_id: item.project_id,
    project_name: projectName ?? projectStore.find((project) => project.id === item.project_id)?.name ?? item.project_id,
    token_prefix: item.token_prefix,
    created_at: item.created_at,
    expires_at: item.expires_at,
    revoked_at: item.revoked_at,
  }
}

export const deploymentService = {
  async rollbackTargets(id: Id, user: UserSummary | null) {
    requireReviewer(user)
    if (useDemoDeployments) {
      const active = deployments.find((item) => item.id === id)
      if (!active || active.status !== 'active' || active.environment !== 'production') throw new Error('Select an active production deployment.')
      return (versionStore[active.prompt_id] ?? []).filter((version) => version.version_number < active.version_number)
    }
    return (await readAllPages((page) => adminDeploymentsApi.rollbackTargets(id, page))).map(adaptVersion)
  },
  async activeProduction(user?: UserSummary | null): Promise<Deployment[]> {
    if (user?.role === 'admin' && !useDemoDeployments) {
      const items = await readAllPages((page) => adminDeploymentsApi.active(page))
      return items.map(adaptBackendDeployment).filter((item) => item.status === 'active' && item.environment === 'production')
    }
    const items = await readAllPages((page) => deploymentService.list({ status: 'active', environment: 'production', page, page_size: 100 }))
    return items.filter((item) => item.status === 'active' && item.environment === 'production')
  },
  async reviewDetail(id: Id, user: UserSummary | null, signal?: AbortSignal) {
    requireReviewer(user)
    if (!useDemoDeployments) {
      const result = await adminDeploymentsApi.reviewDetail(id, signal)
      return {
        deployment: adaptBackendDeployment(result.deployment),
        requested_version: adaptVersion(result.requested_version),
        active_version: result.active_version ? adaptVersion(result.active_version) : null,
        recent_runs: result.recent_runs.map(adaptRun),
        validation: result.validation,
      }
    }
    const deployment = deployments.find((item) => item.id === id)
    if (!deployment) throw new Error('Deployment not found.')
    const requested = versionInfo(deployment.version_id).version
    const active = deployments.find((item) => item.prompt_id === deployment.prompt_id && item.environment === 'production' && item.status === 'active')
    return { deployment, requested_version: requested, active_version: active ? versionInfo(active.version_id).version : null, recent_runs: (await runService.list({ version_id: requested.id, page_size: 5 })).items }
  },
  async list(query: DeploymentListQuery = {}): Promise<Page<Deployment>> {
    if (!useDemoDeployments) {
      const page = await deploymentsApi.list({ ...query, environment: toBackendEnvironment(query.environment), status: toBackendStatus(query.status) })
      return { ...page, items: page.items.map(adaptBackendDeployment) }
    }
    const items = deployments.filter((item) => (!query.project_id || item.project_id === query.project_id) && (!query.environment || item.environment === query.environment) && (!query.status || item.status === query.status))
    const page = query.page ?? 1; const pageSize = query.page_size ?? 25
    return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize }
  },
  async get(id: Id): Promise<Deployment | undefined> {
    if (!useDemoDeployments) return adaptBackendDeployment(await deploymentsApi.get(id))
    return deployments.find((item) => item.id === id)
  },
  async create(request: CreateDeploymentRequest, user: UserSummary | null): Promise<Deployment> {
    const actor = requireUser(user)
    if (!useDemoDeployments) {
      const item = adaptBackendDeployment(await deploymentsApi.create({ version_id: request.version_id, environment: toBackendEnvironment(request.environment)!, request_note: request.note, validation_id: request.validation_id }))
      notify()
      return item
    }
    const { version, prompt, project } = versionInfo(request.version_id)
    if (!['development', 'staging', 'production'].includes(request.environment)) throw new Error('Select a valid environment.')
    const status: DeploymentStatus = request.environment === 'production' ? 'pending_approval' : 'active'
    if (status === 'active') deployments = deployments.map((item) => item.prompt_id === prompt.id && item.environment === request.environment && item.status === 'active' ? { ...item, status: 'superseded' } : item)
    const item: Deployment = { id: uniqueId('deployment'), project_id: project.id, project_name: project.name, prompt_id: prompt.id, prompt_key: prompt.key, version_id: version.id, version_number: version.version_number, environment: request.environment, status, note: request.note?.trim() || null, requested_by: actor.id, requested_by_name: actor.display_name, reviewed_by: null, reviewed_at: null, review_note: null, created_at: now() }
    deployments = [item, ...deployments]; notify(); auditStore.record('deployment.requested', 'deployment', item.id, actor); return item
  },
  async cancel(id: Id, user: UserSummary | null): Promise<Deployment> {
    const actor = requireUser(user)
    if (!useDemoDeployments) {
      const item = adaptBackendDeployment(await deploymentsApi.cancel(id))
      notify()
      return item
    }
    const item = deployments.find((entry) => entry.id === id)
    if (!item) throw new Error('Deployment not found.')
    if (item.requested_by !== actor.id) throw new Error('Only the requester can cancel this deployment.')
    if (item.status !== 'pending_approval') throw new Error('Only pending requests can be cancelled.')
    const updated = { ...item, status: 'cancelled' as const }
    deployments = deployments.map((entry) => entry.id === id ? updated : entry); notify(); auditStore.record('deployment.cancelled', 'deployment', id, actor); return updated
  },
  async pending(user: UserSummary | null): Promise<Deployment[]> {
    requireReviewer(user)
    if (useDemoDeployments) return deployments.filter((item) => item.status === 'pending_approval')
    return (await readAllPages((page) => adminDeploymentsApi.pending(page))).map(adaptBackendDeployment)
  },
  async review(id: Id, action: 'approve' | 'reject', request: ReviewDeploymentRequest, user: UserSummary | null): Promise<Deployment> {
    const actor = requireReviewer(user)
    if (!useDemoDeployments) {
      const result = action === 'approve'
        ? await adminDeploymentsApi.approve(id, request.note)
        : await adminDeploymentsApi.reject(id, request.note ?? '')
      const item = adaptBackendDeployment(result)
      notify()
      return item
    }
    const item = deployments.find((entry) => entry.id === id)
    if (!item) throw new Error('Deployment not found.')
    if (item.status !== 'pending_approval') throw new Error('This request has already been reviewed.')
    if (action === 'reject' && !request.note?.trim()) throw new Error('Add a reason before rejecting.')
    if (action === 'approve') deployments = deployments.map((entry) => entry.prompt_id === item.prompt_id && entry.environment === item.environment && entry.status === 'active' ? { ...entry, status: 'superseded' } : entry)
    const updated: Deployment = { ...item, status: action === 'approve' ? 'active' : 'rejected', reviewed_by: actor.id, reviewed_at: now(), review_note: request.note?.trim() || null }
    deployments = deployments.map((entry) => entry.id === id ? updated : entry); notify(); auditStore.record(action === 'approve' ? 'deployment.approved' : 'deployment.rejected', 'deployment', id, actor); return updated
  },
  async rollback(activeId: Id, targetVersionId: Id, note: string, user: UserSummary | null): Promise<Deployment> {
    const actor = requireReviewer(user)
    if (!note.trim()) throw new Error('A rollback reason is required.')
    if (!useDemoDeployments) {
      const active = user?.role === 'admin' ? (await adminDeploymentsApi.reviewDetail(activeId)).deployment : await deploymentsApi.get(activeId)
      if (active.environment !== 'prod') throw new Error('Rollback is supported only for production deployments.')
      if (active.status !== 'active') throw new Error('This deployment is no longer active. Refresh and select the current production deployment.')
      const item = adaptBackendDeployment(await adminDeploymentsApi.rollback(active.prompt_id, targetVersionId, note))
      notify()
      return item
    }
    const active = deployments.find((item) => item.id === activeId)
    const { version } = versionInfo(targetVersionId)
    if (!active || active.status !== 'active') throw new Error('Select an active deployment.')
    if (active.environment !== 'production') throw new Error('Rollback is supported only for production deployments.')
    if (version.prompt_id !== active.prompt_id || version.version_number >= active.version_number) throw new Error('Select an earlier version of this prompt.')
    deployments = deployments.map((item) => item.id === activeId ? { ...item, status: 'rolled_back' } : item)
    const item: Deployment = { ...active, id: uniqueId('rollback'), version_id: version.id, version_number: version.version_number, status: 'active', note: note.trim(), requested_by: actor.id, requested_by_name: actor.display_name, reviewed_by: actor.id, reviewed_at: now(), review_note: `Rollback from v${active.version_number}`, rollback_of_id: active.id, rollback_reason: note.trim(), activated_at: now(), requested_at: now(), created_at: now() }
    deployments = [item, ...deployments]; notify(); auditStore.record('deployment.rolled_back', 'deployment', item.id, actor); return item
  },
}

function generateSecret(): string { const bytes = new Uint8Array(24); crypto.getRandomValues(bytes); return `pv_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}` }
export const tokenService = {
  async list(): Promise<ApiTokenMetadata[]> { return useDemoDeployments ? [...tokens] : (await readAllPages((page) => apiTokensApi.list(page))).map((item) => adaptBackendToken(item)) },
  async issue(request: CreateApiTokenRequest, user: UserSummary | null): Promise<CreatedApiToken> {
    const actor = requireUser(user)
    if (!useDemoDeployments) {
      const result = await apiTokensApi.create(request)
      notify()
      return { ...adaptBackendToken(result), token: result.token }
    }
    const project = projectStore.find((item) => item.id === request.project_id)
    if (!project || !request.name.trim()) throw new Error('Token name and project are required.')
    const token = generateSecret()
    const metadata: ApiTokenMetadata = { id: uniqueId('token'), name: request.name.trim(), project_id: project.id, project_name: project.name, token_prefix: token.slice(0, 20), created_at: now(), expires_at: request.expires_at ?? null, revoked_at: null }
    tokens = [metadata, ...tokens]; notify(); auditStore.record('token.issued', 'api_token', metadata.id, actor)
    return { ...metadata, token }
  },
  async revoke(id: Id, user: UserSummary | null): Promise<void> {
    const actor = requireUser(user)
    if (!useDemoDeployments) { await apiTokensApi.revoke(id); notify(); return }
    const token = tokens.find((item) => item.id === id)
    if (!token) throw new Error('Token not found.')
    if (token.revoked_at) throw new Error('This token is already revoked.')
    tokens = tokens.map((item) => item.id === id ? { ...item, revoked_at: now() } : item); notify(); auditStore.record('token.revoked', 'api_token', id, actor)
  },
}
