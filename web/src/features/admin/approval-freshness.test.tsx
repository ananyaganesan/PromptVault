import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiClientError, apiClient } from '../../lib/api/client'
import { adminDeploymentsApi, deploymentsApi, type BackendDeployment, type BackendDeploymentReviewDetail } from '../deployments/api'
import { runsApi } from '../runs/api'
import { DeploymentApprovalQueuePage, DeploymentApprovalReviewPage } from './deployment-governance'

const auth = vi.hoisted(() => ({ user: { id: 'admin', role: 'super_admin', display_name: 'Admin' } }))
vi.mock('../auth/auth-context', () => ({ useAuth: () => auth }))
vi.mock('../../lib/runtime', () => ({ useDemoData: false }))
let status: BackendDeployment['status'] = 'pending'
function deployment(): BackendDeployment {
  return { id: 'request', project_id: 'project', prompt_id: 'prompt', prompt_key: 'reply', version_id: 'v2', version_number: 2, environment: 'prod', status, request_note: 'Ready', review_note: status === 'pending' ? null : 'Reviewed', rollback_reason: null, rollback_of_id: null, requested_by: { id: 'owner', display_name: 'Owner' }, reviewed_by: null, requested_at: '2026-10-10T00:00:00Z', reviewed_at: null, activated_at: null }
}
function detail(): BackendDeploymentReviewDetail {
  const version = { id: 'v2', prompt_id: 'prompt', version_number: 2, parent_version_id: 'v1', template_body: 'Candidate from combined endpoint', variables: [], model_config: { provider: 'gemini', model: 'deterministic', temperature: 0, max_output_tokens: 100 }, commit_message: 'Saved', created_by: { id: 'owner', display_name: 'Owner' }, created_at: '2026-10-10T00:00:00Z' }
  return { deployment: deployment(), requested_version: version, active_version: { ...version, id: 'v1', version_number: 1, parent_version_id: null, template_body: 'Active from combined endpoint' }, recent_runs: [], validation: { id: 'check', version_id: 'v2', environment: 'prod', created_by: 'owner', base_deployment_id: null, created_at: '2026-10-10T00:00:00Z', status: 'passed', summary: 'Every release check passed.', checks: [], configuration: null, evaluation: null, minimum_score: 70 } }
}
function setup(queue = false) {
  render(<MemoryRouter initialEntries={['/admin/approvals/request']}><Routes><Route path="/admin/approvals/:approvalId" element={<>{queue && <DeploymentApprovalQueuePage />}<DeploymentApprovalReviewPage /></>} /></Routes></MemoryRouter>)
}
beforeEach(() => {
  status = 'pending'
  vi.spyOn(adminDeploymentsApi, 'reviewDetail').mockImplementation(async () => detail())
  vi.spyOn(adminDeploymentsApi, 'pending').mockImplementation(async () => ({ items: status === 'pending' ? [deployment()] : [], total: status === 'pending' ? 1 : 0, page: 1, page_size: 100 }))
})
afterEach(() => vi.restoreAllMocks())

it('loads candidate, active version, and run evidence from the combined admin endpoint', async () => {
  const get = vi.spyOn(deploymentsApi, 'get')
  const list = vi.spyOn(deploymentsApi, 'list')
  const runs = vi.spyOn(runsApi, 'list')
  setup()
  expect(await screen.findByDisplayValue('Candidate from combined endpoint')).toBeInTheDocument()
  expect(screen.getByText('Active from combined endpoint')).toBeInTheDocument()
  expect(adminDeploymentsApi.reviewDetail).toHaveBeenCalledWith('request', expect.any(AbortSignal))
  expect(get).not.toHaveBeenCalled()
  expect(list).not.toHaveBeenCalled()
  expect(runs).not.toHaveBeenCalled()
})

it('uses GET /admin/deployments/{id} through the API client', async () => {
  vi.mocked(adminDeploymentsApi.reviewDetail).mockRestore()
  const request = vi.spyOn(apiClient, 'request').mockResolvedValue(detail())
  await adminDeploymentsApi.reviewDetail('request')
  expect(request).toHaveBeenCalledWith('/admin/deployments/request', { signal: undefined })
})

it.each(['approve', 'reject'] as const)('prevents repeated %s submissions and refreshes queue/review after completion', async (action) => {
  let resolve!: (value: BackendDeployment) => void
  const decide = vi.spyOn(adminDeploymentsApi, action).mockImplementation(() => new Promise<BackendDeployment>((yes) => { resolve = yes }))
  setup(true)
  await screen.findByDisplayValue('Candidate from combined endpoint')
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Review note'), 'My review')
  await user.click(screen.getByRole('button', { name: action === 'approve' ? 'Approve production' : 'Reject request' }))
  const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm' })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  expect(decide).toHaveBeenCalledTimes(1)
  expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Working…' })).toBeDisabled()
  status = action === 'approve' ? 'active' : 'rejected'
  await act(async () => resolve(deployment()))
  await screen.findByText('No production requests are waiting for review.')
  await waitFor(() => expect(adminDeploymentsApi.reviewDetail).toHaveBeenCalledTimes(2))
  expect(adminDeploymentsApi.pending).toHaveBeenCalledTimes(2)
  expect(screen.queryByRole('button', { name: 'Approve production' })).not.toBeInTheDocument()
})

it('handles a competing review by refetching the decision and preserving the draft note', async () => {
  vi.spyOn(adminDeploymentsApi, 'approve').mockImplementation(async () => {
    status = 'rejected'
    throw new ApiClientError(409, { code: 'already_reviewed', message: 'Deployment was already reviewed' })
  })
  setup(true)
  await screen.findByDisplayValue('Candidate from combined endpoint')
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Review note'), 'Keep this explanation')
  await user.click(screen.getByRole('button', { name: 'Approve production' }))
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm' }))
  expect(await screen.findByText(/Deployment was already reviewed.*your note is preserved/)).toBeInTheDocument()
  expect(screen.getByText('Your draft note: Keep this explanation')).toBeInTheDocument()
  await screen.findByText('No production requests are waiting for review.')
  expect(screen.queryByRole('button', { name: 'Approve production' })).not.toBeInTheDocument()
})


it.each(['blocked', 'stale', 'running', 'missing'] as const)('blocks approval when validation is %s but allows rejection', async (state) => {
  const data = detail()
  data.validation = state === 'missing' ? null : { ...data.validation!, status: state }
  vi.mocked(adminDeploymentsApi.reviewDetail).mockResolvedValue(data)
  setup()
  await screen.findByDisplayValue('Candidate from combined endpoint')
  expect(screen.getByRole('button', { name: 'Approve production' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject request' })).toBeEnabled()
})
