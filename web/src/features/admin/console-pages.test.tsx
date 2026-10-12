import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminService } from './admin-service'
import { AdminRunsExplorerPage, ProviderKeyManagementPage } from './console-pages'

vi.mock('../auth/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'admin-id',
      email: 'admin@example.com',
      display_name: 'Admin',
      role: 'super_admin',
      is_active: true,
    },
  }),
}))

describe('ProviderKeyManagementPage', () => {
  beforeEach(() => {
    vi.spyOn(adminService, 'listProviderKeys').mockResolvedValue([])
  })

  it('offers credentials only for the fixed three-provider scope', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><ProviderKeyManagementPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Add provider key' }))

    const options = screen.getByLabelText('Provider').querySelectorAll('option')
    expect(Array.from(options, (option) => option.value)).toEqual(['gemini', 'openrouter', 'groq'])
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
