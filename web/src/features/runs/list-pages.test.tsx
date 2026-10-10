import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { refreshLiveData } from '../../lib/live-refresh'
import type { Page } from '../../types/api'
import type { PromptRun } from '../../types/runs'
import type { Deployment } from '../../types/deployments'
import { DeploymentListPage } from '../deployments/deployment-pages'
import { deploymentService } from '../deployments/deployment-service'
import { runService } from './run-service'
import { RunsPage } from './runs-page'

type Kind = 'runs' | 'deployments'
type Seed = { id: string; target: boolean }
type Query = { page?: number; page_size?: number; status?: string; project_id?: string; environment?: string; model?: string; from?: string }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function run(row: Seed): PromptRun {
  return {
    id: row.id, prompt_key: row.id, project_id: row.target ? 'growth' : 'checkout',
    prompt_id: 'prompt-1', version_id: 'version-1', version_number: 1, user_id: 'user-1',
    model: row.target ? 'rare-model' : 'common-model', status: row.target ? 'failed' : 'completed',
    input_variables: {}, output: null, prompt_tokens: 1, completion_tokens: 1,
    latency_ms: 25, cost: '0', created_at: '2026-10-10T10:00:00Z',
  }
}
function deployment(row: Seed): Deployment {
  return {
    id: row.id, prompt_key: row.id, project_id: row.target ? 'growth' : 'checkout',
    project_name: 'Project', prompt_id: 'prompt-1', version_id: 'version-1', version_number: 1,
    status: row.target ? 'rejected' : 'active', environment: row.target ? 'production' : 'staging',
    note: null, requested_by: 'user-1', requested_by_name: 'User', reviewed_by: null,
    reviewed_at: null, review_note: null, created_at: '2026-10-10T10:00:00Z',
  }
}
function setup(kind: Kind) {
  let rows: Seed[] = Array.from({ length: 24 }, (_, index) => ({ id: `record-${index}`, target: index >= 20 }))
  const read = vi.fn(async (query: Query): Promise<Page<Seed>> => {
    const filtered = rows.filter((row) => {
      const item = kind === 'runs' ? run(row) : deployment(row)
      return (!query.project_id || item.project_id === query.project_id)
        && (!query.status || item.status === query.status)
        && (!query.model || run(row).model === query.model)
        && (!query.environment || deployment(row).environment === query.environment)
    })
    const page = query.page ?? 1
    const pageSize = query.page_size ?? 10
    return { items: filtered.slice((page - 1) * pageSize, page * pageSize), total: filtered.length, page, page_size: pageSize }
  })
  if (kind === 'runs') vi.spyOn(runService, 'list').mockImplementation(async (query) => {
    const result = await read(query ?? {})
    return { ...result, items: result.items.map(run) }
  })
  else vi.spyOn(deploymentService, 'list').mockImplementation(async (query) => {
    const result = await read(query ?? {})
    return { ...result, items: result.items.map(deployment) }
  })
  render(<MemoryRouter>{kind === 'runs' ? <RunsPage /> : <DeploymentListPage />}</MemoryRouter>)
  return {
    read,
    setRows(next: Seed[]) { rows = next },
    prefix: kind === 'runs' ? 'Run' : 'Deployment',
    text(id: string) { return kind === 'runs' ? `${id} · v1` : `${id} → ${Number(id.split('-')[1]) >= 20 ? 'Production' : 'Staging'}` },
  }
}
afterEach(() => vi.restoreAllMocks())

describe.each<Kind>(['runs', 'deployments'])('%s list correctness', (kind) => {
  it('reaches records beyond page one and filters the entire server result set', async () => {
    const user = userEvent.setup()
    const h = setup(kind)
    await screen.findByText(h.text('record-0'))
    expect(screen.queryByRole('textbox', { name: /search/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText(h.text('record-10'))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText(h.text('record-20'))
    await user.selectOptions(screen.getByLabelText(`${h.prefix} status`), kind === 'runs' ? 'failed' : 'rejected')
    await screen.findByText(`4 ${kind} · page 1`)
    expect(screen.getAllByRole('row')).toHaveLength(5)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    expect(h.read).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, status: kind === 'runs' ? 'failed' : 'rejected' }))
  })

  it('preserves server filters and page during controlled refresh and retry', async () => {
    const user = userEvent.setup()
    const h = setup(kind)
    await screen.findByText(h.text('record-0'))
    await user.selectOptions(screen.getByLabelText(`${h.prefix} project`), 'checkout')
    await user.selectOptions(screen.getByLabelText(`${h.prefix} status`), kind === 'runs' ? 'completed' : 'active')
    if (kind === 'runs') {
      await user.type(screen.getByLabelText('Run model'), 'common-model')
      await user.selectOptions(screen.getByLabelText('Run period'), 'all')
    } else await user.selectOptions(screen.getByLabelText('Deployment environment'), 'staging')
    await screen.findByText(`20 ${kind} · page 1`)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText(h.text('record-10'))
    h.read.mockRejectedValueOnce(new Error('Temporary list outage'))
    await act(async () => refreshLiveData())
    await screen.findByText('Temporary list outage')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText(`20 ${kind} · page 2`)
    expect(screen.getByLabelText(`${h.prefix} project`)).toHaveValue('checkout')
    expect(screen.getByLabelText(`${h.prefix} status`)).toHaveValue(kind === 'runs' ? 'completed' : 'active')
    expect(h.read).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, project_id: 'checkout', status: kind === 'runs' ? 'completed' : 'active' }))
    if (kind === 'runs') {
      expect(screen.getByLabelText('Run model')).toHaveValue('common-model')
      expect(screen.getByLabelText('Run period')).toHaveValue('all')
      expect(h.read).toHaveBeenLastCalledWith(expect.objectContaining({ model: 'common-model', from: undefined }))
    } else expect(screen.getByLabelText('Deployment environment')).toHaveValue('staging')
  })

  it('clamps a page after totals shrink and resets an empty result to page one', async () => {
    const user = userEvent.setup()
    const h = setup(kind)
    await screen.findByText(h.text('record-0'))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText(h.text('record-10'))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText(h.text('record-20'))
    h.setRows(Array.from({ length: 11 }, (_, index) => ({ id: `record-${index}`, target: false })))
    await act(async () => refreshLiveData())
    await screen.findByText(`11 ${kind} · page 2`)
    expect(screen.getAllByRole('row')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    h.setRows([])
    await act(async () => refreshLiveData())
    await screen.findByText(`0 ${kind} · page 1`)
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it.each(['success', 'failure'] as const)('hides previous rows while loading and ignores an older %s', async (outcome) => {
    const h = setup(kind)
    await screen.findByText(h.text('record-0'))
    const old = deferred<Page<Seed>>()
    h.read.mockReturnValueOnce(old.promise)
    await act(async () => refreshLiveData())
    expect(screen.getByText(`Loading ${kind}…`)).toBeInTheDocument()
    expect(screen.queryByText(h.text('record-0'))).not.toBeInTheDocument()
    h.setRows([{ id: 'record-23', target: true }])
    await act(async () => refreshLiveData())
    await screen.findByText(h.text('record-23'))
    await act(async () => {
      if (outcome === 'success') old.resolve({ items: [{ id: 'record-0', target: false }], total: 1, page: 1, page_size: 10 })
      else old.reject(new Error('Obsolete error'))
    })
    expect(screen.queryByText(h.text('record-0'))).not.toBeInTheDocument()
    expect(screen.queryByText('Obsolete error')).not.toBeInTheDocument()
    expect(screen.getByText(h.text('record-23'))).toBeInTheDocument()
  })
})

it('finds exact-model matches originally beyond the first twenty runs', async () => {
  const user = userEvent.setup()
  const h = setup('runs')
  await screen.findByText(h.text('record-0'))
  await user.type(screen.getByLabelText('Run model'), 'rare-model')
  await screen.findByText('4 runs · page 1')
  expect(screen.getByText(h.text('record-20'))).toBeInTheDocument()
  expect(h.read).toHaveBeenLastCalledWith(expect.objectContaining({ model: 'rare-model', page: 1 }))
})

it('finds production deployments beyond page one through the server environment filter', async () => {
  const h = setup('deployments')
  await screen.findByText(h.text('record-0'))
  await userEvent.setup().selectOptions(screen.getByLabelText('Deployment environment'), 'production')
  await screen.findByText('4 deployments · page 1')
  expect(screen.getByText(h.text('record-20'))).toBeInTheDocument()
  await waitFor(() => expect(h.read).toHaveBeenLastCalledWith(expect.objectContaining({ environment: 'production', page: 1 })))
})
