import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')
test.setTimeout(90_000)

const apiBase = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const serveBase = apiBase.replace(/\/api\/v1$/, '')

async function signIn(page: Page, role: 'user' | 'admin') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'admin' ? 'AdminDemo2026!' : 'UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

async function switchAccount(page: Page, role: 'user' | 'admin') {
  await page.evaluate(() => sessionStorage.clear())
  await page.reload()
  await signIn(page, role)
}

async function createVersionedPrompt(request: APIRequestContext, token: string, suffix: string) {
  const headers = { Authorization: `Bearer ${token}` }
  const projectResponse = await request.post(`${apiBase}/projects`, {
    headers,
    data: { name: `Release Project ${suffix}`, key: `release-project-${suffix}`, description: 'Live deployment acceptance project.' },
  })
  expect(projectResponse.ok()).toBeTruthy()
  const project = await projectResponse.json()
  const promptResponse = await request.post(`${apiBase}/projects/${project.id}/prompts`, {
    headers,
    data: {
      key: `release-reply-${suffix}`,
      name: `Release Reply ${suffix}`,
      description: 'Prompt used for the deployment lifecycle.',
      template_body: 'Reply to {{message}} with version one.',
      model_config: { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 },
      commit_message: 'Version one',
    },
  })
  expect(promptResponse.ok()).toBeTruthy()
  const prompt = await promptResponse.json()
  let parent = prompt.latest_version
  for (const versionNumber of [2, 3]) {
    const response = await request.post(`${apiBase}/prompts/${prompt.id}/versions`, {
      headers,
      data: {
        parent_version_id: parent.id,
        template_body: `Reply to {{message}} with version ${versionNumber}.`,
        model_config: { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 },
        commit_message: `Version ${versionNumber}`,
      },
    })
    expect(response.ok()).toBeTruthy()
    parent = await response.json()
  }
  return { project, prompt, version: parent }
}

test('production approval, Serve token, rollback, and revocation use the live control plane', async ({ page, request }) => {
  const suffix = Date.now().toString(36)
  const tokenName = `Release consumer ${suffix}`
  await signIn(page, 'user')
  const jwt = await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))
  expect(jwt).toBeTruthy()
  const fixture = await createVersionedPrompt(request, jwt!, suffix)
  await switchAccount(page, 'user')

  await page.goto('/deployments/new')
  await page.getByLabel('Prompt version').selectOption(fixture.version.id)
  await page.getByLabel('Environment').selectOption('staging')
  await page.getByLabel('Deployment note').fill('Validate the live staging path.')
  await page.getByRole('button', { name: 'Create deployment' }).click()
  await expect(page).toHaveURL(/\/deployments\/[0-9a-f-]+$/)
  await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByText('Staging', { exact: true }).first()).toBeVisible()
  await page.goto('/deployments')
  await page.getByLabel('Deployment project').selectOption(fixture.project.id)
  await expect(page.getByRole('row').filter({ hasText: fixture.prompt.key })).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(1)

  await page.goto('/deployments/new')
  await page.getByLabel('Prompt version').selectOption(fixture.version.id)
  await page.getByLabel('Environment').selectOption('production')
  await page.getByLabel('Deployment note').fill('Ready for production approval.')
  await page.getByRole('button', { name: 'Request approval' }).click()
  await expect(page.getByText('Pending approval', { exact: true }).first()).toBeVisible()
  const approvalId = page.url().split('/').at(-1)!

  await page.goto('/api-tokens')
  await page.getByRole('button', { name: 'Issue token' }).click()
  const issueDialog = page.getByRole('dialog', { name: 'Issue API token' })
  await issueDialog.getByPlaceholder('e.g. Production consumer').fill(tokenName)
  await issueDialog.locator('select').selectOption(fixture.project.id)
  await issueDialog.getByRole('button', { name: 'Issue token' }).click()
  const runtimeToken = await page.getByLabel('New API token').inputValue()
  expect(runtimeToken).toMatch(/^pv_live_/)
  await page.getByRole('button', { name: 'I saved it' }).click()
  await expect(page.getByRole('row').filter({ hasText: tokenName })).toBeVisible()

  await switchAccount(page, 'admin')
  await page.goto(`/admin/approvals/${approvalId}`)
  await expect(page.getByRole('heading', { name: new RegExp(`${fixture.prompt.key} v3`) })).toBeVisible()
  await page.getByLabel('Review note').fill('Live release evidence verified.')
  await page.getByRole('button', { name: 'Approve production' }).click()
  await page.getByRole('dialog', { name: 'Approve production deployment' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()

  const servedV3 = await request.get(`${serveBase}/serve/v1/prompts/${fixture.prompt.key}?env=prod`, {
    headers: { Authorization: `Bearer ${runtimeToken}` },
  })
  expect(servedV3.ok()).toBeTruthy()
  expect((await servedV3.json()).version.version_number).toBe(3)

  await page.goto('/admin/rollback')
  const activeSelect = page.getByLabel('Active deployment')
  const activeOption = activeSelect.locator('option').filter({ hasText: `${fixture.prompt.key} · production v3` })
  await activeSelect.selectOption(await activeOption.getAttribute('value') ?? '')
  const restoreSelect = page.getByLabel('Restore version')
  const restoreOption = restoreSelect.locator('option').filter({ hasText: 'v2 · Version 2' })
  await restoreSelect.selectOption(await restoreOption.getAttribute('value') ?? '')
  await page.getByLabel('Rollback reason').fill('Restore the previously verified prompt.')
  await page.getByRole('button', { name: 'Review rollback' }).click()
  await page.getByRole('dialog', { name: 'Confirm rollback' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(page).toHaveURL(/\/deployments\/[0-9a-f-]+$/)
  await expect(page.getByText('v2', { exact: true }).first()).toBeVisible()

  const servedV2 = await request.get(`${serveBase}/serve/v1/prompts/${fixture.prompt.key}?env=prod`, {
    headers: { Authorization: `Bearer ${runtimeToken}` },
  })
  expect(servedV2.ok()).toBeTruthy()
  expect((await servedV2.json()).version.version_number).toBe(2)

  await switchAccount(page, 'user')
  await page.goto('/api-tokens')
  const tokenRow = page.getByRole('row').filter({ hasText: tokenName })
  await tokenRow.getByRole('button', { name: 'Revoke' }).click()
  await page.getByRole('dialog', { name: 'Revoke API token' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(tokenRow.getByText('Revoked', { exact: true })).toBeVisible()
  const revoked = await request.get(`${serveBase}/serve/v1/prompts/${fixture.prompt.key}?env=prod`, {
    headers: { Authorization: `Bearer ${runtimeToken}` },
  })
  expect(revoked.status()).toBe(401)
})
