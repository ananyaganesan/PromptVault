import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/auth-context'
import { LoginPage } from '../auth/pages'
import { ApiTokensPage } from './api-tokens-page'

describe('API token one-time reveal', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.unstubAllGlobals()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: 'unit-user-token',
      token_type: 'bearer',
      expires_in: 1800,
      user: {
        id: 'usr_demo_user',
        email: 'user@promptvault.dev',
        display_name: 'Demo User',
        role: 'user',
        is_active: true,
        created_at: '2026-09-27T00:00:00Z',
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  })

  it('shows the secret on issue and hides it after closing the dialog', async () => {
    const user = userEvent.setup()
    render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<ApiTokensPage />} /></Routes></MemoryRouter></AuthProvider>)
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Issue token' }))
    await user.type(screen.getByPlaceholderText('e.g. Production consumer'), 'Test consumer')
    await user.type(screen.getByLabelText('Expiration'), '2026-12-31T12:00')
    await user.click(within(screen.getByRole('dialog', { name: 'Issue API token' })).getByRole('button', { name: 'Issue token' }))
    expect(await screen.findByRole('dialog', { name: 'Save your API token' })).toBeInTheDocument()
    expect((screen.getByLabelText('New API token') as HTMLInputElement).value).toMatch(/^pv_/)
    await user.click(screen.getByRole('button', { name: 'I saved it' }))
    expect(screen.queryByLabelText('New API token')).not.toBeInTheDocument()
    const tokenName = await screen.findByText('Test consumer')
    expect(tokenName).toBeInTheDocument()
    expect(within(tokenName.closest('tr')!).getByText('Dec 31, 2026')).toBeInTheDocument()
  })
})
