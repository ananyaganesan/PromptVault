import { StrictMode } from 'react'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './auth-context'
import { authApi } from './api'

function SessionState() {
  const { user, restoring } = useAuth()
  return <p>{restoring ? 'restoring' : user?.email ?? 'signed out'}</p>
}

describe('AuthProvider session restoration', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps a valid session when Strict Mode aborts its first restoration request', async () => {
    sessionStorage.setItem('promptvault.api.session', 'valid-token')

    vi.stubGlobal('fetch', vi.fn((_url: string | URL | Request, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
      const signal = init?.signal
      signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
      if (!signal?.aborted) {
        queueMicrotask(() => resolve(new Response(JSON.stringify({
          id: 'user-id',
          email: 'user@promptvault.dev',
          display_name: 'Demo User',
          role: 'user',
          is_active: true,
          created_at: '2026-09-27T00:00:00Z',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
      }
    })))

    render(<StrictMode><AuthProvider><SessionState /></AuthProvider></StrictMode>)

    expect(await screen.findByText('user@promptvault.dev')).toBeInTheDocument()
    expect(sessionStorage.getItem('promptvault.api.session')).toBe('valid-token')
  })

  it('does not trust stored user details without a backend token', () => {
    sessionStorage.setItem('promptvault.api.session.user', JSON.stringify({ email: 'user@promptvault.dev' }))
    const me = vi.spyOn(authApi, 'me')
    render(<AuthProvider><SessionState /></AuthProvider>)
    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(me).not.toHaveBeenCalled()
  })
})
