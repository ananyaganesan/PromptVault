import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')
test.setTimeout(90_000)

async function signIn(page: Page, role: 'user' | 'admin') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'admin' ? 'AdminDemo2026!' : 'UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

async function verifyRoutes(page: Page, routes: string[]) {
  const issues: string[] = []
  for (const route of routes) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${route} has horizontal overflow` }).toBe(true)
    const result = await new AxeBuilder({ page }).analyze()
    issues.push(...result.violations
      .filter((item) => item.impact === 'critical' || item.impact === 'serious')
      .map((item) => `${route}: ${item.id} (${item.nodes.map((node) => node.target.join(' ')).join(', ')})`))
  }
  expect(issues).toEqual([])
}

test('user routes are responsive and have no serious automated accessibility violations', async ({ page }) => {
  await page.goto('/login')
  const login = await new AxeBuilder({ page }).analyze()
  expect(login.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious')).toEqual([])
  await signIn(page, 'user')
  await verifyRoutes(page, ['/dashboard', '/projects', '/prompts', '/playground', '/runs', '/deployments', '/costs', '/api-tokens', '/profile'])
})

test('admin routes are responsive and have no serious automated accessibility violations', async ({ page }) => {
  await signIn(page, 'admin')
  await verifyRoutes(page, ['/admin', '/admin/approvals', '/admin/rollback', '/admin/users', '/admin/provider-keys', '/admin/budgets', '/admin/runs', '/admin/audit', '/admin/model-pricing', '/admin/maintenance'])
})
