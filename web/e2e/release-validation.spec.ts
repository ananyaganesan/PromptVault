import { expect, test } from '@playwright/test'

test('release checks stay in deployment workflow and fixes require a new validation', async ({ page }, testInfo) => {
  const now = '2026-10-26T10:00:00Z'
  const user = { id: 'owner', email: 'owner@example.com', display_name: 'Example Owner', role: 'user', is_active: true, is_approved: true, created_at: now }
  const model = { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 500 }
  const versions = [{ id: 'version-1', prompt_id: 'prompt-1', version_number: 1, parent_version_id: null as string | null, template_body: 'Answer {{topic}}.', variables: ['topic'], model_config: model, commit_message: 'Initial prompt', created_by: { id: 'owner', display_name: user.display_name }, created_at: now }]
  let report: Record<string, unknown> | null = null
  let deployments = 0
  let validations = 0
  let saves = 0
  const pageOf = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 100 })
  await page.addInitScript(() => sessionStorage.setItem('promptvault.api.session', 'browser-release-token'))
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } })
    let result: unknown
    if (path === '/auth/me') result = user
    else if (path === '/projects') result = pageOf([{ id: 'project-1', key: 'support', name: 'Support', description: 'Customer support', owner: { id: user.id, display_name: user.display_name }, prompt_count: 1, member_count: 1, created_at: now, updated_at: now }])
    else if (path === '/projects/project-1/prompts') result = pageOf([{ id: 'prompt-1', project_id: 'project-1', key: 'support-answer', name: 'Support answer', latest_version_number: versions.length, created_at: now, updated_at: now }])
    else if (path === '/prompts/prompt-1/versions' && request.method() === 'POST') {
      saves++
      const body = request.postDataJSON()
      versions.unshift({ ...versions[0], id: 'version-2', version_number: 2, parent_version_id: body.parent_version_id, template_body: body.template_body })
      result = versions[0]
    } else if (path === '/prompts/prompt-1/versions') result = pageOf(versions)
    else if (path === '/prompts/prompt-1/evaluation-setup') result = { configuration: null }
    else if (path === '/deployments/validations' && request.method() === 'POST') {
      validations++
      const body = request.postDataJSON()
      report = { id: body.id, version_id: body.version_id, environment: body.environment, created_by: 'owner', created_at: now, base_deployment_id: null, status: validations === 1 ? 'blocked' : 'passed', summary: validations === 1 ? 'The answer exceeded the word limit.' : 'Every release check passed.', minimum_score: 70,
        configuration: { ...body.suite, version_ids: [body.version_id], preset: 'accurate_answers' },
        checks: [{ name: 'Gemini configuration', passed: true, detail: 'Permitted Gemini model.' }, { name: 'Variable compatibility', passed: true, detail: 'Input contract preserved.' }],
        evaluation: { status: 'completed', results: [{ version_id: body.version_id, case_index: 0, output: 'Contact support with your tracking number.', weighted_score: validations === 1 ? 60 : 92, checks: [{ name: 'Word limit', passed: validations > 1, detail: 'Maximum 100 words.' }], scores: {}, error: null, summary: 'Helpful next steps.' }] } }
      result = report
    } else if (path.endsWith('/suggest-fix')) result = { template: 'Answer {{topic}} clearly in under 100 words.', explanation: 'Adds an explicit word limit. This draft has not been tested.' }
    else if (path.startsWith('/deployments/validations/')) result = report
    else if (path === '/deployments' && request.method() === 'POST') {
      deployments++
      expect(request.postDataJSON().validation_id).toBe(report?.id)
      result = { id: 'release-1', project_id: 'project-1', prompt_id: 'prompt-1', prompt_key: 'support-answer', version_id: 'version-2', version_number: 2, environment: 'prod', status: 'pending', request_note: null, review_note: null, rollback_reason: null, rollback_of_id: null, requested_by: { id: user.id, display_name: user.display_name }, reviewed_by: null, requested_at: now, reviewed_at: null, activated_at: null }
    } else if (path === '/deployments') result = pageOf([])
    else if (path === '/deployments/release-1') result = { id: 'release-1', project_id: 'project-1', prompt_id: 'prompt-1', prompt_key: 'support-answer', version_id: 'version-2', version_number: 2, environment: 'prod', status: 'pending', requested_by: { id: user.id, display_name: user.display_name }, reviewed_by: null, requested_at: now, timeline: [], validation: report }
    else return route.fulfill({ status: 404, json: { code: 'not_found', message: `Unexpected test route: ${path}` } })
    return route.fulfill({ json: result, headers: { 'Access-Control-Allow-Origin': '*' } })
  })
  await page.goto('/deployments/new?version=version-1')
  await expect(page.getByRole('heading', { name: 'Create deployment' })).toBeVisible()
  await page.getByRole('combobox', { name: 'Environment', exact: true }).selectOption('production')
  await page.getByLabel('Test 1: topic', { exact: true }).fill('My delivery is late.')
  await page.getByLabel('Maximum words (optional)').fill('100')
  await page.getByRole('button', { name: 'Validate release', exact: true }).click()
  await expect(page.getByText('The answer exceeded the word limit.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Request approval', exact: true })).toHaveCount(0)
  expect(deployments).toBe(0)
  await page.getByRole('button', { name: 'Suggest a fix', exact: true }).click()
  expect(saves).toBe(0)
  await page.getByRole('button', { name: 'Save fix and validate', exact: true }).click()
  expect(saves).toBe(1)
  await expect(page.getByRole('button', { name: 'Request approval', exact: true })).toBeVisible()
  expect(validations).toBe(2)
  // Durable report is restored after a page reload.
  await page.reload()
  await expect(page.getByRole('button', { name: 'Request approval', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('validated-release.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Request approval', exact: true }).click()
  await expect(page).toHaveURL(/\/deployments\/release-1$/)
  expect(deployments).toBe(1)
  await expect(page.getByRole('link', { name: 'Revalidate this request' })).toBeVisible()
})
