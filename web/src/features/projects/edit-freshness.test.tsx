import { projectsApi } from './api'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ProjectDetailPage } from './project-pages'
import { PromptDetailPage } from '../prompts/prompt-pages'
import { activeVersionsStore, memberStore, projectStore, promptStore, versionStore, workspaceService } from './workspace-data'
import type { PromptVersion } from '../../types/versions'

const auth = vi.hoisted(() => ({ user: { id: 'owner', role: 'user', display_name: 'Owner' } }))
vi.mock('../auth/auth-context', () => ({ useAuth: () => auth }))

function version(number: number): PromptVersion {
  return { id: `v${number}`, prompt_id: 'prompt', version_number: number, parent_version_id: number > 1 ? `v${number - 1}` : null, template: `Template ${number}`, variables: [], model_config: { provider: 'mock', model: 'deterministic', temperature: 0, max_output_tokens: 100 }, commit_message: 'Saved', created_by: 'owner', created_by_name: 'Owner', created_at: '2026-10-10T00:00:00Z' }
}
beforeEach(() => {
  auth.user = { id: 'owner', role: 'user', display_name: 'Owner' }
  projectStore.splice(0, projectStore.length, { id: 'project', name: 'Original', key: 'project', description: 'Original description', owner_id: 'owner', is_owner: true, member_count: 2, prompt_count: 1, monthly_spend: '0', updated_at: '2026-10-10T00:00:00Z', created_at: '2026-10-10T00:00:00Z' })
  promptStore.splice(0, promptStore.length, { id: 'prompt', project_id: 'project', name: 'Prompt', key: 'prompt', description: null, latest_version_number: 1, active_environment: 'production', updated_at: '2026-10-10T00:00:00Z', created_at: '2026-10-10T00:00:00Z' })
  versionStore.prompt = [version(1)]
  activeVersionsStore.prompt = { prod: 'v1' }
  memberStore.project = [
    { user_id: 'owner', display_name: 'Owner', email: 'owner@example.com', role: 'owner', joined_at: '2026-10-10T00:00:00Z' },
    { user_id: 'member', display_name: 'Member', email: 'member@example.com', role: 'member', joined_at: '2026-10-10T00:00:00Z' },
  ]
  vi.spyOn(projectsApi, 'listInvitations').mockResolvedValue([])
  vi.spyOn(workspaceService, 'loadMembers').mockResolvedValue(memberStore.project)
})
afterEach(() => vi.restoreAllMocks())
function setup(page: 'project' | 'prompt') {
  const tree = <MemoryRouter initialEntries={[`/${page}s/${page}`]}><Routes><Route path="/projects/:projectId" element={<ProjectDetailPage />} /><Route path="/prompts/:promptId" element={<PromptDetailPage />} /></Routes></MemoryRouter>
  const view = render(tree)
  return () => view.rerender(<MemoryRouter initialEntries={[`/${page}s/${page}`]}><Routes><Route path="/projects/:projectId" element={<ProjectDetailPage />} /><Route path="/prompts/:promptId" element={<PromptDetailPage />} /></Routes></MemoryRouter>)
}

it('uses refreshed settings when clean, preserves dirty fields, and blocks stale saves until acknowledged', async () => {
  const user = userEvent.setup()
  const rerender = setup('project')
  await user.click(screen.getByRole('button', { name: 'Settings' }))
  projectStore[0] = { ...projectStore[0], name: 'Refreshed' }
  rerender()
  expect(screen.getByLabelText('Project name')).toHaveValue('Refreshed')
  await user.clear(screen.getByLabelText('Project name'))
  await user.type(screen.getByLabelText('Project name'), 'Unsaved name')
  projectStore[0] = { ...projectStore[0], name: 'Other editor', description: 'Other description' }
  rerender()
  expect(screen.getByLabelText('Project name')).toHaveValue('Unsaved name')
  expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Keep my edits' }))
  expect(screen.getByLabelText('Project name')).toHaveValue('Unsaved name')
  expect(screen.getByRole('button', { name: 'Save settings' })).toBeEnabled()
})

it.each(['member', 'owner', 'admin'])('shows member management only for owner/admin: %s', async (role) => {
  auth.user = { id: role === 'owner' ? 'owner' : 'member', role: role === 'admin' ? 'super_admin' : 'user', display_name: 'User' }
  setup('project')
  await userEvent.setup().click(screen.getByRole('button', { name: /Members/ }))
  if (role === 'member') {
    expect(screen.queryByRole('button', { name: 'Invite member' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
  } else {
    expect(screen.getByRole('button', { name: 'Invite member' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1)
  }
})

it('assigns global typography roles to every member identity element', async () => {
  setup('project')
  await userEvent.setup().click(screen.getByRole('button', { name: /Members/ }))

  expect(screen.getByText('Invited users must have a PromptVault account and accept the email invitation before getting access.')).toHaveClass('member-invitation-note')
  expect(screen.getByRole('heading', { name: 'Pending invitations' })).toHaveClass('member-subheading')
  expect(screen.getByText('No pending invitations.')).toHaveClass('member-empty-invitations')
  expect(screen.getByText('Owner')).toHaveClass('member-name')
  expect(screen.getByText('owner@example.com')).toHaveClass('member-email')
  expect(screen.getByText('owner', { selector: '.status' })).toHaveClass('member-role')
  expect(screen.getByText('O', { selector: '.member-avatar' })).toBeInTheDocument()
})

it('refreshes a clean prompt editor to the latest snapshot', () => {
  const rerender = setup('prompt')
  versionStore.prompt = [version(2), version(1)]
  rerender()
  expect(screen.getByLabelText('Prompt template')).toHaveValue('Template 2')
})

it('preserves an edited template and commit, blocks silent rebasing, and uses an explicitly selected parent', async () => {
  const user = userEvent.setup()
  const rerender = setup('prompt')
  await user.clear(screen.getByLabelText('Prompt template'))
  await user.type(screen.getByLabelText('Prompt template'), 'My unsaved draft')
  await user.type(screen.getByLabelText('Commit message'), 'My explanation')
  versionStore.prompt = [version(2), version(1)]
  rerender()
  expect(screen.getByLabelText('Prompt template')).toHaveValue('My unsaved draft')
  expect(screen.getByLabelText('Commit message')).toHaveValue('My explanation')
  expect(screen.getByRole('button', { name: 'Save new version' })).toBeDisabled()
  const create = vi.spyOn(workspaceService, 'createVersion').mockResolvedValue({ ...version(3), template: 'My unsaved draft' })
  await user.click(screen.getByRole('button', { name: 'Keep draft with latest parent' }))
  await user.click(screen.getByRole('button', { name: 'Save new version' }))
  expect(create).toHaveBeenCalledWith('prompt', expect.objectContaining({ parent_version_id: 'v2', template: 'My unsaved draft', commit_message: 'My explanation' }))
})

it('pins a commit-only draft to its original parent on refresh', async () => {
  const rerender = setup('prompt')
  await userEvent.setup().type(screen.getByLabelText('Commit message'), 'Commit-only edit')
  versionStore.prompt = [version(2), version(1)]
  rerender()
  expect(screen.getByLabelText('Prompt template')).toHaveValue('Template 1')
  expect(screen.getByRole('button', { name: 'Save new version' })).toBeDisabled()
})

it('allows explicit replacement of stale settings without silently discarding edits on refresh', async () => {
  const user = userEvent.setup()
  const rerender = setup('project')
  await user.click(screen.getByRole('button', { name: 'Settings' }))
  await user.type(screen.getByLabelText('Project name'), ' local')
  projectStore[0] = { ...projectStore[0], name: 'Server name', description: 'Server description' }
  rerender()
  expect(screen.getByLabelText('Project name')).toHaveValue('Original local')
  await user.click(screen.getByRole('button', { name: 'Use refreshed settings' }))
  expect(screen.getByLabelText('Project name')).toHaveValue('Server name')
  expect(screen.getByLabelText('Description')).toHaveValue('Server description')
})

it('returns a successfully saved clean editor to automatic latest-version refresh', async () => {
  const user = userEvent.setup()
  const rerender = setup('prompt')
  vi.spyOn(workspaceService, 'createVersion').mockImplementation(async () => {
    versionStore.prompt = [version(2), version(1)]
    return version(2)
  })
  await user.type(screen.getByLabelText('Commit message'), 'Save')
  await user.click(screen.getByRole('button', { name: 'Save new version' }))
  versionStore.prompt = [version(3), version(2), version(1)]
  rerender()
  expect(screen.getByLabelText('Prompt template')).toHaveValue('Template 3')
  expect(screen.queryByText(/A newer version is available/)).not.toBeInTheDocument()
})
