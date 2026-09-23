import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/auth-context'
import { LoginPage } from '../auth/pages'
import { ApiTokensPage } from './api-tokens-page'

describe('API token one-time reveal', () => {
  it('shows the secret on issue and hides it after closing the dialog', async () => {
    const user = userEvent.setup()
    render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<ApiTokensPage />} /></Routes></MemoryRouter></AuthProvider>)
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'User@123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Issue token' }))
    await user.type(screen.getByPlaceholderText('e.g. Production consumer'), 'Test consumer')
    await user.click(within(screen.getByRole('dialog', { name: 'Issue API token' })).getByRole('button', { name: 'Issue token' }))
    expect(await screen.findByRole('dialog', { name: 'Save your API token' })).toBeInTheDocument()
    expect((screen.getByLabelText('New API token') as HTMLInputElement).value).toMatch(/^pv_/)
    await user.click(screen.getByRole('button', { name: 'I saved it' }))
    expect(screen.queryByLabelText('New API token')).not.toBeInTheDocument()
    expect(await screen.findByText('Test consumer')).toBeInTheDocument()
  })
})
