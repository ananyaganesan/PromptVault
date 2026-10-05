import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/auth-context'
import { LoginPage } from '../auth/pages'
import { AdminOnly } from './admin-only'

function setup() { render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/403" element={<p>Access denied</p>} /><Route element={<AdminOnly />}><Route path="/dashboard" element={<p>Admin console</p>} /><Route path="/admin" element={<p>Admin console</p>} /></Route></Routes></MemoryRouter></AuthProvider>) }

function mockSession(role: 'user' | 'admin') {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    access_token: `unit-${role}-token`,
    token_type: 'bearer',
    expires_in: 1800,
    user: {
      id: role === 'admin' ? 'usr_demo_admin' : 'usr_demo_user',
      email: `${role}@promptvault.dev`,
      display_name: role === 'admin' ? 'Demo Admin' : 'Demo User',
      role,
      is_active: true,
      created_at: '2026-09-27T00:00:00Z',
    },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
}

describe('admin route access', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.unstubAllGlobals()
  })

  it('denies the regular user', async () => {
    mockSession('user')
    const user = userEvent.setup(); setup()
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
  })

  it('allows the Super Admin', async () => {
    mockSession('admin')
    const user = userEvent.setup(); setup()
    await user.type(screen.getByLabelText('Email address'), 'admin@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'AdminDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Admin console')).toBeInTheDocument()
  })
})
