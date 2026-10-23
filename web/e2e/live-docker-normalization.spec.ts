import { expect, test } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1' || process.env.E2E_PROVIDER_SIMULATION !== '1', 'Requires the isolated Gemini HTTP simulator.')
const apiBase = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1'

test('Docker frontend filters normalized versions by project and persists a Gemini execution', async ({ page, request }) => {
  const login = await request.post(`${apiBase}/auth/login`, {
    data: { email: 'admin@promptvault.dev', password: 'AdminDemo2026!' },
  })
  expect(login.status()).toBe(200)
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const key = await request.post(`${apiBase}/admin/provider-keys`, { headers, data: { provider: 'gemini', alias: `browser-${suffix}`, secret: 'simulation-key-not-a-real-credential' } })
  expect(key.status()).toBe(201)
  const keyId = (await key.json()).id
  const projects: { id: string; name: string }[] = []
  try {
    for (const label of ['Alpha', 'Beta']) {
      const created = await request.post(`${apiBase}/projects`, {
        headers, data: { name: `${label} Docker ${suffix}`, key: `${label.toLowerCase()}-${suffix}` },
      })
      expect(created.status()).toBe(201)
      const project = await created.json()
      projects.push(project)
      const prompt = await request.post(`${apiBase}/projects/${project.id}/prompts`, {
        headers, data: {
          name: `${label} reply`, key: `${label.toLowerCase()}-reply`,
          template_body: 'Hello {{name}}', commit_message: 'First normalized version',
          model_config: { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 },
        },
      })
      expect(prompt.status()).toBe(201)
      if (label === 'Alpha') {
        const initial = await prompt.json()
        const version = await request.post(`${apiBase}/prompts/${initial.id}/versions`, {
          headers, data: {
            parent_version_id: initial.latest_version.id, template_body: 'Welcome {{name}}',
            commit_message: 'Second normalized version', model_config: initial.latest_version.model_config,
          },
        })
        expect(version.status()).toBe(201)
      }
    }
    await page.goto('/login')
    await page.getByLabel('Email address').fill('admin@promptvault.dev')
    await page.getByLabel('Password', { exact: true }).fill('AdminDemo2026!')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await page.goto('/playground')
    const projectFilter = page.getByRole('combobox', { name: 'Project', exact: true })
    const versionFilter = page.getByRole('combobox', { name: 'Prompt version', exact: true })
    await expect(page.getByRole('combobox', { name: 'LLM provider', exact: true }).locator('option')).toHaveText(['gemini'])
    await projectFilter.selectOption(projects[0].id)
    await expect(versionFilter.locator('option')).toHaveCount(2)
    await expect(versionFilter).not.toContainText('beta-reply')
    await projectFilter.selectOption(projects[1].id)
    await expect(versionFilter.locator('option')).toHaveCount(1)
    await expect(versionFilter).toContainText('beta-reply')
    await expect(versionFilter).not.toContainText('alpha-reply')
    await page.reload()
    await expect(projectFilter).toHaveValue(projects[1].id)
    await page.locator('.playground textarea').first().fill('Docker demo')
    await expect(page.getByRole('button', { name: 'Run prompt' })).toBeEnabled()
    const response = page.waitForResponse((reply) => reply.url().endsWith('/api/v1/runs') && reply.request().method() === 'POST')
    await page.getByRole('button', { name: 'Run prompt' }).click()
    const recorded = await (await response).json()
    await expect(page.getByText('completed', { exact: true })).toBeVisible()
    await page.reload()
    await expect(projectFilter).toHaveValue(projects[1].id)
    const persisted = await request.get(`${apiBase}/runs/${recorded.id}`, { headers })
    expect(persisted.status()).toBe(200)
    expect(await persisted.json()).toMatchObject({
      id: recorded.id, project_id: projects[1].id, status: 'completed',
      input_variables: { name: 'Docker demo' },
    })
  } finally {
    for (const project of projects) {
      const removed = await request.delete(`${apiBase}/projects/${project.id}`, { headers })
      expect(removed.status()).toBe(204)
    }
    expect((await request.delete(`${apiBase}/admin/provider-keys/${keyId}`, { headers })).status()).toBe(204)
  }
})
