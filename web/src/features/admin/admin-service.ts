import { adminApi } from './api'
import { auditStore } from './audit-store'
import { budgetStore } from './budget-store'
import { deploymentService } from '../deployments/deployment-service'
import { runStore } from '../runs/run-service'
import { demoUsers } from '../../mocks/users'
import { projectStore } from '../projects/workspace-data'
import type { Page } from '../../types/api'
import type { AdminRunListQuery, AdminUser, AuditEvent, AuditListQuery, Budget, CreateModelPriceRequest, CreateProviderKeyRequest, MaintenanceStatus, ModelPrice, OrganizationDashboard, ProviderKeyMetadata, UpdateUserRequest, UpsertBudgetRequest } from '../../types/admin'
import type { UserSummary } from '../../types/auth'
import type { PromptRun } from '../../types/runs'

const demo = import.meta.env.VITE_USE_MOCK_ADMIN !== 'false'
const now = () => new Date().toISOString()
const id = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
let revision = 0
const listeners = new Set<() => void>()
const notify = () => { revision += 1; listeners.forEach((listener) => listener()) }
export const adminStore = { subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }, getSnapshot() { return revision } }
export const isDemoAdmin = demo

let users: AdminUser[] = [
  ...demoUsers.map((user) => ({ id: user.id, email: user.email, display_name: user.display_name, role: user.role, is_active: user.is_active, created_at: user.created_at, project_count: user.role === 'super_admin' ? 3 : 1, last_active_at: now() })),
  { id: 'usr_riley', email: 'riley@promptvault.dev', display_name: 'Riley Park', role: 'user', is_active: true, created_at: '2025-02-10T09:00:00Z', project_count: 2, last_active_at: '2025-08-27T10:00:00Z' },
  { id: 'usr_taylor', email: 'taylor@promptvault.dev', display_name: 'Taylor Reed', role: 'user', is_active: false, created_at: '2025-03-10T09:00:00Z', project_count: 1, last_active_at: '2025-08-20T10:00:00Z' },
]
let providerKeys: ProviderKeyMetadata[] = [{ id: 'provider-key-demo', provider: 'gemini', label: 'Primary sandbox key', created_at: '2025-08-18T09:00:00Z', deactivated_at: null }]
let modelPrices: ModelPrice[] = [
  { id: 'price-input', provider: 'gemini', model: 'gemini-2.0-flash', token_type: 'input', price_per_million_tokens: '0.100000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
  { id: 'price-output', provider: 'gemini', model: 'gemini-2.0-flash', token_type: 'output', price_per_million_tokens: '0.400000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
  { id: 'price-mock', provider: 'mock', model: 'gpt-4o-mini', token_type: 'combined', price_per_million_tokens: '10.000000', effective_from: '2025-08-01T00:00:00Z', effective_to: null },
]
let refreshedAt: string | null = null

function requireAdmin(actor: UserSummary | null): UserSummary { if (!actor || actor.role !== 'super_admin' || !actor.is_active) throw new Error('Super Admin access is required.'); return actor }
function pageOf<T>(items: T[], page = 1, pageSize = 25): Page<T> { return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize } }
function monthSpend(runs: PromptRun[], target: 'user' | 'project', targetId: string) { const month = now().slice(0, 7); return runs.filter((run) => run.status === 'completed' && run.created_at.startsWith(month) && (target === 'user' ? run.user_id : run.project_id) === targetId).reduce((total, run) => total + Number(run.cost), 0) }
function record(action: string, resource: string, resourceId: string, actor: UserSummary) { auditStore.record(action, resource, resourceId, actor); notify() }

export const adminService = {
  async dashboard(actor: UserSummary | null): Promise<OrganizationDashboard> {
    requireAdmin(actor)
    if (!demo) return adminApi.dashboard()
    const runs = runStore.getRuns(); const monthRuns = runs.filter((run) => run.created_at.startsWith(now().slice(0, 7))); const total = monthRuns.reduce((sum, run) => sum + Number(run.cost), 0)
    const grouped = new Map<string, number>()
    monthRuns.forEach((run) => grouped.set(run.model, (grouped.get(run.model) ?? 0) + Number(run.cost)))
    const pending = await deploymentService.pending(actor)
    return { monthly_spend: total.toFixed(4), run_count: runs.length, active_user_count: users.filter((user) => user.is_active).length, pending_approval_count: pending.length, spend_by_model: [...grouped].map(([model, cost]) => ({ model, cost: cost.toFixed(4), percentage: total ? Math.round(cost / total * 100) : 0 })) }
  },
  async listRuns(query: AdminRunListQuery = {}, actor: UserSummary | null): Promise<Page<PromptRun>> {
    requireAdmin(actor)
    if (!demo) return adminApi.listRuns(query)
    const rows = runStore.getRuns().filter((run) => (!query.user_id || run.user_id === query.user_id) && (!query.project_id || run.project_id === query.project_id) && (!query.status || run.status === query.status) && (!query.from || run.created_at >= query.from) && (!query.to || run.created_at <= query.to))
    return pageOf(rows, query.page, query.page_size)
  },
  async listUsers(query: { page?: number; page_size?: number; search?: string; role?: string; is_active?: boolean } = {}, actor: UserSummary | null): Promise<Page<AdminUser>> {
    requireAdmin(actor)
    if (!demo) return adminApi.listUsers(query)
    const items = users.filter((user) => (!query.search || `${user.display_name} ${user.email}`.toLowerCase().includes(query.search.toLowerCase())) && (!query.role || user.role === query.role) && (query.is_active === undefined || user.is_active === query.is_active))
    return pageOf(items, query.page, query.page_size)
  },
  async updateUser(userId: string, request: UpdateUserRequest, actor: UserSummary | null): Promise<AdminUser> {
    const admin = requireAdmin(actor)
    if (userId === admin.id && (request.role === 'user' || request.is_active === false)) throw new Error('You cannot remove your own Super Admin access or deactivate your account.')
    if (!demo) return adminApi.updateUser(userId, request)
    const current = users.find((user) => user.id === userId)
    if (!current) throw new Error('User not found.')
    const updated = { ...current, ...request }
    users = users.map((user) => user.id === userId ? updated : user)
    const loginUser = demoUsers.find((user) => user.id === userId)
    if (loginUser) { loginUser.role = updated.role; loginUser.is_active = updated.is_active }
    record('user.updated', 'user', userId, admin)
    return updated
  },
  async listProviderKeys(actor: UserSummary | null): Promise<ProviderKeyMetadata[]> { requireAdmin(actor); return demo ? [...providerKeys] : adminApi.listProviderKeys() },
  async addProviderKey(request: CreateProviderKeyRequest, actor: UserSummary | null): Promise<ProviderKeyMetadata> {
    const admin = requireAdmin(actor)
    if (!request.provider.trim() || !request.label.trim() || !request.secret.trim()) throw new Error('Provider, label, and secret are required.')
    if (!demo) return adminApi.createProviderKey(request)
    const item: ProviderKeyMetadata = { id: id('provider-key'), provider: request.provider.trim(), label: request.label.trim(), created_at: now(), deactivated_at: null }
    providerKeys = [item, ...providerKeys]; record('provider_key.created', 'provider_key', item.id, admin); return item
  },
  async deactivateProviderKey(keyId: string, actor: UserSummary | null): Promise<ProviderKeyMetadata> {
    const admin = requireAdmin(actor)
    if (!demo) return adminApi.deactivateProviderKey(keyId)
    const key = providerKeys.find((item) => item.id === keyId)
    if (!key || key.deactivated_at) throw new Error('Active provider key not found.')
    const updated = { ...key, deactivated_at: now() }
    providerKeys = providerKeys.map((item) => item.id === keyId ? updated : item); record('provider_key.deactivated', 'provider_key', keyId, admin); return updated
  },
  async listBudgets(actor: UserSummary | null): Promise<Budget[]> {
    requireAdmin(actor)
    if (!demo) return adminApi.listBudgets()
    const runs = runStore.getRuns()
    return budgetStore.getBudgets().map((item) => ({ ...item, monthly_spend: monthSpend(runs, item.target_type, item.target_id).toFixed(4) }))
  },
  async upsertBudget(request: UpsertBudgetRequest, actor: UserSummary | null): Promise<Budget> {
    const admin = requireAdmin(actor)
    const amount = Number(request.monthly_limit)
    if (!request.monthly_limit.trim() || !Number.isFinite(amount) || amount < 0) throw new Error('Enter a valid non-negative monthly limit.')
    if (!demo) return adminApi.upsertBudget(request)
    const target = request.target_type === 'user' ? users.find((user) => user.id === request.target_id) : projectStore.find((project) => project.id === request.target_id)
    if (!target) throw new Error('Select a valid budget target.')
    const previous = budgetStore.getBudgets().find((item) => item.target_type === request.target_type && item.target_id === request.target_id)
    const item: Budget = { id: previous?.id ?? id('budget'), target_type: request.target_type, target_id: request.target_id, target_name: request.target_type === 'user' ? (target as AdminUser).display_name : (target as typeof projectStore[number]).name, monthly_limit: amount.toFixed(4), monthly_spend: monthSpend(runStore.getRuns(), request.target_type, request.target_id).toFixed(4), period_start: previous?.period_start ?? new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString(), period_end: previous?.period_end ?? new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1).toISOString() }
    budgetStore.upsert(item); record('budget.updated', 'budget', item.id, admin); return item
  },
  async listModelPrices(actor: UserSummary | null): Promise<ModelPrice[]> { requireAdmin(actor); return demo ? [...modelPrices] : adminApi.listModelPrices() },
  async addModelPrice(request: CreateModelPriceRequest, actor: UserSummary | null): Promise<ModelPrice> {
    const admin = requireAdmin(actor)
    if (!request.provider.trim() || !request.model.trim() || !request.price_per_million_tokens.trim() || !Number.isFinite(Number(request.price_per_million_tokens)) || Number(request.price_per_million_tokens) < 0 || Number.isNaN(Date.parse(request.effective_from))) throw new Error('Enter a provider, model, non-negative price, and valid effective date.')
    if (!demo) return adminApi.createModelPrice(request)
    const sameSeries = modelPrices.filter((price) => price.provider === request.provider.trim() && price.model === request.model.trim() && price.token_type === request.token_type)
    if (sameSeries.some((price) => price.effective_from === request.effective_from)) throw new Error('A price already starts on that date for this model and token type.')
    const next = sameSeries.filter((price) => price.effective_from > request.effective_from).sort((a, b) => a.effective_from.localeCompare(b.effective_from))[0]
    const previous = sameSeries.filter((price) => price.effective_from < request.effective_from).sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0]
    const item: ModelPrice = { id: id('price'), provider: request.provider.trim(), model: request.model.trim(), token_type: request.token_type, price_per_million_tokens: Number(request.price_per_million_tokens).toFixed(6), effective_from: request.effective_from, effective_to: next?.effective_from ?? null }
    modelPrices = [item, ...modelPrices.map((price) => price.id === previous?.id ? { ...price, effective_to: item.effective_from } : price)]; record('model_price.created', 'model_price', item.id, admin); return item
  },
  async listAudit(query: AuditListQuery = {}, actor: UserSummary | null): Promise<Page<AuditEvent>> {
    requireAdmin(actor)
    if (!demo) return adminApi.listAudit(query)
    const rows = auditStore.getEvents().filter((event) => (!query.action || event.action.startsWith(query.action)) && (!query.actor_id || event.actor_id === query.actor_id) && (!query.from || event.created_at >= query.from) && (!query.to || event.created_at <= query.to))
    return pageOf(rows, query.page, query.page_size)
  },
  async maintenance(actor: UserSummary | null): Promise<MaintenanceStatus> { requireAdmin(actor); return demo ? { api_status: 'unavailable', database_status: 'unavailable', partition_count: 0, last_view_refresh_at: refreshedAt } : adminApi.maintenanceStatus() },
  async refreshViews(actor: UserSummary | null): Promise<MaintenanceStatus> { const admin = requireAdmin(actor); if (!demo) return adminApi.refreshViews(); refreshedAt = now(); record('maintenance.views_refreshed', 'maintenance', 'views', admin); return this.maintenance(actor) },
}
