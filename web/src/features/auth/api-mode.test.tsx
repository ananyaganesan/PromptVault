import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ApiClientError, clearAccessToken, createApiClient } from '../../lib/api/client'
import { AuthProvider } from './auth-context'
import { authApi } from './api'
import { RequireAuth } from './guards'
import { LoginPage, RegisterPage } from './pages'

function Location() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output> }
function renderAuth(path: '/login' | '/register') {
  render(<AuthProvider><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route path="/dashboard" element={<Location />} />
    <Route path="/admin" element={<Location />} />
  </Routes></MemoryRouter></AuthProvider>)
}

const backendUser = {
  id: '11111111-1111-4111-8111-111111111111',
  email: 'user@promptvault.dev',
  display_name: 'Jamie Chen',
  role: 'user' as const,
  is_active: true,
  created_at: '2026-09-23T00:00:00Z',
}

afterEach(() => { vi.restoreAllMocks(); clearAccessToken(); sessionStorage.clear() })

describe('PostgreSQL-backed authentication', () => {
  it('uses the API response and bearer token for login', async () => {
    const login = vi.spyOn(authApi, 'login').mockResolvedValue({ user: { ...backendUser, role: 'admin' }, access_token: 'server-jwt', token_type: 'bearer', expires_in: 1800 })
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), backendUser.email)
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
    expect(login).toHaveBeenCalledWith({ email: backendUser.email, password: 'UserDemo2026!' })
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
    await createApiClient({ fetcher }).request('/api/v1/auth/me')
    expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer server-jwt' }) }))
    expect(sessionStorage.getItem('promptvault.api.session')).toBe('server-jwt')
  })

  it('returns to the requested page after login, including its query and hash', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue({ user: backendUser, access_token: 'server-jwt', token_type: 'bearer', expires_in: 1800 })
    const user = userEvent.setup()
    render(<AuthProvider><MemoryRouter initialEntries={['/projects?search=checkout#results']}><Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}><Route path="/projects" element={<Location />} /></Route>
    </Routes></MemoryRouter></AuthProvider>)

    await user.type(await screen.findByLabelText('Email address'), backendUser.email)
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/projects?search=checkout#results')
  })

  it('restores a saved session after a page refresh', async () => {
    sessionStorage.setItem('promptvault.api.session', 'saved-jwt')
    const me = vi.spyOn(authApi, 'me').mockResolvedValue(backendUser)
    render(<AuthProvider><MemoryRouter initialEntries={['/dashboard']}><Routes>
      <Route path="/login" element={<Location />} />
      <Route element={<RequireAuth />}><Route path="/dashboard" element={<Location />} /></Route>
    </Routes></MemoryRouter></AuthProvider>)

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
    expect(me).toHaveBeenCalledOnce()
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
    await createApiClient({ fetcher }).request('/api/v1/auth/me')
    expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer saved-jwt' }) }))
  })

  it('clears an expired saved session', async () => {
    sessionStorage.setItem('promptvault.api.session', 'expired-jwt')
    vi.spyOn(authApi, 'me').mockRejectedValue(new ApiClientError(401, { code: 'token_expired', message: 'Token expired' }))
    render(<AuthProvider><MemoryRouter initialEntries={['/dashboard']}><Routes>
      <Route path="/login" element={<Location />} />
      <Route element={<RequireAuth />}><Route path="/dashboard" element={<Location />} /></Route>
    </Routes></MemoryRouter></AuthProvider>)

    expect(await screen.findByTestId('location')).toHaveTextContent('/login')
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('does not accept a demo-only password when the API rejects it', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new ApiClientError(401, { code: 'invalid_credentials', message: 'Invalid email or password.' }))
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), backendUser.email)
    await user.type(screen.getByLabelText('Password'), 'User@123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows when an email is absent from the database', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new ApiClientError(401, { code: 'invalid_credentials', message: 'Invalid email or password.' }))
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), 'missing@example.com')
    await user.type(screen.getByLabelText('Password'), 'SomePassword2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
  })

  it('shows the pending account without creating a browser session', async () => {
    const register = vi.spyOn(authApi, 'register').mockResolvedValue({ email: 'new@example.com', message: 'Check your email to verify your account' })
    const user = userEvent.setup()
    renderAuth('/register')
    await user.type(screen.getByLabelText('Display name'), 'New User')
    await user.type(screen.getByLabelText('Email address'), 'NEW@EXAMPLE.COM')
    await user.type(screen.getByLabelText('Password'), 'StrongPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByText('new@example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend in 60s' })).toBeDisabled()
    expect(screen.queryByTestId('location')).not.toBeInTheDocument()
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
    expect(register).toHaveBeenCalledWith({ display_name: 'New User', email: 'NEW@EXAMPLE.COM', password: 'StrongPassword2026!' })
  })

  it('shows the exact duplicate-account feedback', async () => {
    vi.spyOn(authApi, 'register').mockRejectedValue(new ApiClientError(409, {
      code: 'duplicate_email',
      message: 'An account with this email already exists',
    }))
    const user = userEvent.setup()
    renderAuth('/register')
    await user.type(screen.getByLabelText('Display name'), 'Existing User')
    await user.type(screen.getByLabelText('Email address'), 'existing@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('An account with this email already exists')
  })

  it('does not count spaces toward a new password', async () => {
    const register = vi.spyOn(authApi, 'register')
    const user = userEvent.setup()
    renderAuth('/register')
    await user.type(screen.getByLabelText('Display name'), 'New User')
    await user.type(screen.getByLabelText('Email address'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'Short   123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByPlaceholderText('Create a strong password (12+ characters, no spaces)')).toHaveValue('Short123')
    expect(screen.getByText('Use at least 12 characters.')).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })
})
