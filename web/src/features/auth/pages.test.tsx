import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from './pages'
import { AuthProvider } from './auth-context'

function Location() { return <output data-testid="location">{useLocation().pathname}</output> }

function renderLogin() {
  return render(<AuthProvider mode="demo"><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<Location />} /><Route path="/admin" element={<Location />} /></Routes></MemoryRouter></AuthProvider>)
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
    expect(sessionStorage.getItem('promptvault.session.token')).toBe('live-user-token')
  })

  it('maps the backend admin role to the Super Admin workspace', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', mockJson(session('admin')))
    renderLogin()

    await user.type(screen.getByLabelText('Email address'), 'admin@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'AdminDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/admin')
  })

  it('shows the relevant login error for a missing email or wrong password', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.type(screen.getByLabelText('Email address'), 'missing@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'WrongPassword2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email address not found.')

    await user.clear(screen.getByLabelText('Email address'))
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect password.')
  })
})
