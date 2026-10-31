import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const user = { id: 'browser-user', email: 'member@example.com', display_name: 'Jamie Member', role: 'user', is_active: true, is_approved: true, created_at: '2026-10-28T10:00:00Z' }
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' }

async function mockApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
    if (path === '/auth/login') return route.fulfill({ json: { user, access_token: 'browser-test-token', token_type: 'bearer', expires_in: 1800 }, headers: cors })
    if (path === '/auth/logout') return route.fulfill({ status: 204, headers: cors })
    if (path === '/auth/me') return route.fulfill({ json: user, headers: cors })
    if (path === '/projects') return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 100 }, headers: cors })
    if (path === '/dashboard/me') return route.fulfill({ json: { project_count: 0, prompt_count: 0, run_count: 0, pending_approval_count: 0, monthly_spend: '0', monthly_budget: null, recent_runs: [], cost_trend: [], month: '2026-10', timezone: 'UTC', completed_run_count: 0, failed_run_count: 0, blocked_run_count: 0, refreshed_through: '2026-10-28T10:00:00Z' }, headers: cors })
    return route.fulfill({ status: 404, json: { code: 'not_found', message: `Unexpected request: ${path}` }, headers: cors })
  })
}

test('local sign-in restores the session, enforces role access, and signs out', async ({ page, isMobile }) => {
  await mockApi(page)
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email address').fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill('BrowserTestPassword2026!')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Good morning, Jamie' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Jamie' })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Projects', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/403$/)
  await page.goto('/dashboard')
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Sign out' }).last().click()
  await expect(page).toHaveURL(/\/login$/)
})

test('registration waits for verification without creating a session', async ({ page }) => {
  await page.route('**/api/v1/auth/register', (route) => route.fulfill({ status: 202, json: { email: 'new@example.com', message: 'Check your email to verify your account. An administrator must then approve access.' }, headers: cors }))
  await page.goto('/register')
  await page.getByLabel('Display name').fill('New Member')
  await page.getByLabel('Email address').fill('new@example.com')
  await page.getByLabel('Password', { exact: true }).fill('NewMemberPassword2026!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))).toBeNull()
})

test('signed-out form validates inputs and fits the viewport', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Email address is required.')).toBeVisible()
  await expect(page.getByText('Password is required.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const audit = await new AxeBuilder({ page }).analyze()
  expect(audit.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? ''))).toEqual([])
})
