import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { LoginPage } from './pages'
import { AuthProvider } from './auth-context'

function Location() { return <output data-testid="location">{useLocation().pathname}</output> }

function renderLogin() {
  return render(<AuthProvider mode="demo"><MemoryRouter initialEntries={['/login']}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/dashboard" element={<Location />} /><Route path="/admin" element={<Location />} /></Routes></MemoryRouter></AuthProvider>)
}

describe('LoginPage', () => {
  it('blocks an empty sign-in attempt', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByText('Email address is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
  })

  it('redirects the demo user to the workspace', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email address'), 'user@promptvault.dev')
    await user.type(screen.getByLabelText('Password'), 'UserDemo2026!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
  })

  it('redirects the demo Super Admin to administration', async () => {
    const user = userEvent.setup()
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
