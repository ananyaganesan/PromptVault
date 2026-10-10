import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { databaseRows } from './support/database'

test.skip(process.env.E2E_LIVE !== '1' || !process.env.E2E_DATABASE_URL, 'Requires a live isolated stack and E2E_DATABASE_URL.')
test.setTimeout(120_000)
const api = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const model = { provider: 'mock', model: 'deterministic-v1', temperature: 0, max_output_tokens: 100 }
const suffix = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`

async function signIn(page: Page, role: 'user' | 'admin' = 'user') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'user' ? 'UserDemo2026!' : 'AdminDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  return (await page.evaluate(() => sessionStorage.getItem('promptvault.api.session')))!
}
async function refresh(page: Page) {
  await page.getByRole('button', { name: 'Refresh data', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Refresh data', exact: true })).toBeEnabled()
}
async function fixture(request: APIRequestContext, jwt: string, key: string) {
  const headers = { Authorization: `Bearer ${jwt}` }
  const projectResponse = await request.post(`${api}/projects`, { headers, data: { name: `Audit ${key}`, key: `audit-${key}` } })
  expect(projectResponse.status()).toBe(201)
  const project = await projectResponse.json()
  const promptResponse = await request.post(`${api}/projects/${project.id}/prompts`, { headers, data: {
    name: `Reply ${key}`, key: `reply-${key}`, template_body: 'Answer {{message}}.', model_config: model, commit_message: 'Initial',
  } })
  expect(promptResponse.status()).toBe(201)
  return { project, prompt: await promptResponse.json(), headers }
}

test('project/version mutations, cross-user refresh, lineage and revoked membership match PostgreSQL', async ({ page, request, browser }) => {
  const key = suffix()
  const jwt = await signIn(page)
  await page.goto('/projects/new')
  await page.getByLabel('Project name').fill(`Audit ${key}`)
  await page.getByLabel('Project key').fill(`audit-${key}`)
  await page.getByRole('button', { name: 'Create project' }).click()
  await expect(page.getByRole('heading', { name: `Audit ${key}` })).toBeVisible()
  const projectId = page.url().split('/').at(-1)!
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  const updatedName = `Updated ${key}`
  await page.getByLabel('Project name').fill(updatedName)
  await page.getByRole('button', { name: 'Save settings' }).click()
  await expect(page.getByRole('heading', { name: updatedName })).toBeVisible()
  expect(databaseRows('SELECT name, key, member_count FROM (SELECT p.*, (SELECT count(*) FROM project_members m WHERE m.project_id=p.id) member_count FROM projects p) q WHERE id=%s', [projectId])[0]).toMatchObject({ name: updatedName, key: `audit-${key}`, member_count: 1 })
  await page.getByRole('link', { name: 'Projects', exact: true }).click()
  await page.getByRole('textbox', { name: 'Search projects' }).fill(key)
  await refresh(page)
  await expect(page.getByRole('textbox', { name: 'Search projects' })).toHaveValue(key)
  await expect(page.getByRole('heading', { name: updatedName })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: updatedName })).toBeVisible()

  const email = `audit-member-${key}@example.com`
  const registration = await request.post(`${api}/auth/register`, { data: { display_name: `Member ${key}`, email, password: 'AuditMemberPassword2026!' } })
  expect(registration.status()).toBe(201)
  const memberSession = await registration.json()
  const ownerHeaders = { Authorization: `Bearer ${jwt}` }
  expect((await request.post(`${api}/projects/${projectId}/members`, { headers: ownerHeaders, data: { email } })).status()).toBe(201)
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173' })
  const member = await context.newPage()
  try {
    await member.goto('/login')
    await member.evaluate((token) => sessionStorage.setItem('promptvault.api.session', token), memberSession.access_token)
    await member.goto(`/projects/${projectId}`)
    await expect(member.getByRole('heading', { name: updatedName })).toBeVisible()
    await page.goto(`/prompts/new?project=${projectId}`)
    await page.getByLabel('Prompt key').fill(`reply-${key}`)
    await page.getByLabel('Prompt name').fill(`Reply ${key}`)
    await page.getByRole('textbox', { name: 'Template', exact: true }).fill('Answer {{message}}.')
    await page.getByRole('button', { name: 'Create prompt' }).click()
    await expect(page.getByRole('heading', { name: `Reply ${key}` })).toBeVisible()
    const promptId = page.url().split('/').at(-1)!
    await page.getByRole('textbox', { name: 'Prompt template' }).fill('Answer {{message}} clearly.')
    await page.getByLabel('Commit message').fill('Clarify response')
    await page.getByRole('button', { name: 'Save new version' }).click()
    await expect(page.getByText('Version 2 was saved as an immutable snapshot.')).toBeVisible()
    await expect(page.getByRole('link', { name: /v2 Current/ })).toBeVisible()
    const versions = databaseRows('SELECT id, version_number, parent_version_id, template_body FROM prompt_versions WHERE prompt_id=%s ORDER BY version_number', [promptId])
    expect(versions.map((row) => row.version_number)).toEqual([1, 2])
    expect(versions[1].parent_version_id).toBe(versions[0].id)
    expect((await request.post(`${api}/prompts/${promptId}/versions`, { headers: { Authorization: `Bearer ${memberSession.access_token}` }, data: {
      parent_version_id: versions[1].id, template_body: 'Answer {{message}} with next steps.', model_config: model, commit_message: 'Member adds next steps',
    } })).status()).toBe(201)
    await refresh(page)
    await expect(page.getByRole('link', { name: /v3 Current/ })).toBeVisible()
    await page.getByRole('link', { name: /v3 Current/ }).click()
    await expect(page.getByLabel('Template snapshot')).toHaveValue('Answer {{message}} with next steps.')
    await page.getByRole('button', { name: 'Compare versions' }).click()
    await expect(page.getByLabel('Template snapshot').nth(0)).toHaveValue('Answer {{message}} clearly.')
    await expect(page.getByLabel('Template snapshot').nth(1)).toHaveValue('Answer {{message}} with next steps.')
    await page.reload()
    await expect(page.getByLabel('Template snapshot').nth(1)).toHaveValue('Answer {{message}} with next steps.')
    const latest = databaseRows('SELECT id FROM prompt_versions WHERE prompt_id=%s ORDER BY version_number DESC LIMIT 1', [promptId])[0]
    await page.goto(`/versions/${latest.id}/lineage`)
    await expect(page.getByText(/descends through 2 earlier versions/)).toBeVisible()
    await page.reload()
    await expect(page.locator('.version-row')).toHaveCount(3)

    expect((await request.delete(`${api}/projects/${projectId}/members/${memberSession.user.id}`, { headers: ownerHeaders })).status()).toBe(204)
    await refresh(member)
    await expect(member.getByText('Project not found', { exact: true })).toBeVisible()
    expect((await request.get(`${api}/projects/${projectId}`, { headers: { Authorization: `Bearer ${memberSession.access_token}` } })).status()).toBe(404)
    expect((await request.get(`${api}/versions/${latest.id}`, { headers: { Authorization: `Bearer ${memberSession.access_token}` } })).status()).toBe(404)
  } finally { await context.close() }
})

test('mock runs, counts and timestamps reconcile; refresh and retry preserve page and filters', async ({ page, request }) => {
  const jwt = await signIn(page)
  const { project, prompt, headers } = await fixture(request, jwt, suffix())
  await page.reload()
  await page.goto(`/playground?version=${prompt.latest_version.id}`)
  await page.locator('.playground textarea').first().fill('Freshness check')
  await page.getByRole('button', { name: 'Run prompt' }).click()
  await page.getByRole('link', { name: 'View run details →' }).click()
  const runId = page.url().split('/').at(-1)!
  const row = databaseRows('SELECT status, output_text, prompt_tokens, completion_tokens, latency_ms, created_at FROM runs WHERE id=%s', [runId])[0]
  expect(row.status).toBe('completed')
  await expect(page.locator('.output-copy')).toHaveText(String(row.output_text))
  const apiRun = await (await request.get(`${api}/runs/${runId}`, { headers })).json()
  expect(new Date(String(row.created_at)).getTime()).toBe(new Date(apiRun.created_at).getTime())
  expect(apiRun.prompt_tokens).toBe(row.prompt_tokens)
  expect(apiRun.completion_tokens).toBe(row.completion_tokens)
  expect(apiRun.latency_ms).toBe(row.latency_ms)
  await page.reload()
  await expect(page.locator('.output-copy')).toHaveText(String(row.output_text))
  for (let index = 0; index < 11; index += 1) {
    expect((await request.post(`${api}/runs`, { headers, data: { version_id: prompt.latest_version.id, variables: { message: `Run ${index}` } } })).status()).toBe(201)
  }
  await page.goto('/runs')
  await page.getByLabel('Run project').selectOption(project.id)
  await page.getByLabel('Run status').selectOption('completed')
  await page.getByLabel('Run period').selectOption('all')
  await page.getByLabel('Run model').fill(model.model)
  await expect(page.locator('.run-pagination')).toContainText('12 runs · page 1')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.locator('.run-pagination')).toContainText('page 2')
  await refresh(page)
  await expect(page.locator('.run-pagination')).toContainText('12 runs · page 2')
  await expect(page.getByLabel('Run project')).toHaveValue(project.id)
  await expect(page.getByLabel('Run model')).toHaveValue(model.model)
  await expect(page.locator('tbody tr')).toHaveCount(2)

  let failed = false
  await page.route('**/api/v1/runs?**', async (route) => {
    if (!failed) { failed = true; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'unavailable', message: 'Temporary acceptance-test outage' }) }) }
    else await route.continue()
  })
  await refresh(page)
  await expect(page.getByRole('alert')).toContainText('Temporary acceptance-test outage')
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.locator('.run-pagination')).toContainText('12 runs · page 2')
  await expect(page.getByLabel('Run status')).toHaveValue('completed')
  await expect(page.getByLabel('Run period')).toHaveValue('all')
  await page.unroute('**/api/v1/runs?**')
  await page.goto('/dashboard')
  const actor = await (await request.get(`${api}/auth/me`, { headers })).json()
  const total = databaseRows("SELECT count(*) count FROM runs WHERE user_id=%s AND created_at>=date_trunc('month',now()) AND created_at<date_trunc('month',now())+interval '1 month'", [actor.id])[0].count
  await expect(page.locator('.stat').filter({ has: page.getByText('YOUR RUNS', { exact: true }) }).locator('strong')).toHaveText(String(total))
  const recent = databaseRows('SELECT id FROM runs WHERE user_id=%s ORDER BY created_at DESC,id DESC LIMIT 4', [actor.id])
  await expect(page.locator('.activity')).toHaveCount(4)
  expect(await page.locator('.activity').evaluateAll((links) => links.map((link) => link.getAttribute('href')))).toEqual(recent.map((run) => `/runs/${run.id}`))
})

test('approval evidence, active deployment and token revocation refresh across users and persist', async ({ page, request, browser }) => {
  const jwt = await signIn(page)
  const { project, prompt, headers } = await fixture(request, jwt, suffix())
  const run = await (await request.post(`${api}/runs`, { headers, data: { version_id: prompt.latest_version.id, variables: { message: 'Approval evidence' } } })).json()
  await page.reload()
  await page.goto('/deployments/new')
  await page.getByLabel('Prompt version').selectOption(prompt.latest_version.id)
  await page.getByLabel('Environment').selectOption('production')
  await page.getByLabel('Deployment note').fill('Audit approval')
  await page.getByRole('button', { name: 'Request approval' }).click()
  await expect(page.getByText('Pending approval', { exact: true }).first()).toBeVisible()
  const deploymentId = page.url().split('/').at(-1)!
  const adminContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173' })
  const admin = await adminContext.newPage()
  try {
    await signIn(admin, 'admin')
    await admin.goto('/admin/approvals')
    await admin.getByRole('link', { name: `${prompt.key} v1 → Production`, exact: true }).click()
    await expect(admin.getByRole('link', { name: new RegExp(`${prompt.key} · v1`) })).toHaveAttribute('href', `/runs/${run.id}`)
    await admin.getByLabel('Review note').fill('Verified persisted run')
    await admin.getByRole('button', { name: 'Approve production', exact: true }).click()
    await admin.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click()
    await expect(admin.getByText('Active', { exact: true }).first()).toBeVisible()
    await admin.goto('/admin/approvals')
    await expect(admin.getByRole('row').filter({ hasText: prompt.key })).toHaveCount(0)
    await refresh(page)
    await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()
    await page.reload()
    await expect(page.getByText('Active', { exact: true }).first()).toBeVisible()
    expect(databaseRows('SELECT status, version_id, reviewed_at FROM deployments WHERE id=%s', [deploymentId])[0]).toMatchObject({ status: 'active', version_id: prompt.latest_version.id, reviewed_at: expect.any(String) })
    await page.goto(`/projects/${project.id}`)
    await expect(page.getByText(/^Active: .*production/)).toBeVisible()
    await page.goto('/deployments')
    await page.getByLabel('Deployment project').selectOption(project.id)
    await page.getByLabel('Deployment environment').selectOption('production')
    await page.getByLabel('Deployment status').selectOption('active')
    await refresh(page)
    await expect(page.getByRole('row').filter({ hasText: prompt.key })).toContainText('Active')
    await expect(page.getByLabel('Deployment project')).toHaveValue(project.id)
    await page.goto('/api-tokens')
    const tokenName = `Consumer ${suffix()}`
    await page.getByRole('button', { name: 'Issue token', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Issue API token' })
    await dialog.getByPlaceholder('e.g. Production consumer').fill(tokenName)
    await dialog.getByLabel('Project').selectOption(project.id)
    await dialog.getByRole('button', { name: 'Issue token' }).click()
    await page.getByRole('button', { name: 'I saved it' }).click()
    const tokenRow = page.getByRole('row').filter({ hasText: tokenName })
    await expect(tokenRow).toContainText('Active')
    await page.reload()
    await expect(page.getByLabel('New API token')).toHaveCount(0)
    await tokenRow.getByRole('button', { name: 'Revoke' }).click()
    await page.getByRole('dialog', { name: 'Revoke API token' }).getByRole('button', { name: 'Confirm' }).click()
    await expect(tokenRow).toContainText('Revoked')
    expect(databaseRows('SELECT revoked_at FROM api_tokens WHERE project_id=%s AND name=%s', [project.id, tokenName])[0].revoked_at).not.toBeNull()
    await page.reload()
    await expect(tokenRow).toContainText('Revoked')
    const externalName = `External ${suffix()}`
    const external = await (await request.post(`${api}/api-tokens`, { headers, data: { project_id: project.id, name: externalName } })).json()
    await refresh(page)
    await expect(page.getByRole('row').filter({ hasText: externalName })).toContainText('Active')
    expect((await request.delete(`${api}/api-tokens/${external.id}`, { headers })).status()).toBe(204)
    await refresh(page)
    await expect(page.getByRole('row').filter({ hasText: externalName })).toContainText('Revoked')
  } finally { await adminContext.close() }
})
