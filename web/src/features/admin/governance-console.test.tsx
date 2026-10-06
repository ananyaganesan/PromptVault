import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminService } from './admin-service'
import { PricingManagementPage } from './governance-console'

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

describe('PricingManagementPage', () => {
  beforeEach(() => {
    vi.spyOn(adminService, 'listModelPrices').mockResolvedValue([])
  })

  it('submits input and output prices together', async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(adminService, 'addModelPrice').mockResolvedValue([])
    render(<MemoryRouter><PricingManagementPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Add price' }))
    await user.type(screen.getByLabelText('Model'), 'gemini-2.0-flash')
    await user.type(screen.getByLabelText('Input price per million tokens'), '0.125')
    await user.type(screen.getByLabelText('Output price per million tokens'), '0.5')
    await user.click(within(screen.getByRole('dialog', { name: 'Add model price' })).getByRole('button', { name: 'Add price' }))

    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'gemini',
      model: 'gemini-2.0-flash',
      input_price_per_million: '0.125',
      output_price_per_million: '0.5',
    }), expect.objectContaining({ id: 'admin-id' }))
  })
})
