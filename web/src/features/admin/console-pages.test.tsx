import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminService } from './admin-service'
import { AdminRunsExplorerPage, ProviderKeyManagementPage, UserManagementPage } from './console-pages'

const authRole = vi.hoisted(() => ({ value: 'super_admin' }))
beforeEach(() => { authRole.value = 'super_admin' })

vi.mock('../auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'admin-id',
      email: 'admin@example.com',
      display_name: 'Admin',
      role: authRole.value,
      is_active: true,
    },
  }),
}))

describe('ProviderKeyManagementPage', () => {
  beforeEach(() => {
    vi.spyOn(adminService, 'listProviderKeys').mockResolvedValue([])
  })

  it('offers credentials only for the Gemini-only scope', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><ProviderKeyManagementPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Add provider key' }))

    const options = screen.getByLabelText('Provider').querySelectorAll('option')
    expect(Array.from(options, (option) => option.value)).toEqual(['gemini'])
  })
})

describe('AdminRunsExplorerPage', () => {
  it('sends search to the API so filtering happens before pagination', async () => {
    const user = userEvent.setup()
    vi.spyOn(adminService, 'listUsers').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })
    const listRuns = vi.spyOn(adminService, 'listRuns').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    render(<MemoryRouter><AdminRunsExplorerPage /></MemoryRouter>)

    await user.type(screen.getByLabelText('Search runs'), 'checkout')

    await waitFor(() => expect(listRuns).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: 'checkout', page: 1, page_size: 20 }),
      expect.objectContaining({ id: 'admin-id' }),
    ))
  })
})

describe('UserManagementPage', () => {
  it('hides peer Super Admin role changes and offers self-demotion when another Super Admin is active', async () => {
    vi.spyOn(adminService, 'listUsers').mockResolvedValue({
      items: [
        { id: 'other-admin-id', email: 'other@example.com', display_name: 'Other Admin', role: 'super_admin', is_active: true, project_count: 0, last_active_at: null, created_at: '2026-01-01T00:00:00Z' },
        { id: 'admin-id', email: 'admin@example.com', display_name: 'Admin', role: 'super_admin', is_active: true, project_count: 0, last_active_at: null, created_at: '2026-01-01T00:00:00Z' },
      ],
      total: 2,
      page: 1,
      page_size: 25,
    })

    render(<MemoryRouter><UserManagementPage /></MemoryRouter>)

    const otherRow = (await screen.findByText('Other Admin')).closest('tr')
    const ownRow = screen.getByText('Admin', { selector: 'b' }).closest('tr')
    expect(otherRow).not.toBeNull()
    expect(ownRow).not.toBeNull()
    const peerRoles = within(otherRow!).getByRole('combobox', { name: 'Change role for Other Admin' })
    const ownRoles = within(ownRow!).getByRole('combobox', { name: 'Change role for Admin' })
    expect(peerRoles).toBeDisabled()
    expect(within(otherRow!).queryByRole('option', { name: 'User' })).not.toBeInTheDocument()
    await waitFor(() => expect(ownRoles).toBeEnabled())
    expect(within(ownRow!).getByRole('option', { name: 'Super Admin (current)' })).toBeInTheDocument()
    expect(within(ownRow!).getByRole('option', { name: 'User' })).toBeInTheDocument()
    expect(within(ownRow!).getByRole('option', { name: 'Admin' })).toBeInTheDocument()
  })

  it('confirms a role change and shows success after refreshing the user list', async () => {
    const member = { id: 'member-id', email: 'member@example.com', display_name: 'Member', role: 'user' as const, is_active: true, is_approved: true, project_count: 0, last_active_at: null, created_at: '2026-01-01T00:00:00Z' }
    const list = vi.spyOn(adminService, 'listUsers').mockResolvedValue({ items: [member], total: 1, page: 1, page_size: 25 })
    const update = vi.spyOn(adminService, 'updateUser').mockResolvedValue({ ...member, role: 'admin' })
    const user = userEvent.setup()
    render(<MemoryRouter><UserManagementPage /></MemoryRouter>)
    const roles = await screen.findByRole('combobox', { name: 'Change role for Member' })
    await user.selectOptions(roles, 'admin')
    expect(screen.getByRole('dialog')).toHaveTextContent('Change Member to Admin?')
    expect(update).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('member-id', { role: 'admin' }, expect.objectContaining({ role: 'super_admin' })))
    expect(await screen.findByRole('status')).toHaveTextContent("Member's role was updated.")
    await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(1))
  })

  it('confirms deactivation and activation, and keeps errors visible', async () => {
    let member = { id: 'member-id', email: 'member@example.com', display_name: 'Member', role: 'user' as const, is_active: true, is_approved: true, project_count: 0, last_active_at: null, created_at: '2026-01-01T00:00:00Z' }
    vi.spyOn(adminService, 'listUsers').mockImplementation(async () => ({ items: [member], total: 1, page: 1, page_size: 25 }))
    const update = vi.spyOn(adminService, 'updateUser').mockImplementation(async (_id, request) => { member = { ...member, is_active: request.is_active ?? member.is_active }; return member })
    const user = userEvent.setup()
    render(<MemoryRouter><UserManagementPage /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: 'Deactivate' }))
    expect(update).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('member-id', { is_active: false }, expect.anything()))
    expect(await screen.findByRole('status')).toHaveTextContent('Member was deactivated.')
    await user.click(await screen.findByRole('button', { name: 'Activate' }))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('member-id', { is_active: true }, expect.anything()))
    expect(await screen.findByRole('status')).toHaveTextContent('Member was activated.')
    update.mockRejectedValueOnce(new Error('Protected account'))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Change role for Member' }), 'admin')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Protected account')
  })
})


describe('Admin approval permissions', () => {
  it('allows approving a regular user and hides role assignment', async () => {
    authRole.value = 'admin'
    const pending = { id: 'pending-id', email: 'pending@example.com', display_name: 'Pending User', role: 'user' as const, is_active: true, is_approved: false, project_count: 0, last_active_at: null, created_at: '2026-01-01T00:00:00Z' }
    vi.spyOn(adminService, 'listUsers').mockResolvedValue({ items: [pending], total: 1, page: 1, page_size: 25 })
    const update = vi.spyOn(adminService, 'updateUser').mockResolvedValue({ ...pending, is_approved: true })
    const user = userEvent.setup()
    render(<MemoryRouter><UserManagementPage /></MemoryRouter>)
    const roles = await screen.findByRole('combobox', { name: 'Change role for Pending User' })
    expect(within(roles).queryByRole('option', { name: 'Admin' })).not.toBeInTheDocument()
    expect(within(roles).queryByRole('option', { name: 'Super Admin' })).not.toBeInTheDocument()
    await user.selectOptions(roles, 'approve')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('pending-id', { is_approved: true }, expect.objectContaining({ role: 'admin' })))
  })
})
