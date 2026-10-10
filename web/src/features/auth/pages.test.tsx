import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage, ResetPasswordPage } from './pages'
import { AuthProvider } from './auth-context'

function Location() { return <output data-testid="location">{useLocation().pathname}</output> }

function renderLogin() {
  return render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<Location />} /><Route path="/admin" element={<Location />} /></Routes></MemoryRouter></AuthProvider>)
}

function session(role: 'user' | 'admin') {
  return {
    access_token: `live-${role}-token`,
    token_type: 'bearer',
    expires_in: 1800,
    user: {
      id: `${role}-id`,
      email: `${role}@promptvault.dev`,
      display_name: role === 'admin' ? 'Demo Admin' : 'Demo User',
      role,
      is_active: true,
      created_at: '2026-09-27T00:00:00Z',
    },
  }
}

function mockJson(payload: unknown, status = 200) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('LoginPage', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('blocks an empty sign-in attempt', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByText('Email address is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
  })

  it('signs in through the live API and redirects the user to the workspace', async () => {
    const user = userEvent.setup()
    const fetcher = mockJson(session('user'))
    vi.stubGlobal('fetch', fetcher)
    renderLogin()

    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/login',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(sessionStorage.getItem('promptvault.api.session')).toBe('live-user-token')
  })

  it('sends an admin to the dashboard after sign-in', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', mockJson(session('admin')))
    renderLogin()

    await user.type(screen.getByLabelText('Email address'), 'admin@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'AdminDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
  })

  it('shows the same login error for a missing email or wrong password', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ code: 'invalid_credentials', message: 'Invalid email or password.' }), { status: 401, headers: { 'Content-Type': 'application/json' } }))))
    renderLogin()
    await user.type(screen.getByLabelText('Email address'), 'missing@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'WrongPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')

    await user.clear(screen.getByLabelText('Email address'))
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
  })

  it('stays signed out when the backend cannot be reached', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderLogin()
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'AnyPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect to the server.')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })
})

describe('ResetPasswordPage', () => {
  it('keeps the email link usable after password reuse and accepts a fresh password', async () => {
    const user = userEvent.setup()
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'password_reused',
        message: 'Choose a password you have never used for this account',
      }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    const token = 'example-reset-token'.repeat(3)
    render(<MemoryRouter initialEntries={[`/reset-password?token=${token}`]}><ResetPasswordPage /></MemoryRouter>)
    await user.type(screen.getByLabelText('New password'), 'PreviousPassword2026!')
    await user.type(screen.getByLabelText('Confirm password'), 'PreviousPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a password you have never used')
    await user.clear(screen.getByLabelText('New password'))
    await user.clear(screen.getByLabelText('Confirm password'))
    await user.type(screen.getByLabelText('New password'), 'FreshPassword2026!')
    await user.type(screen.getByLabelText('Confirm password'), 'FreshPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(await screen.findByText('Your password has been reset. You can now sign in.')).toBeInTheDocument()
    expect(fetcher).toHaveBeenLastCalledWith(
      'http://localhost:8000/api/v1/auth/password-reset/confirm',
      expect.objectContaining({ body: JSON.stringify({ token, password: 'FreshPassword2026!' }) }),
    )
  })

  it('does not submit a reset without the token from the email link', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    render(<MemoryRouter><ResetPasswordPage /></MemoryRouter>)
    expect(screen.getByRole('alert')).toHaveTextContent('This password reset link is invalid.')
    expect(screen.queryByRole('button', { name: 'Reset password' })).not.toBeInTheDocument()
    expect(fetcher).not.toHaveBeenCalled()
  })
})
