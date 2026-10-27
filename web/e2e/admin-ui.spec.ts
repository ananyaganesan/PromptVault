import { expect, test } from '@playwright/test'

test('admin landing page focuses on approvals and hides software controls', async ({ page }, testInfo) => {
  const now = '2026-10-25T10:00:00Z'
  const user = { id: 'admin-id', email: 'admin@example.com', display_name: 'Example Admin', role: 'admin', is_active: true, is_approved: true, created_at: now }
  const pendingUser = { id: 'pending-id', email: 'pending@example.com', display_name: 'Pending account', role: 'user', is_active: true, is_approved: false, project_count: 0, created_at: now, updated_at: now }
  const pageOf = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 100 })
  await page.addInitScript(() => sessionStorage.setItem('promptvault.api.session', 'admin-ui-test-token'))
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } })
    let result: unknown
    if (path === '/auth/me') result = user
    else if (path === '/projects') result = pageOf([])
    else if (path === '/admin/users') result = pageOf([pendingUser])
    else if (path === '/admin/deployments/pending') result = pageOf([])
    else return route.fulfill({ status: 403, json: { code: 'forbidden', message: 'Unexpected admin UI request.' } })
    return route.fulfill({ json: result, headers: { 'Access-Control-Allow-Origin': '*' } })
  })
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Admin dashboard' })).toBeVisible()
  await expect(page.getByText('Pending account', { exact: true })).toBeVisible()
  await expect(page.getByText('USER APPROVALS', { exact: true })).toBeVisible()
  for (const label of ['Database maintenance', 'Provider keys', 'Audit log']) await expect(page.getByRole('link', { name: label })).toHaveCount(0)
  if (testInfo.project.name === 'mobile-chrome') {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Admin dashboard' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Rollback' })).toBeVisible()
    await page.getByRole('button', { name: 'Close navigation' }).click()
  }
  if (testInfo.project.name === 'desktop-chrome') await expect(page.getByRole('link', { name: 'Rollback' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-dashboard.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  // Also review the empty approval queues at the reference image's desktop size.
  if (testInfo.project.name === 'desktop-chrome') await page.setViewportSize({ width: 1701, height: 925 })
  await page.route('**/api/v1/admin/users?**', (route) => route.fulfill({ json: pageOf([
    { ...pendingUser, id: 'approved-one', is_approved: true },
    { ...pendingUser, id: 'approved-two', is_approved: true },
  ]), headers: { 'Access-Control-Allow-Origin': '*' } }))
  await page.reload()
  await expect(page.getByText('No users are waiting for approval.', { exact: true })).toBeVisible()
  await expect(page.getByText('No deployment requests are waiting for review.', { exact: true })).toBeVisible()
  await expect(page.locator('.stat').filter({ hasText: 'ACTIVE USERS' }).first().locator('strong')).toHaveText('2')
  await page.screenshot({ path: testInfo.outputPath('admin-dashboard-empty.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
