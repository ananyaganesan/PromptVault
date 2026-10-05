import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../../lib/api/client'
import { authApi } from './api'
import { ForgotPasswordPage, ResetPasswordPage } from './pages'

function renderPage(path: string, element: React.ReactNode) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/forgot-password" element={element} />
    <Route path="/reset-password" element={element} />
    <Route path="/login" element={<h1>Sign in</h1>} />
  </Routes></MemoryRouter>)
}

afterEach(() => vi.restoreAllMocks())

describe('password recovery', () => {
  it('shows an invalid-link state immediately when the reset token is missing', () => {
    renderPage('/reset-password', <ResetPasswordPage />)

    expect(screen.getByRole('alert')).toHaveTextContent('This password reset link is invalid.')
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reset password' })).not.toBeInTheDocument()
  })

  it('requests a reset without revealing whether the account exists', async () => {
    const requestReset = vi.spyOn(authApi, 'requestPasswordReset').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPage('/forgot-password', <ForgotPasswordPage />)

    await user.type(screen.getByLabelText('Email address'), 'missing@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByText(/If this email belongs to an active account/)).toBeInTheDocument()
    expect(requestReset).toHaveBeenCalledWith('missing@example.com')
  })

  it('shows an expired-or-reused reset-token error from the API', async () => {
    vi.spyOn(authApi, 'confirmPasswordReset').mockRejectedValue(new ApiClientError(400, {
      code: 'invalid_reset_token',
      message: 'Password reset link is invalid or expired',
    }))
    const user = userEvent.setup()
    renderPage('/reset-password?token=valid-looking-reset-token-value-123456', <ResetPasswordPage />)

    await user.type(screen.getByLabelText('New password'), 'NewPassword2026!')
    await user.type(screen.getByLabelText('Confirm password'), 'NewPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Password reset link is invalid or expired')
  })

  it('moves a successful reset to a sign-in action', async () => {
    vi.spyOn(authApi, 'confirmPasswordReset').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPage('/reset-password?token=valid-looking-reset-token-value-123456', <ResetPasswordPage />)

    await user.type(screen.getByLabelText('New password'), 'NewPassword2026!')
    await user.type(screen.getByLabelText('Confirm password'), 'NewPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByText('Your password has been reset. You can now sign in.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})
