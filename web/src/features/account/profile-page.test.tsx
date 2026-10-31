import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth/auth-context'
import { authApi } from '../auth/api'
import { ProfilePage } from './account-pages'

const account = { id: 'profile-user', display_name: 'Original name', email: 'profile@example.com', role: 'user' as const, is_active: true, created_at: '2026-10-01T00:00:00Z' }
function Identity() { const { user } = useAuth(); return <div data-testid="shared-identity">{user?.display_name ?? 'signed out'}</div> }
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear() })
function setup(role: 'user' | 'super_admin' = 'user') {
  sessionStorage.setItem('promptvault.api.session', 'profile-session')
  vi.spyOn(authApi, 'me').mockResolvedValue({ ...account, role })
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
    expect(screen.queryByRole('button', { name: 'Delete my account' })).not.toBeInTheDocument()
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

  it('lets a Super Admin delete their own account after password confirmation', async () => {
    const close = vi.spyOn(authApi, 'closeAccount').mockResolvedValue(undefined)
    const user = userEvent.setup(); setup('super_admin')
    await user.click(await screen.findByRole('button', { name: 'Delete my account' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete my account' })
    expect(close).not.toHaveBeenCalled()
    await user.type(within(dialog).getByLabelText('Current password'), 'CorrectPassword2026!')
    await user.click(within(dialog).getByRole('button', { name: 'Delete my account' }))
    expect(close).toHaveBeenCalledWith('CorrectPassword2026!')
    expect(await screen.findByText('signed out')).toBeVisible()
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('keeps the account signed in when the last Super Admin safeguard rejects deletion', async () => {
    vi.spyOn(authApi, 'closeAccount').mockRejectedValue(new Error('The last active Super Admin cannot close their account'))
    const user = userEvent.setup(); setup('super_admin')
    await user.click(await screen.findByRole('button', { name: 'Delete my account' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete my account' })
    await user.type(within(dialog).getByLabelText('Current password'), 'CorrectPassword2026!')
    await user.click(within(dialog).getByRole('button', { name: 'Delete my account' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('last active Super Admin')
    expect(screen.getByTestId('shared-identity')).toHaveTextContent('Original name')
    expect(sessionStorage.getItem('promptvault.api.session')).toBe('profile-session')
  })

  it('shows a wrong-password error without closing the confirmation dialog', async () => {
    vi.spyOn(authApi, 'closeAccount').mockRejectedValue(new Error('Invalid password'))
    const user = userEvent.setup(); setup('super_admin')
    await user.click(await screen.findByRole('button', { name: 'Delete my account' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete my account' })
    await user.type(within(dialog).getByLabelText('Current password'), 'WrongPassword2026!')
    await user.click(within(dialog).getByRole('button', { name: 'Delete my account' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Invalid password')
    expect(within(dialog).getByLabelText('Current password')).toHaveValue('WrongPassword2026!')
    expect(screen.getByTestId('shared-identity')).toHaveTextContent('Original name')
  })
})
