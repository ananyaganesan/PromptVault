import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { activeVersionsStore, promptStore, versionStore, type BackendVersion } from '../projects/workspace-data'
import { CompareVersionPage, VersionDetailPage, VersionLineagePage } from './version-pages'
import { versionsApi, type BackendVersionDiff, type BackendVersionLineage } from './api'

vi.mock('../../lib/runtime', () => ({ useDemoData: false }))
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => { resolve = yes })
  return { promise, resolve }
}
function version(number: number): BackendVersion {
  return { id: `v${number}`, prompt_id: 'prompt', version_number: number, parent_version_id: number > 1 ? `v${number - 1}` : null, template_body: `Template ${number}`, variables: [], model_config: { provider: 'gemini', model: 'deterministic', temperature: 0, max_output_tokens: 100 }, commit_message: 'Saved', created_by: { id: 'owner', display_name: 'Owner' }, created_at: '2026-10-10T00:00:00Z' }
}
function diff(number: number): BackendVersionDiff {
  return { from_version_id: `v${number - 1}`, to_version_id: `v${number}`, template_body: { before: `API base ${number}`, after: `API candidate ${number}`, changed: true }, variables: { added: [], removed: [] }, model_config: { before: version(number).model_config, after: version(number).model_config, changed_fields: [] } }
}
function pairDiff(from: number, to: number): BackendVersionDiff {
  return { from_version_id: `v${from}`, to_version_id: `v${to}`, template_body: { before: `API v${from}`, after: `API v${to}`, changed: from !== to }, variables: { added: [], removed: [] }, model_config: { before: version(from).model_config, after: version(to).model_config, changed_fields: [] } }
}
beforeEach(() => {
  promptStore.splice(0, promptStore.length, { id: 'prompt', project_id: 'project', key: 'prompt', name: 'Prompt', description: null, latest_version_number: 3, active_environment: 'production', created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' })
  versionStore.prompt = [3, 2, 1].map((number) => ({ ...version(number), template: `Template ${number}`, created_by: 'owner', created_by_name: 'Owner', variables: [] }))
  activeVersionsStore.prompt = { prod: 'v1', staging: 'v3' }
})
afterEach(() => vi.restoreAllMocks())
function setup(kind: 'compare' | 'lineage') {
  function Switch() { const navigate = useNavigate(); return <button onClick={() => navigate(`/versions/v3/${kind}`)}>Select v3</button> }
  render(<MemoryRouter initialEntries={[`/versions/v2/${kind}`]}><Switch /><Routes><Route path="/versions/:versionId/compare" element={<CompareVersionPage />} /><Route path="/versions/:versionId/lineage" element={<VersionLineagePage />} /></Routes></MemoryRouter>)
}

it('clears comparison data for a new selection while preserving its current snapshot fallback', async () => {
  const next = deferred<BackendVersionDiff>()
  vi.spyOn(versionsApi, 'diff').mockResolvedValueOnce(diff(2)).mockReturnValueOnce(next.promise)
  setup('compare')
  await screen.findByDisplayValue('API candidate 2')
  await userEvent.setup().click(screen.getByRole('button', { name: 'Select v3' }))
  expect(screen.queryByDisplayValue('API candidate 2')).not.toBeInTheDocument()
  expect(screen.getByDisplayValue('Template 3')).toBeInTheDocument()
  await act(async () => next.resolve(diff(3)))
  expect(screen.getByDisplayValue('API candidate 3')).toBeInTheDocument()
})

it('ignores a comparison response arriving after its selection is abandoned', async () => {
  const old = deferred<BackendVersionDiff>()
  vi.spyOn(versionsApi, 'diff').mockReturnValueOnce(old.promise).mockResolvedValueOnce(diff(3))
  setup('compare')
  await userEvent.setup().click(screen.getByRole('button', { name: 'Select v3' }))
  await screen.findByDisplayValue('API candidate 3')
  await act(async () => old.resolve(diff(2)))
  expect(screen.queryByDisplayValue('API candidate 2')).not.toBeInTheDocument()
  expect(screen.getByDisplayValue('API candidate 3')).toBeInTheDocument()
})

it('compares any two selected versions instead of only a direct parent', async () => {
  const request = vi.spyOn(versionsApi, 'diff')
    .mockResolvedValueOnce(pairDiff(1, 3))
    .mockResolvedValueOnce(pairDiff(2, 3))
    .mockResolvedValueOnce(pairDiff(2, 1))
  render(<MemoryRouter initialEntries={['/versions/v3/compare?against=v1']}><Routes><Route path="/versions/:versionId/compare" element={<CompareVersionPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByDisplayValue('API v1')).toBeInTheDocument()
  expect(screen.getByDisplayValue('API v3')).toBeInTheDocument()
  expect(request).toHaveBeenLastCalledWith('v3', 'v1', expect.any(AbortSignal))

  await userEvent.setup().selectOptions(screen.getByLabelText('Base version'), 'v2')
  expect(await screen.findByDisplayValue('API v2')).toBeInTheDocument()
  expect(request).toHaveBeenLastCalledWith('v3', 'v2', expect.any(AbortSignal))

  await userEvent.setup().selectOptions(screen.getByLabelText('Compare version'), 'v1')
  expect(await screen.findByDisplayValue('API v1')).toBeInTheDocument()
  expect(request).toHaveBeenLastCalledWith('v1', 'v2', expect.any(AbortSignal))
})

it('clears loaded lineage while fetching a newly selected version', async () => {
  const next = deferred<BackendVersionLineage>()
  vi.spyOn(versionsApi, 'lineage').mockResolvedValueOnce({ items: [version(2), version(1)], cycle_detected: false }).mockReturnValueOnce(next.promise)
  setup('lineage')
  await screen.findByText(/descends through 1 earlier version/)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Select v3' }))
  expect(screen.getByText('Loading lineage…')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /v2/ })).not.toBeInTheDocument()
  await act(async () => next.resolve({ items: [version(3), version(2), version(1)], cycle_detected: false }))
  expect(screen.getByText(/descends through 2 earlier versions/)).toBeInTheDocument()
})

it('ignores lineage arriving after its selection changes', async () => {
  const old = deferred<BackendVersionLineage>()
  vi.spyOn(versionsApi, 'lineage').mockReturnValueOnce(old.promise).mockResolvedValueOnce({ items: [version(3), version(2), version(1)], cycle_detected: false })
  setup('lineage')
  await userEvent.setup().click(screen.getByRole('button', { name: 'Select v3' }))
  await screen.findByText(/descends through 2 earlier versions/)
  await act(async () => old.resolve({ items: [version(2)], cycle_detected: false }))
  expect(screen.getByText(/descends through 2 earlier versions/)).toBeInTheDocument()
})

it('labels the selected version rather than inheriting the prompt environment', () => {
  render(<MemoryRouter initialEntries={['/versions/v2']}><Routes><Route path="/versions/:versionId" element={<VersionDetailPage />} /></Routes></MemoryRouter>)
  expect(screen.getByText('Not active')).toBeInTheDocument()
  expect(screen.queryByText('production')).not.toBeInTheDocument()
})
