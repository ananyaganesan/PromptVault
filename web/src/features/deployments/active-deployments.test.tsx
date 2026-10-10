import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DeploymentRollbackPage } from '../admin/deployment-governance'
import { DeploymentDetailPage } from './deployment-pages'
import { adminDeploymentsApi, deploymentsApi, type BackendDeploymentDetail } from './api'
import { adaptBackendDeployment, deploymentService } from './deployment-service'
import { activeVersionsStore, versionStore } from '../projects/workspace-data'
import { PromptsPage } from '../prompts/prompt-pages'
import { promptStore } from '../projects/workspace-data'
import { PromptDeploymentStatus, VersionDeploymentStatus } from '../versions/version-pages'
import { refreshLiveData } from '../../lib/live-refresh'
const auth = vi.hoisted(() => ({ user: { id: 'admin', role: 'super_admin' as const, display_name: 'Admin', email: 'admin@example.com', is_active: true, created_at: '2026-10-10T00:00:00Z' } }))
vi.mock('../auth/auth-context', () => ({ useAuth: () => auth }))
vi.mock('../../lib/runtime', () => ({ useDemoData: false }))
function deployment(id = 'active'): BackendDeploymentDetail {
  return { id, project_id: 'project', prompt_id: 'prompt', prompt_key: id, version_id: 'v3', version_number: 3, environment: 'prod', status: 'active', request_note: null, review_note: null, rollback_reason: 'Restore stability', rollback_of_id: 'previous', requested_by: { id: 'admin', display_name: 'Admin' }, reviewed_by: null, requested_at: '2026-10-10T00:00:00Z', reviewed_at: null, activated_at: '2026-10-10T00:01:00Z', timeline: [{ id: 'previous', version_id: 'v2', version_number: 2, status: 'rolled_back', requested_at: '2026-10-09T00:00:00Z', reviewed_at: null, activated_at: '2026-10-09T00:01:00Z' }] }
}
function setup() { render(<MemoryRouter initialEntries={['/rollback']}><Routes><Route path="/rollback" element={<DeploymentRollbackPage />} /><Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} /></Routes></MemoryRouter>) }
beforeEach(() => {
  versionStore.prompt = [3, 2, 1].map((number) => ({ id: `v${number}`, prompt_id: 'prompt', version_number: number, parent_version_id: null, template: 'Template', variables: [], model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 100 }, commit_message: 'Saved', created_by: 'admin', created_by_name: 'Admin', created_at: '2026-10-10T00:00:00Z' }))
  vi.spyOn(deploymentsApi, 'list').mockResolvedValue({ items: [deployment()], total: 1, page: 1, page_size: 100 })
  vi.spyOn(deploymentsApi, 'get').mockImplementation(async (id) => deployment(id))
})
afterEach(() => vi.restoreAllMocks())
it('loads all 101 active production records and excludes staging', async () => {
  vi.mocked(deploymentsApi.list).mockImplementation(async (query) => ({ items: query?.page === 1 ? Array.from({ length: 100 }, (_, n) => deployment(`record-${n}`)) : [deployment('last'), { ...deployment('staging'), environment: 'staging' }], total: 102, page: query?.page ?? 1, page_size: 100 }))
  setup()
  expect(await screen.findByRole('option', { name: /last · production/ })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: /staging ·/ })).not.toBeInTheDocument()
  expect(deploymentsApi.list).toHaveBeenNthCalledWith(2, expect.objectContaining({ page: 2, page_size: 100, environment: 'prod', status: 'active' }))
})
it.each(['staging', 'superseded'] as const)('rejects an unsupported or obsolete %s rollback before POST', async (kind) => {
  vi.mocked(deploymentsApi.get).mockResolvedValue({ ...deployment(), ...(kind === 'staging' ? { environment: 'staging' as const } : { status: 'superseded' as const }) })
  const post = vi.spyOn(adminDeploymentsApi, 'rollback')
  await expect(deploymentService.rollback('active', 'v2', 'Reason', auth.user)).rejects.toThrow(kind === 'staging' ? 'production' : 'no longer active')
  expect(post).not.toHaveBeenCalled()
})
it('submits once and refreshes the currently active result after a successful rollback', async () => {
  let resolve!: (value: BackendDeploymentDetail) => void
  const post = vi.spyOn(adminDeploymentsApi, 'rollback').mockImplementation(() => new Promise((yes) => { resolve = yes }))
  setup()
  await screen.findByRole('option', { name: /active · production/ })
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Rollback reason'), 'Restore stability')
  await user.click(screen.getByRole('button', { name: 'Review rollback' }))
  const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm' })
  fireEvent.click(confirm); fireEvent.click(confirm)
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
  expect(post).toHaveBeenCalledWith('prompt', 'v2', 'Restore stability')
  vi.mocked(deploymentsApi.get).mockResolvedValue({ ...deployment('rollback'), version_id: 'v2', version_number: 2 })
  await act(async () => resolve({ ...deployment('rollback'), version_id: 'v2', version_number: 2 }))
  expect(await screen.findByText('rollback → Production')).toBeInTheDocument()
  expect(screen.getByText('v2')).toBeInTheDocument()
  expect(screen.getAllByText('Restore stability')).toHaveLength(2)
  expect(screen.getByRole('link', { name: 'v2 · Rolled back' })).toBeInTheDocument()
})
it('preserves the backend failure and reason, and refetches after failed rollback', async () => {
  vi.spyOn(adminDeploymentsApi, 'rollback').mockRejectedValue(new Error('Rollback target must be an earlier version'))
  setup()
  await screen.findByRole('option', { name: /active · production/ })
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Rollback reason'), 'My reason')
  await user.click(screen.getByRole('button', { name: 'Review rollback' }))
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm' }))
  expect(await screen.findByText(/Rollback target must be an earlier version/)).toBeInTheDocument()
  await waitFor(() => expect(deploymentsApi.list).toHaveBeenCalledTimes(2))
  expect(screen.getByLabelText('Rollback reason')).toHaveValue('My reason')
})
it('does not silently replace an invalidated active selection on refresh', async () => {
  setup(); await screen.findByRole('option', { name: /active · production/ })
  vi.mocked(deploymentsApi.list).mockResolvedValue({ items: [deployment('new-active')], total: 1, page: 1, page_size: 100 })
  act(refreshLiveData)
  await screen.findByRole('option', { name: /new-active · production/ })
  expect(screen.getByLabelText('Active deployment')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Review rollback' })).toBeDisabled()
  expect(screen.getByText(/selected deployment is no longer active/)).toBeInTheDocument()
})
it('retains timeline, activation, and rollback metadata', () => {
  expect(adaptBackendDeployment(deployment())).toMatchObject({ requested_at: deployment().requested_at, activated_at: deployment().activated_at, rollback_of_id: 'previous', rollback_reason: 'Restore stability', timeline: deployment().timeline })
})
it('shows every active environment and labels each version independently', () => {
  activeVersionsStore.prompt = { prod: 'v3', staging: 'v2', dev: 'v3' }
  render(<><PromptDeploymentStatus promptId="prompt" /><VersionDeploymentStatus promptId="prompt" versionId="v3" /></>)
  expect(screen.getByText('Active: production, staging, development')).toBeInTheDocument()
  expect(screen.getByText('Active: production, development')).toBeInTheDocument()
})
it('hides old detail status during refresh and ignores an obsolete response', async () => {
  let resolve!: (value: BackendDeploymentDetail) => void
  vi.mocked(deploymentsApi.get).mockImplementationOnce(() => new Promise((yes) => { resolve = yes })).mockResolvedValueOnce({ ...deployment(), status: 'rolled_back' })
  render(<MemoryRouter initialEntries={['/deployments/active']}><Routes><Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} /></Routes></MemoryRouter>)
  act(refreshLiveData)
  await screen.findAllByText('Rolled back')
  await act(async () => resolve(deployment()))
  expect(screen.queryByText('Active')).not.toBeInTheDocument()
})

it('includes a prompt in each active environment filter instead of only its primary environment', async () => {
  promptStore.splice(0, promptStore.length, { id: 'prompt', project_id: 'project', key: 'reply', name: 'Reply', description: null, latest_version_number: 3, active_environment: 'production', created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' })
  activeVersionsStore.prompt = { prod: 'v3', staging: 'v2' }
  render(<MemoryRouter><PromptsPage /></MemoryRouter>)
  await userEvent.setup().selectOptions(screen.getByLabelText('Environment'), 'staging')
  expect(screen.getByRole('link', { name: /replyReply/ })).toBeInTheDocument()
  await userEvent.setup().selectOptions(screen.getByLabelText('Environment'), 'draft')
  expect(screen.queryByRole('link', { name: /replyReply/ })).not.toBeInTheDocument()
})

it('ignores an obsolete rollback list response after controlled refresh', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof deploymentsApi.list>>) => void
  vi.mocked(deploymentsApi.list).mockImplementationOnce(() => new Promise((yes) => { resolve = yes })).mockResolvedValueOnce({ items: [deployment('current')], total: 1, page: 1, page_size: 100 })
  setup()
  act(refreshLiveData)
  await screen.findByRole('option', { name: /current · production/ })
  await act(async () => resolve({ items: [deployment('obsolete')], total: 1, page: 1, page_size: 100 }))
  expect(screen.queryByRole('option', { name: /obsolete · production/ })).not.toBeInTheDocument()
  expect(screen.getByLabelText('Active deployment')).toHaveValue('current')
})
