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
  it('disables demotion for another Super Admin but keeps self-demotion available', async () => {
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
    expect(within(otherRow!).getByRole('button', { name: 'Make user' })).toBeDisabled()
    expect(within(ownRow!).getByRole('button', { name: 'Make user' })).toBeEnabled()
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
    await user.click(await screen.findByRole('button', { name: 'Approve user' }))
    expect(screen.queryByRole('button', { name: 'Make admin' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make Super Admin' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('pending-id', { is_approved: true }, expect.objectContaining({ role: 'admin' })))
  })
})
