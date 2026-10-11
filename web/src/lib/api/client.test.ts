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

  it('forwards an idempotency key without replacing authentication headers', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'run_1' }), { headers: { 'Content-Type': 'application/json' } }))
    const client = createApiClient({ baseUrl: 'https://api.example.test', getAccessToken: () => 'demo-token', fetcher })

    await client.request('/runs', {
      method: 'POST',
      body: { version_id: 'version_1', variables: {} },
      headers: { 'Idempotency-Key': 'execution-request-0001' },
    })

    expect(fetcher).toHaveBeenCalledWith('https://api.example.test/runs', expect.objectContaining({
      headers: expect.objectContaining({
        Authorization: 'Bearer demo-token',
        'Idempotency-Key': 'execution-request-0001',
      }),
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

  it('keeps a newer session when an older request returns 401', async () => {
    let resolveRequest!: (response: Response) => void
    const fetcher = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { resolveRequest = resolve }))
    let token = 'old-token'
    const onUnauthorized = vi.fn()
    const client = createApiClient({ getAccessToken: () => token, fetcher, onUnauthorized })

    const request = client.request('/projects')
    token = 'new-token'
    resolveRequest(new Response(JSON.stringify({ code: 'unauthorized', message: 'Expired' }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    }))

    await expect(request).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
