import { describe, expect, it, vi } from 'vitest'
import * as adminServiceModule from './admin-service'
import { adaptAdminDashboard, adaptAdminUser, adaptMaintenance, adaptModelPricing, toBackendModelPricingRequest } from './admin-service'
import type { BackendPromptRun } from '../runs/api'

describe('admin API adapters', () => {
  it('maps backend roles and dashboard totals into the existing admin view model', () => {
    expect(adaptAdminUser({
      id: 'admin-id', email: 'admin@example.com', display_name: 'Admin', role: 'admin',
      is_active: true, project_count: 2, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
    }).role).toBe('super_admin')
    expect(adaptAdminDashboard({
      month: '2026-09', timezone: 'UTC', user_count: 3, active_user_count: 2,
      project_count: 4, prompt_count: 5, run_count: 6, completed_run_count: 4,
      failed_run_count: 1, blocked_run_count: 1, total_spend: '1.250000',
      pending_approval_count: 2,
      spend_by_model: [{ provider: 'gemini', model: 'gemini-3.5-flash-lite', run_count: 4, cost: '1.000000' }],
      cost_trend: [], top_spenders: [], refreshed_through: '2026-09-27T00:00:00Z',
    })).toEqual(expect.objectContaining({ monthly_spend: '1.250000', run_count: 6, pending_approval_count: 2 }))
  })

  it('expands a backend input/output pricing record for the existing table', () => {
    expect(adaptModelPricing({
      id: 'price-id', provider: 'gemini', model: 'gemini-3.5-flash-lite', input_price_per_million: '1.0',
      output_price_per_million: '2.0', effective_from: '2026-09-01T00:00:00Z', effective_to: null,
      created_by: null, created_at: '2026-09-01T00:00:00Z',
    })).toEqual([
      expect.objectContaining({ id: 'price-id:input', token_type: 'input', price_per_million_tokens: '1.0' }),
      expect.objectContaining({ id: 'price-id:output', token_type: 'output', price_per_million_tokens: '2.0' }),
    ])
  })

  it('sends both token prices when creating an effective-dated price', () => {
    expect(toBackendModelPricingRequest({
      provider: 'gemini', model: 'gemini-2.0-flash',
      input_price_per_million: '0.125000', output_price_per_million: '0.500000',
      effective_from: '2026-10-01T00:00:00Z',
    })).toEqual({
      provider: 'gemini', model: 'gemini-2.0-flash',
      input_price_per_million: '0.125000', output_price_per_million: '0.500000',
      effective_from: '2026-10-01T00:00:00Z',
    })
  })

  it('summarizes database maintenance details without claiming unavailable data', () => {
    expect(adaptMaintenance({
      database: 'healthy',
      materialized_views: [{ name: 'monthly_usage', is_populated: true, refreshed_through: '2026-09-27T00:00:00Z' }],
      run_partitions: [{ name: 'runs_2026_09', range_expression: 'September' }],
      maintenance_jobs: [], active_provider_key_count: 1, pending_deployment_count: 0,
      checked_at: '2026-09-27T00:00:01Z',
    })).toEqual({ api_status: 'healthy', database_status: 'healthy', partition_count: 1, last_view_refresh_at: '2026-09-27T00:00:00Z' })
  })

  it('loads every organization-run page before budget spend is reconciled', async () => {
    const run = (id: string): BackendPromptRun => ({
      id, project_id: 'project-id', prompt_id: 'prompt-id', prompt_key: 'prompt',
      version_id: 'version-id', version_number: 1, user_id: 'user-id', status: 'completed',
      output_text: 'ok', input_variables: {}, prompt_tokens: 1, completion_tokens: 1,
      latency_ms: 1, cost: '0.010000', model: 'gemini-3.5-flash-lite', provider: 'gemini',
      error_code: null, created_at: '2026-09-28T00:00:00Z',
    })
    const first = Array.from({ length: 100 }, (_, index) => run(`run-${index}`))
    const load = vi.fn()
      .mockResolvedValueOnce({ items: first, total: 101, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ items: [run('run-100')], total: 101, page: 2, page_size: 100 })
    const fetchAllAdminRuns = (adminServiceModule as typeof adminServiceModule & {
      fetchAllAdminRuns?: (loader: typeof load) => Promise<BackendPromptRun[]>
    }).fetchAllAdminRuns

    expect(fetchAllAdminRuns).toBeTypeOf('function')
    await expect(fetchAllAdminRuns!(load)).resolves.toHaveLength(101)
    expect(load).toHaveBeenNthCalledWith(1, { page: 1, page_size: 100 })
    expect(load).toHaveBeenNthCalledWith(2, { page: 2, page_size: 100 })
  })
})
