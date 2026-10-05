import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ApiClientError, clearAccessToken, createApiClient } from '../../lib/api/client'
import { AuthProvider } from './auth-context'
import { authApi } from './api'
import { RequireAuth } from './guards'
import { LoginPage, RegisterPage } from './pages'

function Location() { return <output data-testid="location">{useLocation().pathname}</output> }
function renderAuth(path: '/login' | '/register') {
  render(<AuthProvider mode="api"><MemoryRouter initialEntries={[path]}><Routes>
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

afterEach(() => { vi.restoreAllMocks(); clearAccessToken(); sessionStorage.removeItem('promptvault.api.session') })

describe('PostgreSQL-backed authentication mode', () => {
  it('uses the API response and bearer token for login', async () => {
    const login = vi.spyOn(authApi, 'login').mockResolvedValue({ user: { ...backendUser, role: 'admin' }, access_token: 'server-jwt', token_type: 'bearer', expires_in: 1800 })
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), backendUser.email)
    await user.type(screen.getByLabelText('Password'), 'User Demo 2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
    expect(login).toHaveBeenCalledWith({ email: backendUser.email, password: 'UserDemo2026!' })
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
    await createApiClient({ fetcher }).request('/api/v1/auth/me')
    expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer server-jwt' }) }))
    expect(sessionStorage.getItem('promptvault.demo.session')).toBeNull()
    expect(sessionStorage.getItem('promptvault.api.session')).toBe('server-jwt')
  })

  it('restores a saved session after a page refresh', async () => {
    sessionStorage.setItem('promptvault.api.session', 'saved-jwt')
    const me = vi.spyOn(authApi, 'me').mockResolvedValue(backendUser)
    render(<AuthProvider mode="api"><MemoryRouter initialEntries={['/dashboard']}><Routes>
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
    render(<AuthProvider mode="api"><MemoryRouter initialEntries={['/dashboard']}><Routes>
      <Route path="/login" element={<Location />} />
      <Route element={<RequireAuth />}><Route path="/dashboard" element={<Location />} /></Route>
    </Routes></MemoryRouter></AuthProvider>)

    expect(await screen.findByTestId('location')).toHaveTextContent('/login')
    expect(sessionStorage.getItem('promptvault.api.session')).toBeNull()
  })

  it('does not accept a demo-only password when the API rejects it', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new ApiClientError(401, { code: 'invalid_password', message: 'Incorrect password.' }))
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), backendUser.email)
    await user.type(screen.getByLabelText('Password'), 'User@123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect password.')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows when an email is absent from the database', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new ApiClientError(401, { code: 'email_not_found', message: 'Email address not found.' }))
    const user = userEvent.setup()
    renderAuth('/login')
    await user.type(screen.getByLabelText('Email address'), 'missing@example.com')
    await user.type(screen.getByLabelText('Password'), 'SomePassword2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email address not found.')
  })

  it('submits registration attributes and uses the new database identity', async () => {
    const register = vi.spyOn(authApi, 'register').mockResolvedValue({ user: { ...backendUser, id: '22222222-2222-4222-8222-222222222222', email: 'new@example.com', display_name: 'New User' }, access_token: 'new-jwt', token_type: 'bearer', expires_in: 1800 })
    const user = userEvent.setup()
    renderAuth('/register')
    await user.type(screen.getByLabelText('Display name'), 'New User')
    await user.type(screen.getByLabelText('Email address'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
    expect(register).toHaveBeenCalledWith({ display_name: 'New User', email: 'new@example.com', password: 'StrongPassword2026!' })
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
