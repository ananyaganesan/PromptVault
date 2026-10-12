import { expect, test } from '@playwright/test'
import { databaseRows } from './support/database'

// This suite stores dummy keys. Run only against run-provider-simulation.py.
test.skip(process.env.E2E_PROVIDER_SIMULATION !== '1', 'Requires the isolated provider HTTP simulator.')
const api = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8004/api/v1'

test.beforeAll(() => {
  expect(String(databaseRows('SELECT current_database() AS name')[0].name)).toMatch(/_test$/)
})

for (const provider of ['gemini', 'openrouter', 'groq']) {
  test(`${provider}: configure immutable version, run and reconcile output`, async ({ page, request }) => {
    const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const admin = await request.post(`${api}/auth/login`, { data: { email: 'admin@promptvault.dev', password: 'AdminDemo2026!' } })
    expect(admin.status()).toBe(200)
    const adminHeaders = { Authorization: `Bearer ${(await admin.json()).access_token}` }
    expect((await request.post(`${api}/admin/provider-keys`, { headers: adminHeaders, data: { provider, alias: `simulated-${suffix}`, secret: 'simulation-key-not-a-real-credential' } })).status()).toBe(201)
    await page.goto('/login')
    await page.getByLabel('Email address').fill('user@promptvault.dev')
    await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    const token = await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))
    const headers = { Authorization: `Bearer ${token}` }
    const project = await request.post(`${api}/projects`, { headers, data: { name: `Provider ${suffix}`, key: `provider-${suffix}` } })
    expect(project.status()).toBe(201)
    const projectId = (await project.json()).id
    const prompt = await request.post(`${api}/projects/${projectId}/prompts`, { headers, data: {
      key: `text-${suffix}`, name: `Text ${suffix}`, template_body: 'Hello {{name}}', commit_message: 'Initial local fixture',
      model_config: { provider: 'mock', model: 'deterministic-v1', max_output_tokens: 100, temperature: 0 },
    } })
    expect(prompt.status()).toBe(201)
    const original = await prompt.json()
    await page.goto(`/playground?version=${original.latest_version.id}`)
    await page.getByLabel('LLM provider').selectOption(provider)
    await expect(page.getByRole('button', { name: 'Run prompt' })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Save configuration' })).toBeEnabled()
    await page.getByRole('button', { name: 'Save configuration' }).click()
    await expect(page.getByText('Configuration saved as version 2.')).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('LLM provider')).toHaveValue(provider)
    await expect(page.getByRole('button', { name: 'Run prompt' })).toBeEnabled()
    await page.getByRole('textbox', { name: /^name/ }).fill('Local user')
    await page.getByRole('button', { name: 'Run prompt' }).click()
    await expect(page.getByText(`Simulated ${provider} output for local acceptance`)).toBeVisible()
    const link = page.getByRole('link', { name: 'View run details →' })
    const runId = (await link.getAttribute('href'))!.split('/').at(-1)
    expect(databaseRows('SELECT provider, output_text, prompt_tokens, completion_tokens, cost FROM runs WHERE id=%s', [runId])[0]).toMatchObject({ provider, output_text: `Simulated ${provider} output for local acceptance`, prompt_tokens: 7, completion_tokens: 3, cost: '0.000000' })
    const versions = databaseRows('SELECT model_config, parent_version_id FROM prompt_versions WHERE prompt_id=%s ORDER BY version_number', [original.id])
    expect(versions).toHaveLength(2)
    expect(versions[0].model_config).toMatchObject({ provider: 'mock' })
    expect(versions[1].model_config).toMatchObject({ provider })
    expect(versions[1].parent_version_id).toBe(original.latest_version.id)
    if (provider === 'groq' && test.info().project.name === 'desktop-chrome') {
      await page.screenshot({ path: '../evidence/a1/playground-groq.png', fullPage: true })
      await page.getByRole('textbox', { name: /^name/ }).fill('quota-test')
      await page.getByRole('button', { name: 'Run prompt' }).click()
      await expect(page.getByText('Provider free-tier quota reached. Try again later.')).toBeVisible()
    } else {
      await link.click()
      await expect(page.getByText(`Simulated ${provider} output for local acceptance`)).toBeVisible()
      await page.reload()
      await expect(page.getByText(`Simulated ${provider} output for local acceptance`)).toBeVisible()
    }
  })
}
