import { adminApi, type BackendAdminDashboard, type BackendAdminUser, type BackendAuditEvent, type BackendBudget, type BackendMaintenanceStatus, type BackendModelPricing, type BackendProviderKey } from './api'
import { auditStore } from './audit-store'
import { budgetStore } from './budget-store'
import { deploymentService } from '../deployments/deployment-service'
import { adaptRun, runStore } from '../runs/run-service'
import type { BackendPromptRun } from '../runs/api'
import { sampleUserProfiles } from '../../mocks/users'
import { projectStore } from '../projects/workspace-data'
import type { Page } from '../../types/api'
import type { AdminRunListQuery, AdminUser, AuditEvent, AuditListQuery, Budget, CreateModelPriceRequest, CreateProviderKeyRequest, MaintenanceStatus, ModelPrice, OrganizationDashboard, ProviderKeyMetadata, UpdateUserRequest, UpsertBudgetRequest } from '../../types/admin'
import type { UserSummary } from '../../types/auth'
import type { PromptRun } from '../../types/runs'
import { useDemoData } from '../../lib/runtime'

const demo = useDemoData
const now = () => new Date().toISOString()
const id = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
let revision = 0
const listeners = new Set<() => void>()
const notify = () => { revision += 1; listeners.forEach((listener) => listener()) }
export const adminStore = { subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, getSnapshot() { return revision } }
export const isDemoAdmin = demo

let users: AdminUser[] = [
  ...sampleUserProfiles.map((user) => ({ id: user.id, email: user.email, display_name: user.display_name, role: user.role, is_active: user.is_active, created_at: user.created_at, project_count: user.role === 'super_admin' ? 3 : 1, last_active_at: now() })),
  { id: 'usr_riley', email: 'riley@promptvault.dev', display_name: 'Riley Park', role: 'user', is_active: true, created_at: '2025-02-10T09:00:00Z', project_count: 2, last_active_at: '2025-08-27T10:00:00Z' },
  { id: 'usr_taylor', email: 'taylor@promptvault.dev', display_name: 'Taylor Reed', role: 'user', is_active: false, created_at: '2025-03-10T09:00:00Z', project_count: 1, last_active_at: '2025-08-20T10:00:00Z' },
]
let providerKeys: ProviderKeyMetadata[] = [{ id: 'provider-key-demo', provider: 'gemini', label: 'Primary sandbox key', created_at: '2025-08-18T09:00:00Z', deactivated_at: null }]
let modelPrices: ModelPrice[] = [
  { id: 'price-input', provider: 'gemini', model: 'gemini-2.0-flash', token_type: 'input', price_per_million_tokens: '0.100000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
  { id: 'price-output', provider: 'gemini', model: 'gemini-2.0-flash', token_type: 'output', price_per_million_tokens: '0.400000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
  { id: 'price-mock', provider: 'gemini', model: 'gemini-3.5-flash-lite', token_type: 'combined', price_per_million_tokens: '10.000000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
]
let refreshedAt: string | null = null

function requireAdmin(actor: UserSummary | null): UserSummary { if (!actor || actor.role !== 'super_admin' || !actor.is_active) throw new Error('Super Admin access is required.'); return actor }
function pageOf<T>(items: T[], page = 1, pageSize = 25): Page<T> { return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize } }
function monthSpend(runs: PromptRun[], target: 'user' | 'project', targetId: string) { const month = now().slice(0, 7); return runs.filter((run) => run.status === 'completed' && run.created_at.startsWith(month) && (target === 'user' ? run.user_id : run.project_id) === targetId).reduce((total, run) => total + Number(run.cost), 0) }
function record(action: string, resource: string, resourceId: string, actor: UserSummary) { auditStore.record(action, resource, resourceId, actor); notify() }

async function fetchAllPages<T>(load: (query: { page: number; page_size: number }) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = []
  let page = 1
  while (true) {
    const result = await load({ page, page_size: 100 })
    items.push(...result.items)
    if (items.length >= result.total || result.items.length === 0) return items
    page += 1
  }
}

export async function listAllAdminUsers(actor: UserSummary | null): Promise<AdminUser[]> {
  return fetchAllPages((query) => adminService.listUsers(query, actor))
}

export async function fetchAllAdminRuns(
  load: (query: AdminRunListQuery) => Promise<Page<BackendPromptRun>> = adminApi.listRuns,
): Promise<BackendPromptRun[]> {
  const items: BackendPromptRun[] = []
  let page = 1
  while (true) {
    const result = await load({ page, page_size: 100 })
    items.push(...result.items)
    if (items.length >= result.total || result.items.length === 0) return items
    page += 1
  }
}

export function adaptAdminUser(item: BackendAdminUser): AdminUser {
  return {
    id: item.id,
    email: item.email,
    display_name: item.display_name,
    role: item.role === 'admin' ? 'super_admin' : 'user',
    is_active: item.is_active,
    created_at: item.created_at,
    project_count: item.project_count,
    last_active_at: item.updated_at,
  }
}

export function adaptAdminDashboard(item: BackendAdminDashboard): OrganizationDashboard {
  const total = Number(item.total_spend)
  return {
    monthly_spend: item.total_spend,
    run_count: item.run_count,
    active_user_count: item.active_user_count,
    pending_approval_count: item.pending_approval_count,
    spend_by_model: item.spend_by_model.map((row) => ({
      model: row.model,
      cost: row.cost,
      percentage: total > 0 ? Math.round(Number(row.cost) / total * 100) : 0,
    })),
  }
}

function adaptProviderKey(item: BackendProviderKey): ProviderKeyMetadata {
  return { id: item.id, provider: item.provider, label: item.alias, created_at: item.created_at, deactivated_at: item.deactivated_at }
}

export function adaptModelPricing(item: BackendModelPricing): ModelPrice[] {
  const shared = { provider: item.provider, model: item.model, effective_from: item.effective_from, effective_to: item.effective_to }
  return [
    { ...shared, id: `${item.id}:input`, token_type: 'input', price_per_million_tokens: item.input_price_per_million },
    { ...shared, id: `${item.id}:output`, token_type: 'output', price_per_million_tokens: item.output_price_per_million },
  ]
}

export function toBackendModelPricingRequest(request: CreateModelPriceRequest) {
  return {
    provider: request.provider.trim(),
    model: request.model.trim(),
    input_price_per_million: request.input_price_per_million,
    output_price_per_million: request.output_price_per_million,
    effective_from: request.effective_from,
  }
}

function adaptAudit(item: BackendAuditEvent, actorName?: string): AuditEvent {
  return {
    id: String(item.id),
    actor_id: item.actor_user_id,
    actor_name: actorName ?? null,
    action: item.action,
    resource_type: item.entity_type,
    resource_id: item.entity_id,
    request_id: item.request_id,
    created_at: item.created_at,
  }
}

export function adaptMaintenance(item: BackendMaintenanceStatus): MaintenanceStatus {
  const refreshes = item.materialized_views.map((view) => view.refreshed_through).filter((value): value is string => Boolean(value)).sort()
  const databaseStatus: MaintenanceStatus['database_status'] = item.database === 'healthy' ? 'healthy' : item.database === 'degraded' ? 'degraded' : 'unavailable'
  return {
    api_status: 'healthy',
    database_status: databaseStatus,
    partition_count: item.run_partitions.length,
    last_view_refresh_at: refreshes.length ? refreshes[refreshes.length - 1] : null,
  }
}

function adaptBudget(item: BackendBudget, targetName: string, spend = 0): Budget {
  const targetType = item.user_id ? 'user' : 'project'
  const start = new Date(); start.setUTCDate(1); start.setUTCHours(0, 0, 0, 0)
  const end = new Date(start); end.setUTCMonth(end.getUTCMonth() + 1)
  return {
    id: item.id,
    target_type: targetType,
    target_id: item.user_id ?? item.project_id!,
    target_name: targetName,
    monthly_limit: item.monthly_limit,
    monthly_spend: spend.toFixed(6),
    period_start: start.toISOString(),
    period_end: end.toISOString(),
  }
}

export const adminService = {
  async dashboard(actor: UserSummary | null): Promise<OrganizationDashboard> {
    requireAdmin(actor)
    if (!demo) return adaptAdminDashboard(await adminApi.dashboard())
    const runs = runStore.getRuns(); const monthRuns = runs.filter((run) => run.created_at.startsWith(now().slice(0, 7))); const total = monthRuns.reduce((sum, run) => sum + Number(run.cost), 0)
    const grouped = new Map<string, number>()
    monthRuns.forEach((run) => grouped.set(run.model, (grouped.get(run.model) ?? 0) + Number(run.cost)))
    const pending = await deploymentService.pending(actor)
    return { monthly_spend: total.toFixed(4), run_count: runs.length, active_user_count: users.filter((user) => user.is_active).length, pending_approval_count: pending.length, spend_by_model: [...grouped].map(([model, cost]) => ({ model, cost: cost.toFixed(4), percentage: total ? Math.round(cost / total * 100) : 0 })) }
  },
  async listRuns(query: AdminRunListQuery = {}, actor: UserSummary | null): Promise<Page<PromptRun>> {
    requireAdmin(actor)
    if (!demo) { const page = await adminApi.listRuns(query); return { ...page, items: page.items.map(adaptRun) } }
    const search = query.search?.trim().toLowerCase()
    const rows = runStore.getRuns().filter((run) => (!search || `${run.prompt_key} ${run.id}`.toLowerCase().includes(search)) && (!query.user_id || run.user_id === query.user_id) && (!query.project_id || run.project_id === query.project_id) && (!query.status || run.status === query.status) && (!query.from || run.created_at >= query.from) && (!query.to || run.created_at <= query.to))
    return pageOf(rows, query.page, query.page_size)
  },
  async listUsers(query: { page?: number; page_size?: number; search?: string; role?: string; is_active?: boolean } = {}, actor: UserSummary | null): Promise<Page<AdminUser>> {
    requireAdmin(actor)
    if (!demo) {
      const role = query.role === 'super_admin' ? 'admin' : query.role === 'user' ? 'user' : undefined
      const page = await adminApi.listUsers({ ...query, role })
      return { ...page, items: page.items.map(adaptAdminUser) }
    }
    const items = users.filter((user) => (!query.search || `${user.display_name} ${user.email}`.toLowerCase().includes(query.search.toLowerCase())) && (!query.role || user.role === query.role) && (query.is_active === undefined || user.is_active === query.is_active))
    return pageOf(items, query.page, query.page_size)
  },
  async updateUser(userId: string, request: UpdateUserRequest, actor: UserSummary | null): Promise<AdminUser> {
    const admin = requireAdmin(actor)
    if (!demo) {
      const updated = adaptAdminUser(await adminApi.updateUser(userId, { ...request, role: request.role === 'super_admin' ? 'admin' : request.role }))
      notify()
      return updated
    }
    const current = users.find((user) => user.id === userId)
    if (!current) throw new Error('User not found.')
    const updated = { ...current, ...request }
    if (current.role === 'super_admin' && updated.role === 'user' && current.id !== admin.id) throw new Error('A Super Admin cannot change another Super Admin to User.')
    if (current.role === 'super_admin' && current.is_active && (updated.role !== 'super_admin' || !updated.is_active) && !users.some((item) => item.id !== userId && item.role === 'super_admin' && item.is_active)) throw new Error('The last active Super Admin cannot be changed.')
    users = users.map((user) => user.id === userId ? updated : user)
    record('user.updated', 'user', userId, admin)
    return updated
  },
  async listProviderKeys(actor: UserSummary | null): Promise<ProviderKeyMetadata[]> { requireAdmin(actor); return demo ? [...providerKeys] : (await fetchAllPages(adminApi.listProviderKeys)).map(adaptProviderKey) },
  async addProviderKey(request: CreateProviderKeyRequest, actor: UserSummary | null): Promise<ProviderKeyMetadata> {
    const admin = requireAdmin(actor)
    if (!request.provider.trim() || !request.label.trim() || !request.secret.trim()) throw new Error('Provider, label, and secret are required.')
    if (!demo) {
      const item = adaptProviderKey(await adminApi.createProviderKey({ provider: request.provider, alias: request.label, secret: request.secret }))
      notify()
      return item
    }
    const item: ProviderKeyMetadata = { id: id('provider-key'), provider: request.provider.trim(), label: request.label.trim(), created_at: now(), deactivated_at: null }
    providerKeys = [item, ...providerKeys]; record('provider_key.created', 'provider_key', item.id, admin); return item
  },
  async deactivateProviderKey(keyId: string, actor: UserSummary | null): Promise<ProviderKeyMetadata> {
    const admin = requireAdmin(actor)
    if (!demo) {
      const current = (await fetchAllPages(adminApi.listProviderKeys)).find((item) => item.id === keyId)
      await adminApi.deactivateProviderKey(keyId)
      notify()
      if (!current) throw new Error('Active provider key not found.')
      return adaptProviderKey({ ...current, deactivated_at: now() })
    }
    const key = providerKeys.find((item) => item.id === keyId)
    if (!key || key.deactivated_at) throw new Error('Active provider key not found.')
    const updated = { ...key, deactivated_at: now() }
    providerKeys = providerKeys.map((item) => item.id === keyId ? updated : item); record('provider_key.deactivated', 'provider_key', keyId, admin); return updated
  },
  async listBudgets(actor: UserSummary | null): Promise<Budget[]> {
    requireAdmin(actor)
    if (!demo) {
      const [budgets, adminUsers, runs] = await Promise.all([
        fetchAllPages(adminApi.listBudgets),
        fetchAllPages(adminApi.listUsers),
        fetchAllAdminRuns(),
      ])
      const userNames = new Map(adminUsers.map((item) => [item.id, item.display_name]))
      const month = now().slice(0, 7)
      return budgets.map((item) => {
        const targetId = item.user_id ?? item.project_id!
        const spend = runs
          .filter((run) => run.status === 'completed' && run.created_at.startsWith(month) && (item.user_id ? run.user_id === targetId : run.project_id === targetId))
          .reduce((total, run) => total + Number(run.cost), 0)
        const targetName = item.user_id
          ? userNames.get(item.user_id) ?? item.user_id
          : projectStore.find((project) => project.id === item.project_id)?.name ?? item.project_id!
        return adaptBudget(item, targetName, spend)
      })
    }
    const runs = runStore.getRuns()
    return budgetStore.getBudgets().map((item) => ({ ...item, monthly_spend: monthSpend(runs, item.target_type, item.target_id).toFixed(4) }))
  },
  async upsertBudget(request: UpsertBudgetRequest, actor: UserSummary | null): Promise<Budget> {
    const admin = requireAdmin(actor)
    const amount = Number(request.monthly_limit)
    if (!request.monthly_limit.trim() || !Number.isFinite(amount) || amount < 0) throw new Error('Enter a valid non-negative monthly limit.')
    if (!demo) {
      const budgets = await fetchAllPages(adminApi.listBudgets)
      const existing = budgets.find((item) => request.target_type === 'user' ? item.user_id === request.target_id : item.project_id === request.target_id)
      const payload = { monthly_limit: request.monthly_limit, timezone: 'UTC' }
      const result = existing
        ? await adminApi.updateBudget(existing.id, payload)
        : await adminApi.createBudget({ ...payload, ...(request.target_type === 'user' ? { user_id: request.target_id } : { project_id: request.target_id }) })
      const targetName = request.target_type === 'user'
        ? (await fetchAllPages(adminApi.listUsers)).find((item) => item.id === request.target_id)?.display_name ?? request.target_id
        : projectStore.find((project) => project.id === request.target_id)?.name ?? request.target_id
      notify()
      return adaptBudget(result, targetName)
    }
    const target = request.target_type === 'user' ? users.find((user) => user.id === request.target_id) : projectStore.find((project) => project.id === request.target_id)
    if (!target) throw new Error('Select a valid budget target.')
    const previous = budgetStore.getBudgets().find((item) => item.target_type === request.target_type && item.target_id === request.target_id)
    const item: Budget = { id: previous?.id ?? id('budget'), target_type: request.target_type, target_id: request.target_id, target_name: request.target_type === 'user' ? (target as AdminUser).display_name : (target as typeof projectStore[number]).name, monthly_limit: amount.toFixed(4), monthly_spend: monthSpend(runStore.getRuns(), request.target_type, request.target_id).toFixed(4), period_start: previous?.period_start ?? new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString(), period_end: previous?.period_end ?? new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1).toISOString() }
    budgetStore.upsert(item); record('budget.updated', 'budget', item.id, admin); return item
  },
  async listModelPrices(actor: UserSummary | null): Promise<ModelPrice[]> { requireAdmin(actor); return demo ? [...modelPrices] : (await fetchAllPages(adminApi.listModelPrices)).flatMap(adaptModelPricing) },
  async addModelPrice(request: CreateModelPriceRequest, actor: UserSummary | null): Promise<ModelPrice[]> {
    const admin = requireAdmin(actor)
    const prices = [request.input_price_per_million, request.output_price_per_million]
    if (!request.provider.trim() || !request.model.trim() || prices.some((price) => !price.trim() || !Number.isFinite(Number(price)) || Number(price) < 0) || Number.isNaN(Date.parse(request.effective_from))) throw new Error('Enter a provider, model, non-negative input and output prices, and valid effective date.')
    if (!demo) {
      const rows = adaptModelPricing(await adminApi.createModelPrice(toBackendModelPricingRequest(request)))
      notify()
      return rows
    }
    const provider = request.provider.trim()
    const model = request.model.trim()
    const sameModel = modelPrices.filter((price) => price.provider === provider && price.model === model)
    if (sameModel.some((price) => price.effective_from === request.effective_from)) throw new Error('A price already starts on that date for this model.')
    const items: ModelPrice[] = (['input', 'output'] as const).map((tokenType) => {
      const sameSeries = sameModel.filter((price) => price.token_type === tokenType)
      const next = sameSeries.filter((price) => price.effective_from > request.effective_from).sort((a, b) => a.effective_from.localeCompare(b.effective_from))[0]
      return { id: id('price'), provider, model, token_type: tokenType, price_per_million_tokens: Number(tokenType === 'input' ? request.input_price_per_million : request.output_price_per_million).toFixed(6), effective_from: request.effective_from, effective_to: next?.effective_from ?? null }
    })
    const previousIds = new Set((['input', 'output'] as const).flatMap((tokenType) => sameModel.filter((price) => price.token_type === tokenType && price.effective_from < request.effective_from).sort((a, b) => b.effective_from.localeCompare(a.effective_from)).slice(0, 1).map((price) => price.id)))
    modelPrices = [...items, ...modelPrices.map((price) => previousIds.has(price.id) ? { ...price, effective_to: request.effective_from } : price)]
    record('model_price.created', 'model_price', items[0].id, admin)
    return items
  },
  async listAudit(query: AuditListQuery = {}, actor: UserSummary | null): Promise<Page<AuditEvent>> {
    requireAdmin(actor)
    if (!demo) {
      const [page, adminUsers] = await Promise.all([adminApi.listAudit(query), fetchAllPages(adminApi.listUsers)])
      const names = new Map(adminUsers.map((item) => [item.id, item.display_name]))
      return { ...page, items: page.items.map((item) => adaptAudit(item, item.actor_user_id ? names.get(item.actor_user_id) : undefined)) }
    }
    const rows = auditStore.getEvents().filter((event) => (!query.action || event.action.startsWith(query.action)) && (!query.actor_id || event.actor_id === query.actor_id) && (!query.from || event.created_at >= query.from) && (!query.to || event.created_at <= query.to))
    return pageOf(rows, query.page, query.page_size)
  },
  async maintenance(actor: UserSummary | null): Promise<MaintenanceStatus> { requireAdmin(actor); return demo ? { api_status: 'unavailable', database_status: 'unavailable', partition_count: 0, last_view_refresh_at: refreshedAt } : adaptMaintenance(await adminApi.maintenanceStatus()) },
  async refreshViews(actor: UserSummary | null): Promise<MaintenanceStatus> { const admin = requireAdmin(actor); if (!demo) { await adminApi.refreshViews(); notify(); return this.maintenance(actor) } refreshedAt = now(); record('maintenance.views_refreshed', 'maintenance', 'views', admin); return this.maintenance(actor) },
}
