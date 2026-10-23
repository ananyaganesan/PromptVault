import { expect, test } from '@playwright/test'

test.skip(process.env.E2E_PROVIDER_SIMULATION !== '1', 'Requires tests/tools/gemini_http_simulation.py.')
const api = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8004/api/v1'

test('Gemini configuration creates an immutable version and quota errors stay visible', async ({ page, request }) => {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const session = await request.post(`${api}/auth/login`, { data: { email: 'admin@promptvault.dev', password: 'AdminDemo2026!' } })
  expect(session.status()).toBe(200)
  const headers = { Authorization: `Bearer ${(await session.json()).access_token}` }
  const key = await request.post(`${api}/admin/provider-keys`, { headers, data: { provider: 'gemini', alias: suffix, secret: 'simulation-key-not-a-real-credential' } })
  expect(key.status()).toBe(201)
  const keyId = (await key.json()).id
  const created = await request.post(`${api}/projects`, { headers, data: { name: `Gemini ${suffix}`, key: `gemini-${suffix}` } })
  expect(created.status()).toBe(201)
  const project = await created.json()
  try {
    const createdPrompt = await request.post(`${api}/projects/${project.id}/prompts`, { headers, data: {
      key: 'gemini-reply', name: 'Gemini reply', template_body: 'Hello {{name}}', commit_message: 'Initial',
      model_config: { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 },
    } })
    expect(createdPrompt.status()).toBe(201)
    const prompt = await createdPrompt.json()
    await page.goto('/login')
    await page.getByLabel('Email address').fill('admin@promptvault.dev')
    await page.getByLabel('Password', { exact: true }).fill('AdminDemo2026!')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await page.goto(`/playground?version=${prompt.latest_version.id}`)
    await expect(page.getByRole('combobox', { name: 'LLM provider', exact: true }).locator('option')).toHaveText(['gemini'])
    await page.getByLabel('Temperature').fill('0.2')
    await expect(page.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    await page.getByRole('button', { name: 'Save configuration' }).click()
    await expect(page.getByText('Configuration saved as version 2.')).toBeVisible()
    await page.reload()
    await page.getByRole('textbox', { name: /^name/ }).fill('Local user')
    const result = page.waitForResponse((reply) => reply.url().endsWith('/api/v1/runs') && reply.request().method() === 'POST')
    await page.getByRole('button', { name: 'Run prompt' }).click()
    expect((await result).status()).toBe(201)
    await expect(page.getByText('Simulated gemini output for local acceptance')).toBeVisible()
    await page.getByRole('textbox', { name: /^name/ }).fill('quota-test')
    await page.getByRole('button', { name: 'Run prompt' }).click()
    await expect(page.getByText('Provider free-tier quota reached. Try again later.').first()).toBeVisible()
  } finally {
    expect((await request.delete(`${api}/projects/${project.id}`, { headers })).status()).toBe(204)
    expect((await request.delete(`${api}/admin/provider-keys/${keyId}`, { headers })).status()).toBe(204)
  }
})
