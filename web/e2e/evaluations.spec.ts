import { expect, test } from '@playwright/test'

test('review an evaluation and explicitly save an improvement', async ({ page }, testInfo) => {
  const now = '2026-10-25T10:00:00Z'
  const user = { id: 'owner', email: 'owner@example.com', display_name: 'Example Owner', role: 'user', is_active: true, is_approved: true, created_at: now }
  const model = { provider: 'gemini', model: 'gemini-3.5-flash-lite', temperature: 0, max_output_tokens: 500 }
  const versions = [2, 1].map((n) => ({ id: `version-${n}`, prompt_id: 'prompt-1', version_number: n, parent_version_id: n === 2 ? 'version-1' : null, template_body: 'Answer {{topic}} clearly.', variables: ['topic'], model_config: model, commit_message: n === 2 ? 'Clear next steps' : 'Initial prompt', created_by: { id: 'owner', display_name: user.display_name }, created_at: now }))
  const weights = { correctness: 30, relevance: 25, instruction_following: 20, completeness: 15, clarity: 10 }
  const cases = [{ name: 'Delayed delivery', variables: { topic: 'My delivery is late. What should I do?' }, reference: '' }]
  let evaluation: Record<string, unknown> | null = null
  let savedVersions = 0
  const pageOf = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 100 })
  await page.addInitScript(() => sessionStorage.setItem('promptvault.api.session', 'browser-test-token'))
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } })
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    let result: unknown
    if (path === '/auth/me') result = user
    else if (path === '/projects') result = pageOf([{ id: 'project-1', key: 'support', name: 'Support', description: 'Customer support prompts', owner: { id: 'owner', display_name: user.display_name }, prompt_count: 1, member_count: 1, created_at: now, updated_at: now }])
    else if (path === '/projects/project-1/prompts') result = pageOf([{ id: 'prompt-1', project_id: 'project-1', key: 'support-answer', name: 'Support answer', description: 'Practical next steps', latest_version_number: 2, created_at: now, updated_at: now }])
    else if (path === '/prompts/prompt-1/versions' && request.method() === 'POST') {
      savedVersions += 1
      result = { ...versions[0], id: 'version-3', version_number: 3, template_body: request.postDataJSON().template_body }
    } else if (path === '/prompts/prompt-1/versions') result = pageOf(versions)
    else if (path === '/deployments') result = pageOf([])
    else if (path === '/prompts/prompt-1/evaluation-setup') result = { configuration: null }
    else if (path === '/prompts/prompt-1/evaluation-suggestions') result = { cases, weights, requirements: { valid_json: false, required_fields: [], max_words: 100 }, notes: 'Check relevance, clarity, and practical next steps.' }
    else if (path === '/prompts/prompt-1/evaluations' && request.method() === 'POST') {
      const body = request.postDataJSON()
      evaluation = { id: body.id, prompt_id: 'prompt-1', created_by: 'owner', configuration: body.configuration, version_snapshots: versions, status: 'completed', winner_version_id: 'version-2', recommendation: 'Version 2 gives clearer next steps and meets all mandatory requirements.', error: null, created_at: now, updated_at: now, usage: { evaluator_calls: 2, evaluator_prompt_tokens: 200, evaluator_completion_tokens: 180 },
        ranking: versions.map((v) => ({ version_id: v.id, score: v.version_number === 2 ? 92 : 71, eligible: true, passed_cases: 1, total_cases: 1, reason: 'Meets every mandatory check.' })),
        results: versions.map((v) => ({ version_id: v.id, case_index: 0, run_id: `run-${v.id}`, output: 'Check the tracking link, then contact support if the delivery date has passed.', checks: [{ name: 'Word limit', passed: true, detail: '15 words; limit 100' }], scores: { clarity: { score: v.version_number === 2 ? 4.6 : 3.55, reason: 'Offers actionable next steps.', evidence: 'Check the tracking link' } }, weighted_score: v.version_number === 2 ? 92 : 71, summary: 'Helpful instructions for the customer.', error: null, prompt_tokens: 80, completion_tokens: 40, latency_ms: 200 })) }
      result = evaluation
    } else if (path.endsWith('/improvement')) result = { template: 'Answer {{topic}} with empathy and clear next steps.', explanation: 'Makes the next step explicit. This draft has not been evaluated.' }
    else if (/\/evaluations\/[^/]+$/.test(path)) result = evaluation
    else if (path === '/prompts/prompt-1/evaluations') result = evaluation ? [{ ...evaluation, completed_cases: 2, total_cases: 2 }] : []
    else return route.fulfill({ status: 404, json: { code: 'not_found', message: `Unexpected test route: ${path}` } })
    return route.fulfill({ status: 200, json: result, headers: { 'Access-Control-Allow-Origin': '*' } })
  })
  await page.goto('/prompts/prompt-1/evaluate')
  await expect(page.getByRole('heading', { name: 'Prompt evaluation' })).toBeVisible()
  await expect(page.getByLabel(/Require valid JSON|Required top-level JSON/)).toHaveCount(0)
  await page.getByRole('button', { name: 'Suggest examples for me' }).click()
  await expect(page.getByRole('heading', { name: 'Review Gemini’s suggestions' })).toBeVisible()
  await page.getByRole('button', { name: 'Use these examples and preferences' }).click()
  await expect(page.getByLabel('topic · example 1')).toHaveValue(cases[0].variables.topic)
  await page.screenshot({ path: testInfo.outputPath('evaluation-setup.png'), fullPage: true })
  const example = page.locator('.eval-case').first()
  await example.locator('summary').click()
  await expect(page.getByLabel('topic · example 1')).not.toBeVisible()
  await expect(example.locator('.eval-case-preview')).toHaveText(cases[0].variables.topic)
  await expect(page.getByLabel('Clarity (%)')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Use previous examples' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('evaluation-compact-setup.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await example.locator('summary').click()
  await expect(page.getByLabel('topic · example 1')).toHaveValue(cases[0].variables.topic)
  await page.getByRole('button', { name: 'Compare versions' }).click()
  await expect(page.getByRole('heading', { name: 'Recommended: v2' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Evaluation results' }).getByText('Version 2 gives clearer next steps and meets all mandatory requirements.', { exact: true })).toBeVisible()
  await expect(page.getByRole('table').getByRole('button', { name: 'Version 2 gives clearer next steps and meets all mandatory requirements.' })).toBeVisible()
  await page.locator('.eval-output details').first().locator('summary').click()
  await expect(page.locator('mark').first()).toHaveText('Check the tracking link')
  await page.screenshot({ path: testInfo.outputPath('evaluation-results.png'), fullPage: true })
  await page.getByRole('button', { name: 'Suggest an improvement' }).click()
  const draft = page.getByLabel('Review and edit the suggested template')
  await expect(draft).toHaveValue(/Answer \{\{topic\}\}/)
  expect(savedVersions).toBe(0)
  await draft.fill('Answer {{topic}} with clear next steps. Keep it concise.')
  await page.getByRole('button', { name: 'Save as a new version' }).click()
  await expect(page.getByText(/Saved v3/)).toBeVisible()
  expect(savedVersions).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
