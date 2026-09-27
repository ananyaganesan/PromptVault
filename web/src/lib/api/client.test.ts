import { describe, expect, it, vi } from 'vitest'
import { createApiClient } from './client'

describe('api client', () => {
  it('adds query parameters, JSON headers, and a bearer token', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'project_1' }), { headers: { 'Content-Type': 'application/json' } }))
    const client = createApiClient({ baseUrl: 'https://api.example.test', getAccessToken: () => 'demo-token', fetcher })

    await client.request<{ id: string }>('/projects', { method: 'POST', body: { name: 'Checkout' }, query: { page: 2, search: 'checkout' } })

    expect(fetcher).toHaveBeenCalledWith('https://api.example.test/projects?page=2&search=checkout', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ name: 'Checkout' }),
      headers: expect.objectContaining({ Authorization: 'Bearer demo-token', 'Content-Type': 'application/json' }),
    }))
  })

  it('throws a typed error for the documented error envelope', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'forbidden', message: 'Access denied', request_id: 'req_123' }), { status: 403, headers: { 'Content-Type': 'application/json' } }))
    const client = createApiClient({ fetcher })

    await expect(client.request('/admin/users')).rejects.toMatchObject({ code: 'forbidden', status: 403, requestId: 'req_123' })
  })

  it('invalidates the session only when an authenticated request returns 401', async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ code: 'unauthorized', message: 'Session expired' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })))
    const onUnauthorized = vi.fn()
    const client = createApiClient({ getAccessToken: () => 'expired-token', fetcher, onUnauthorized })

    await expect(client.request('/projects')).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)

    await expect(client.request('/auth/login', { method: 'POST', auth: false })).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })
})
