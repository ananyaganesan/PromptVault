import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth/auth-context'
import { authApi } from '../auth/api'
import { ProfilePage } from './account-pages'

const account = { id: 'profile-user', display_name: 'Original name', email: 'profile@example.com', role: 'user' as const, is_active: true, created_at: '2026-10-01T00:00:00Z' }
function Identity() { const { user } = useAuth(); return <div data-testid="shared-identity">{user?.display_name}</div> }
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear() })
function setup() {
  sessionStorage.setItem('promptvault.api.session', 'profile-session')
  vi.spyOn(authApi, 'me').mockResolvedValue(account)
  return render(<AuthProvider><MemoryRouter><Identity /><ProfilePage /></MemoryRouter></AuthProvider>)
}

describe('Profile display name', () => {
  it('saves the trimmed name and refreshes the shared identity', async () => {
    const update = vi.spyOn(authApi, 'updateProfile').mockResolvedValue({ ...account, display_name: 'Ananya Ganesan' })
    const user = userEvent.setup(); setup()
    const input = await screen.findByLabelText('Display name')
    await user.clear(input); await user.type(input, '  Ananya Ganesan  ')
    await user.click(screen.getByRole('button', { name: 'Save display name' }))
    expect(await screen.findByText('Display name saved.')).toBeVisible()
    expect(update).toHaveBeenCalledWith('Ananya Ganesan')
    expect(screen.getByTestId('shared-identity')).toHaveTextContent('Ananya Ganesan')
    expect(screen.getByRole('heading', { name: 'Ananya Ganesan' })).toBeVisible()
  })

  it('preserves the draft and shows a failed save', async () => {
    vi.spyOn(authApi, 'updateProfile').mockRejectedValue(new Error('Could not save profile.'))
    const user = userEvent.setup(); setup()
    const input = await screen.findByLabelText('Display name')
    await user.clear(input); await user.type(input, 'My draft name')
    await user.click(screen.getByRole('button', { name: 'Save display name' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save profile.')
    expect(input).toHaveValue('My draft name')
    expect(screen.getByTestId('shared-identity')).toHaveTextContent('Original name')
  })
})
