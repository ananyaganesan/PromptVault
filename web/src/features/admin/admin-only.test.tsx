import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/auth-context'
import { LoginPage } from '../auth/pages'
import { AdminOnly } from './admin-only'

function setup() { render(<AuthProvider><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/403" element={<p>Access denied</p>} /><Route element={<AdminOnly />}><Route path="/dashboard" element={<p>Admin console</p>} /><Route path="/admin" element={<p>Admin console</p>} /></Route></Routes></MemoryRouter></AuthProvider>) }

describe('admin route access', () => {
  it('denies the regular user', async () => {
    const user = userEvent.setup(); setup()
    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'User@123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
  })

  it('allows the Super Admin', async () => {
    const user = userEvent.setup(); setup()
    await user.type(screen.getByLabelText('Email address'), 'admin@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'Admin@123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Admin console')).toBeInTheDocument()
  })
})
