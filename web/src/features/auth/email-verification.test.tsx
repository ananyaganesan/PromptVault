import { StrictMode } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError, clearAccessToken } from '../../lib/api/client'
import { authApi } from './api'
import { AuthProvider } from './auth-context'
import { LoginPage, VerifyEmailPage } from './pages'

function renderVerification(path: string) {
  return render(<StrictMode><AuthProvider><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/verify-email" element={<VerifyEmailPage />} />
    <Route path="/login" element={<h1>Sign in</h1>} />
  </Routes></MemoryRouter></AuthProvider></StrictMode>)
}

function renderLogin() {
  return render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dashboard" element={<h1>Dashboard</h1>} />
  </Routes></MemoryRouter></AuthProvider>)
}

async function reachUnverifiedLogin() {
  vi.spyOn(authApi, 'login').mockRejectedValue(new ApiClientError(403, {
    code: 'email_unverified',
    message: 'Verify your email before signing in',
  }))
  const user = userEvent.setup()
  renderLogin()
  await user.type(screen.getByLabelText('Email address'), 'Pending@Example.com')
  await user.type(screen.getByLabelText('Password'), 'CorrectHorse2026!')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Verify your email before signing in')
  return user
}

afterEach(() => {
  vi.restoreAllMocks()
  clearAccessToken()
  sessionStorage.clear()
})

describe('email verification', () => {
  it('shows an invalid-link state without calling the API when the token is missing', () => {
    const confirm = vi.spyOn(authApi, 'confirmEmailVerification')

    renderVerification('/verify-email')

    expect(screen.getByRole('alert')).toHaveTextContent('This email verification link is invalid or expired.')
    expect(confirm).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('confirms the query token once and offers sign in without creating a session', async () => {
    const confirm = vi.spyOn(authApi, 'confirmEmailVerification').mockResolvedValue(undefined)

    renderVerification('/verify-email?token=verification-token-value')

    expect(await screen.findByText('Your email has been verified.')).toBeInTheDocument()
    expect(confirm).toHaveBeenCalledOnce()
    expect(confirm).toHaveBeenCalledWith('verification-token-value')
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('shows invalid-or-expired copy for a rejected token', async () => {
    vi.spyOn(authApi, 'confirmEmailVerification').mockRejectedValue(new ApiClientError(400, {
      code: 'invalid_verification_token',
      message: 'Email verification link is invalid or expired',
    }))

    renderVerification('/verify-email?token=expired-token-value')

    expect(await screen.findByRole('alert')).toHaveTextContent('Email verification link is invalid or expired')
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('resends after an unverified login and starts a cooldown', async () => {
    const resend = vi.spyOn(authApi, 'resendEmailVerification').mockResolvedValue(undefined)
    const user = await reachUnverifiedLogin()

    await user.click(screen.getByRole('button', { name: 'Resend verification email' }))

    expect(resend).toHaveBeenCalledWith('Pending@Example.com')
    expect(await screen.findByText('If this account is awaiting verification, we sent a new link.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend in 60s' })).toBeDisabled()
  })

  it.each([
    [429, 'Too many verification email requests. Try again later.'],
    [503, 'Verification email could not be delivered'],
  ])('keeps resend recoverable after a %s response', async (status, message) => {
    vi.spyOn(authApi, 'resendEmailVerification').mockRejectedValue(new ApiClientError(status, {
      code: status === 429 ? 'rate_limited' : 'email_delivery_unavailable',
      message,
    }))
    const user = await reachUnverifiedLogin()

    await user.click(screen.getByRole('button', { name: 'Resend verification email' }))

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend verification email' })).toBeEnabled()
  })
})
