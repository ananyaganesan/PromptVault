import { describe, expect, it } from 'vitest'
import { sampleUserProfiles } from '../../mocks/users'
import { runService } from '../runs/run-service'
import { adminService } from './admin-service'

const admin = sampleUserProfiles[1]

describe('admin governance prototype', () => {
  it('reconciles dashboard totals with recorded runs', async () => {
    const runs = await adminService.listRuns({ page_size: 100 }, admin)
    const dashboard = await adminService.dashboard(admin)
    expect(dashboard.run_count).toBe(runs.total)
    expect(Number(dashboard.monthly_spend)).toBeCloseTo(runs.items.filter((run) => run.created_at.startsWith(new Date().toISOString().slice(0, 7))).reduce((sum, run) => sum + Number(run.cost), 0), 4)
  })

  it('allows a Super Admin to change their own access when another remains active', async () => {
    await expect(adminService.updateUser(admin.id, { role: 'user' }, admin)).rejects.toThrow('last active Super Admin')
    const secondAdmin = { ...sampleUserProfiles[0], role: 'super_admin' as const }
    await adminService.updateUser(secondAdmin.id, { role: 'super_admin' }, admin)
    try {
      expect((await adminService.updateUser(admin.id, { role: 'user' }, admin)).role).toBe('user')
    } finally {
      await adminService.updateUser(admin.id, { role: 'super_admin' }, secondAdmin)
      await adminService.updateUser(secondAdmin.id, { role: 'user' }, admin)
    }
  })

  it('keeps provider secrets out of list results and records changes', async () => {
    const key = await adminService.addProviderKey({ provider: 'gemini', label: 'Test key', secret: 'secret-value' }, admin)
    expect(key).not.toHaveProperty('secret')
    expect((await adminService.listProviderKeys(admin)).find((item) => item.id === key.id)).not.toHaveProperty('secret')
    await adminService.deactivateProviderKey(key.id, admin)
    const audit = await adminService.listAudit({ action: 'provider_key.' }, admin)
    expect(audit.items.map((event) => event.action)).toContain('provider_key.deactivated')
  })

  it('blocks a run when the project budget is lowered below current spend', async () => {
    const previous = (await adminService.listBudgets(admin)).find((item) => item.target_type === 'project' && item.target_id === 'checkout')
    await adminService.upsertBudget({ target_type: 'project', target_id: 'checkout', monthly_limit: '0.0000' }, admin)
    const run = await runService.create({ version_id: 'checkout-v3', variables: { customer_message: 'Check my order' } })
    expect(run.status).toBe('blocked')
    expect(run.cost).toBe('0.0000')
    if (previous) await adminService.upsertBudget({ target_type: 'project', target_id: 'checkout', monthly_limit: previous.monthly_limit }, admin)
  })

  it('preserves price history and reports prototype maintenance honestly', async () => {
    const before = await adminService.listModelPrices(admin)
    await adminService.addModelPrice({ provider: 'gemini', model: 'gemini-2.0-flash', input_price_per_million: '0.200000', output_price_per_million: '0.500000', effective_from: '2026-10-01T00:00:00Z' }, admin)
    expect((await adminService.listModelPrices(admin)).length).toBe(before.length + 2)
    expect((await adminService.maintenance(admin)).database_status).toBe('unavailable')
    expect((await adminService.refreshViews(admin)).last_view_refresh_at).not.toBeNull()
  })
})
