import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectInvitationPage } from './invitation-page'
import { projectsApi } from './api'

vi.mock('../auth/auth-context', () => ({ useAuth: () => ({ user: { email: 'invited@example.com' }, logout: vi.fn() }) }))
afterEach(() => vi.restoreAllMocks())

it('waits for an explicit acceptance click and opens the accepted project', async () => {
  const accept = vi.spyOn(projectsApi, 'acceptInvitation').mockResolvedValue({ id: 'project' })
  render(<MemoryRouter initialEntries={['/project-invitations#token=secret']}><ProjectInvitationPage /></MemoryRouter>)
  expect(accept).not.toHaveBeenCalled()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Accept invitation' }))
  expect(accept).toHaveBeenCalledWith('secret')
  expect(await screen.findByRole('status')).toHaveTextContent('Invitation accepted')
  expect(screen.getByRole('link', { name: 'Open project' })).toHaveAttribute('href', '/projects/project')
})

it('shows a wrong-account or expired-link error without granting access', async () => {
  vi.spyOn(projectsApi, 'acceptInvitation').mockRejectedValue(new Error('Sign in to the account that received this invitation'))
  render(<MemoryRouter initialEntries={['/project-invitations#token=secret']}><ProjectInvitationPage /></MemoryRouter>)
  await userEvent.setup().click(screen.getByRole('button', { name: 'Accept invitation' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign in to the account that received this invitation')
  expect(screen.queryByRole('link', { name: 'Open project' })).not.toBeInTheDocument()
})

it('disables acceptance for a missing token', () => {
  render(<MemoryRouter initialEntries={['/project-invitations']}><ProjectInvitationPage /></MemoryRouter>)
  expect(screen.getByRole('button', { name: 'Accept invitation' })).toBeDisabled()
})
