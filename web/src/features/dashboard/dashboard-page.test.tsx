import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../../lib/api/client'
import { refreshLiveData } from '../../lib/live-refresh'
import { deploymentService } from '../deployments/deployment-service'
import { runsApi, type BackendPersonalDashboard, type BackendPromptRun } from '../runs/api'
import { runService } from '../runs/run-service'
import { RunsPage } from '../runs/runs-page'
import { DashboardPage } from './dashboard-page'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))
vi.mock('../auth/auth-context', () => ({ useAuth: () => ({ user: { id: 'user-1', display_name: 'Ananya' } }) }))

function run(id: string, status: BackendPromptRun['status'] = 'completed'): BackendPromptRun {
  return {
    id, user_id: 'user-1', project_id: 'project-1', prompt_id: 'prompt-1',
    prompt_key: id, version_id: 'version-1', version_number: 1, provider: 'mock',
    model: 'deterministic-v1', status, input_variables: {}, output_text: 'Output',
    prompt_tokens: 1, completion_tokens: 1, latency_ms: 25, cost: '0',
    error_code: status === 'completed' ? null : status === 'blocked' ? 'budget_exceeded' : 'provider_error',
    created_at: '2026-10-10T10:00:00Z',
  }
}
function dashboard(rows: BackendPromptRun[]): BackendPersonalDashboard {
  return {
    recent_runs: rows, project_count: 1, prompt_count: 1, monthly_spend: '0',
    monthly_budget: null, pending_approval_count: 0, run_count: rows.length,
    cost_trend: [], month: '2026-10', timezone: 'UTC', completed_run_count: 0,
    failed_run_count: 0, blocked_run_count: 0, refreshed_through: '2026-10-10T10:00:00Z',
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function setup() { return render(<MemoryRouter><DashboardPage /></MemoryRouter>) }

beforeEach(() => {
  vi.spyOn(deploymentService, 'list').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
})
afterEach(() => vi.restoreAllMocks())

describe('personal Recent Activity', () => {
  it('shows only four runs in the exact backend order and labels the personal scope', async () => {
    const ids = ['newest-z', 'newest-a', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']
    vi.spyOn(runsApi, 'personalDashboard').mockResolvedValue(dashboard(ids.map((id) => run(id))))
    setup()

    await screen.findByText('newest-z · v1')
    expect(screen.getAllByText(/· v1/).map((item) => item.textContent)).toEqual(ids.slice(0, 4).map((id) => `${id} · v1`))
    expect(screen.getByText('Your four most recent runs.')).toBeInTheDocument()
    expect(screen.getByText('YOUR RUNS')).toBeInTheDocument()
    expect(screen.queryByText('fifth · v1')).not.toBeInTheDocument()
  })

  it('keeps an explicit loading and personal empty state', async () => {
    const pending = deferred<BackendPersonalDashboard>()
    vi.spyOn(runsApi, 'personalDashboard').mockReturnValue(pending.promise)
    setup()
    expect(screen.getByText('Loading dashboard…')).toBeInTheDocument()
    await act(async () => pending.resolve(dashboard([])))
    expect(screen.getByText('No personal runs yet')).toBeInTheDocument()
  })

  it('preserves the error message and supports retry', async () => {
    const read = vi.spyOn(runsApi, 'personalDashboard').mockRejectedValueOnce(new Error('Dashboard unavailable')).mockResolvedValue(dashboard([run('recovered')]))
    setup()
    expect(await screen.findByText('Dashboard unavailable')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByText('recovered · v1')).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(2)
  })

  it.each(['success', 'failure'] as const)('ignores an older %s after a newer refresh completes', async (outcome) => {
    const old = deferred<BackendPersonalDashboard>()
    const read = vi.spyOn(runsApi, 'personalDashboard').mockReturnValueOnce(old.promise).mockResolvedValue(dashboard([run('fresh')]))
    setup()
    await act(async () => refreshLiveData())
    expect(await screen.findByText('fresh · v1')).toBeInTheDocument()
    await act(async () => {
      if (outcome === 'success') old.resolve(dashboard([run('stale')]))
      else old.reject(new Error('Stale failure'))
    })
    expect(read).toHaveBeenCalledTimes(2)
    expect(screen.getByText('fresh · v1')).toBeInTheDocument()
    expect(screen.queryByText('stale · v1')).not.toBeInTheDocument()
    expect(screen.queryByText('Stale failure')).not.toBeInTheDocument()
  })

  it.each(['completed', 'failed', 'blocked'] as const)('refetches mounted dashboard and Runs after a recorded %s outcome', async (status) => {
    const read = vi.spyOn(runsApi, 'personalDashboard').mockResolvedValue(dashboard([]))
    const list = vi.spyOn(runsApi, 'list').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 })
    render(<MemoryRouter><DashboardPage /><RunsPage /></MemoryRouter>)
    await screen.findByText('No personal runs yet')
    await screen.findByText('No runs match these filters.')
    const recorded = run(`recorded-${status}`, status)
    read.mockResolvedValue(dashboard([recorded]))
    list.mockResolvedValue({ items: [recorded], total: 1, page: 1, page_size: 10 })
    const error = new ApiClientError(status === 'blocked' ? 409 : 502, {
      code: status === 'blocked' ? 'budget_exceeded' : 'provider_error', message: 'Original provider message',
    })
    const create = vi.spyOn(runsApi, 'create')
    if (status === 'completed') create.mockResolvedValue(recorded)
    else create.mockRejectedValue(error)

    await act(async () => {
      const result = runService.create({ version_id: 'version-1', variables: {} })
      if (status === 'completed') await result
      else await expect(result).rejects.toBe(error)
    })

    await waitFor(() => expect(screen.getAllByText(`recorded-${status} · v1`)).toHaveLength(2))
    expect(read).toHaveBeenCalledTimes(2)
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('prevents an older Runs response from overwriting a refreshed list', async () => {
    const old = deferred<Awaited<ReturnType<typeof runsApi.list>>>()
    vi.spyOn(runsApi, 'list').mockReturnValueOnce(old.promise).mockResolvedValue({ items: [run('fresh-list')], total: 1, page: 1, page_size: 10 })
    render(<MemoryRouter><RunsPage /></MemoryRouter>)
    await act(async () => refreshLiveData())
    expect(await screen.findByText('fresh-list · v1')).toBeInTheDocument()
    await act(async () => old.resolve({ items: [run('stale-list')], total: 1, page: 1, page_size: 10 }))
    expect(screen.queryByText('stale-list · v1')).not.toBeInTheDocument()
    expect(screen.getByText('fresh-list · v1')).toBeInTheDocument()
  })
})
