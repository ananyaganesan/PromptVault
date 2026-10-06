import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminService } from './admin-service'
import { ProviderKeyManagementPage } from './console-pages'

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

  it('offers credentials only for providers implemented by the backend', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><ProviderKeyManagementPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Add provider key' }))

    const options = screen.getByLabelText('Provider').querySelectorAll('option')
    expect(Array.from(options, (option) => option.value)).toEqual(['gemini'])
  })
})
