import { invitationLink } from './support/invitations'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { databaseRows } from './support/database'
import { createVerifiedTestAccount } from './support/auth'

test.skip(process.env.E2E_LIVE !== '1' || !process.env.E2E_DATABASE_URL, 'Requires a live isolated stack and E2E_DATABASE_URL.')
test.setTimeout(120_000)
const api = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000/api/v1'
const model = { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 100 }
const suffix = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`

test.beforeAll(() => {
  // This suite creates accounts and workflow records; require an isolated database.
  const name = databaseRows('SELECT current_database() AS name')[0].name
  expect(String(name), 'Freshness acceptance requires a database ending in _test').toMatch(/_test$/)
})

async function signIn(page: Page, role: 'user' | 'admin' = 'user') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'user' ? 'UserDemo2026!' : 'AdminDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  return (await page.evaluate(() => sessionStorage.getItem('promptvault.api.session')))!
}
async function refresh(page: Page) {
  await page.reload()
}
async function fixture(request: APIRequestContext, jwt: string, key: string) {
  const headers = { Authorization: `Bearer ${jwt}` }
  const projectResponse = await request.post(`${api}/projects`, { headers, data: { name: `Audit ${key}`, key: `audit-${key}` } })
  expect(projectResponse.status()).toBe(201)
  const project = await projectResponse.json()
  // Detect accidentally pairing an API with a different SQL database immediately.
  expect(databaseRows('SELECT id FROM projects WHERE id=%s', [project.id])).toHaveLength(1)
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
  const navigation = page.getByRole('button', { name: 'Open navigation', exact: true })
  if (await navigation.isVisible()) {
    await navigation.click()
    await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Projects', exact: true }).click()
  } else {
    await page.getByRole('link', { name: 'Projects', exact: true }).click()
  }
  await page.getByRole('textbox', { name: 'Search projects' }).fill(key)
  await refresh(page)
  await expect(page.getByRole('textbox', { name: 'Search projects' })).toHaveValue(key)
  await expect(page.getByRole('heading', { name: updatedName })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: updatedName })).toBeVisible()

  const memberAccount = await createVerifiedTestAccount(request, `audit-member-${key}`)
  const email = memberAccount.email
  const memberSession = memberAccount.session
  const ownerHeaders = { Authorization: `Bearer ${jwt}` }
  expect((await request.post(`${api}/projects/${projectId}/members`, { headers: ownerHeaders, data: { email } })).status()).toBe(201)
  const invitationToken = new URLSearchParams(new URL(invitationLink(email, updatedName)).hash.slice(1)).get('token')!
  expect((await request.post(`${api}/project-invitations/accept`, { headers: { Authorization: `Bearer ${memberSession.access_token}` }, data: { token: invitationToken } })).status()).toBe(200)
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
    await page.getByLabel('Prompt template').fill('My unsaved {{message}} draft')
    await page.getByLabel('Commit message').fill('Unsaved explanation')
    expect((await request.post(`${api}/prompts/${promptId}/versions`, { headers: { Authorization: `Bearer ${memberSession.access_token}` }, data: {
      parent_version_id: versions[1].id, template_body: 'Answer {{message}} with next steps.', model_config: model, commit_message: 'Member adds next steps',
    } })).status()).toBe(201)
    await refresh(page)
    await expect(page.getByRole('link', { name: /v3 Current/ })).toBeVisible()
    await expect(page.getByLabel('Prompt template')).toHaveValue('My unsaved {{message}} draft')
    await expect(page.getByLabel('Commit message')).toHaveValue('Unsaved explanation')
    await expect(page.getByRole('button', { name: 'Save new version' })).toBeDisabled()
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
    expect((await request.get(`${api}/projects/${projectId}`, { headers: { Authorization: `Bearer ${memberSession.access_token}` } })).status()).toBe(403)
    expect((await request.get(`${api}/versions/${latest.id}`, { headers: { Authorization: `Bearer ${memberSession.access_token}` } })).status()).toBe(404)
  } finally { await context.close() }
})

async function reconcilePages(request: APIRequestContext, headers: Record<string, string>, path: string, sql: string, parameters: unknown[] = []) {
  const expected = databaseRows(sql, parameters).map((row) => row.id).sort()
  const ids: string[] = []
  for (let number = 1; ; number += 1) {
    const response = await request.get(`${api}${path}`, { headers, params: { page: number, page_size: 25 } })
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data.total).toBe(expected.length)
    expect(data.page).toBe(number)
    ids.push(...data.items.map((item: { id: string }) => item.id))
    if (ids.length >= data.total) break
    expect(data.items).toHaveLength(25)
  }
  expect(ids.sort()).toEqual(expected)
  expect(new Set(ids).size).toBe(ids.length)
}

test('records beyond 100 reconcile across projects, versions, runs, approvals and active deployments', async ({ page, request, browser }) => {
  test.setTimeout(240_000)
  const jwt = await signIn(page)
  const headers = { Authorization: `Bearer ${jwt}` }
  const actor = await (await request.get(`${api}/auth/me`, { headers })).json()
  const key = suffix()
  let first: Awaited<ReturnType<typeof fixture>> | undefined
  for (let index = 0; index < 101; index += 1) {
    const item = await fixture(request, jwt, `${key}-${index}`)
    first ??= item
    for (const environment of ['dev', 'prod']) {
      expect((await request.post(`${api}/deployments`, { headers, data: { version_id: item.prompt.latest_version.id, environment } })).status()).toBe(201)
    }
    expect((await request.post(`${api}/runs`, { headers, data: { version_id: item.prompt.latest_version.id, variables: { message: `Boundary ${index}` } } })).status()).toBe(201)
  }
  const { project, prompt } = first!
  let parent = prompt.latest_version.id
  for (let number = 2; number <= 101; number += 1) {
    const response = await request.post(`${api}/prompts/${prompt.id}/versions`, { headers, data: {
      parent_version_id: parent, template_body: `Version ${number}: {{message}}`, model_config: model, commit_message: `Boundary version ${number}`,
    } })
    expect(response.status()).toBe(201)
    parent = (await response.json()).id
  }
  await reconcilePages(request, headers, '/projects', 'SELECT project_id AS id FROM project_members WHERE user_id=%s', [actor.id])
  await reconcilePages(request, headers, `/prompts/${prompt.id}/versions`, 'SELECT id FROM prompt_versions WHERE prompt_id=%s', [prompt.id])
  await reconcilePages(request, headers, '/runs?status=completed&model=gemini-3.5-flash-lite', "SELECT r.id FROM runs r WHERE r.status='completed' AND r.model='gemini-3.5-flash-lite' AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id=r.project_id AND pm.user_id=%s)", [actor.id])
  await reconcilePages(request, headers, '/deployments?status=active&environment=dev', "SELECT d.id FROM deployments d JOIN prompts p ON p.id=d.prompt_id WHERE d.status='active' AND d.environment='dev' AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id=p.project_id AND pm.user_id=%s)", [actor.id])
  await page.goto('/projects')
  await refresh(page)
  await page.getByRole('textbox', { name: 'Search projects' }).fill(`${key}-0`)
  await expect(page.getByRole('heading', { name: project.name, exact: true })).toBeVisible()
  await page.goto(`/prompts/${prompt.id}`)
  await expect(page.getByRole('link', { name: /v101 Current/ })).toBeVisible()
  await expect(page.getByRole('link', { name: /^v1 / })).toBeVisible()
  await page.goto(`/projects/${project.id}`)
  await expect(page.getByText(/^Active: .*development/)).toBeVisible()
  const adminContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173' })
  try {
    const admin = await adminContext.newPage()
    const adminJwt = await signIn(admin, 'admin')
    await reconcilePages(request, { Authorization: `Bearer ${adminJwt}` }, '/admin/deployments/pending', "SELECT id FROM deployments WHERE status='pending' AND environment='prod'")
    await admin.goto('/admin/approvals')
    await expect(admin.getByRole('link', { name: `${prompt.key} v1 → Production`, exact: true })).toBeVisible()
    const count = databaseRows("SELECT count(*) AS count FROM deployments WHERE status='pending' AND environment='prod'")[0].count
    await expect(admin.locator('tbody tr')).toHaveCount(Number(count))
  } finally { await adminContext.close() }
})

test('an unrelated account sees no restricted records, counts or run output', async ({ page, request, browser }) => {
  const jwt = await signIn(page)
  const { project, prompt, headers } = await fixture(request, jwt, suffix())
  const runResponse = await request.post(`${api}/runs`, { headers, data: { version_id: prompt.latest_version.id, variables: { message: 'Private output' } } })
  expect(runResponse.status()).toBe(201)
  const run = await runResponse.json()
  const unrelatedAccount = await createVerifiedTestAccount(request, `unrelated-${suffix()}`)
  const session = unrelatedAccount.session
  const unrelatedHeaders = { Authorization: `Bearer ${session.access_token}` }
  for (const path of ['/projects', '/runs', '/deployments']) {
    const response = await request.get(`${api}${path}`, { headers: unrelatedHeaders })
    expect(response.status()).toBe(200)
    expect(await response.json()).toMatchObject({ total: 0, items: [] })
  }
  for (const [path, status] of [
    [`/projects/${project.id}`, 403], [`/projects/${project.id}/prompts`, 403],
    [`/prompts/${prompt.id}/versions`, 404], [`/versions/${prompt.latest_version.id}`, 404],
    [`/runs/${run.id}`, 404], ['/admin/deployments/pending', 403],
  ] as const) {
    const response = await request.get(`${api}${path}`, { headers: unrelatedHeaders })
    expect(response.status()).toBe(status)
    expect(await response.text()).not.toContain('Private output')
  }
  const dashboardResponse = await request.get(`${api}/dashboard/me`, { headers: unrelatedHeaders })
  expect(dashboardResponse.status()).toBe(200)
  expect(await dashboardResponse.json()).toMatchObject({ project_count: 0, prompt_count: 0, run_count: 0, pending_approval_count: 0, recent_runs: [] })
  const invitationToken = new URLSearchParams(new URL(invitationLink(email, updatedName)).hash.slice(1)).get('token')!
  expect((await request.post(`${api}/project-invitations/accept`, { headers: { Authorization: `Bearer ${memberSession.access_token}` }, data: { token: invitationToken } })).status()).toBe(200)
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173' })
  try {
    const unrelated = await context.newPage()
    await unrelated.goto('/login')
    await unrelated.evaluate((token) => sessionStorage.setItem('promptvault.api.session', token), session.access_token)
    await unrelated.goto('/dashboard')
    await expect(unrelated.getByText('No personal runs yet')).toBeVisible()
    await unrelated.goto(`/runs/${run.id}`)
    await expect(unrelated.getByRole('heading', { name: 'Could not load this run' })).toBeVisible()
    await expect(unrelated.getByText('Private output', { exact: true })).toHaveCount(0)
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

  let releaseOlder!: () => void
  let olderArrived!: () => void
  let olderFinished!: () => void
  const held = new Promise<void>((resolve) => { releaseOlder = resolve })
  const arrived = new Promise<void>((resolve) => { olderArrived = resolve })
  const finished = new Promise<void>((resolve) => { olderFinished = resolve })
  await page.route('**/api/v1/runs?**', async (route) => {
    if (new URL(route.request().url()).searchParams.get('status') !== 'failed') return route.continue()
    const response = await route.fetch()
    olderArrived()
    await held
    await route.fulfill({ response })
    olderFinished()
  })
  try {
    await page.getByLabel('Run status').selectOption('failed')
    await arrived
    await page.getByLabel('Run status').selectOption('completed')
    await expect(page.locator('.run-pagination')).toContainText('12 runs · page 1')
    releaseOlder()
    await finished
    await expect(page.locator('.run-pagination')).toContainText('12 runs · page 1')
    await expect(page.getByLabel('Run status')).toHaveValue('completed')
  } finally { releaseOlder(); await page.unroute('**/api/v1/runs?**') }
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.locator('.run-pagination')).toContainText('12 runs · page 2')

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
  const dashboard = await (await request.get(`${api}/dashboard/me`, { headers })).json()
  const total = databaseRows("SELECT count(*) count FROM runs WHERE user_id=%s AND created_at >= (%s::date::timestamp AT TIME ZONE %s) AND created_at < ((%s::date + interval '1 month') AT TIME ZONE %s)", [actor.id, `${dashboard.month}-01`, dashboard.timezone, `${dashboard.month}-01`, dashboard.timezone])[0].count
  expect(dashboard.run_count).toBe(total)
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
