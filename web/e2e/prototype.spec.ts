import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('user signs in, refreshes, navigates, and signs out', async ({ page, isMobile }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Good morning, Jamie' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Jamie' })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Projects', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Sign out' }).last().click()
  await expect(page).toHaveURL(/\/login$/)
})

test('admin can reach administration', async ({ page, isMobile }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('admin@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('Admin@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Approvals', exact: true }).first().click()
  await expect(page).toHaveURL(/\/admin\/approvals$/)
})

test('standard user is denied administration', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/403$/)
  await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible()
})

test('user creates a project, prompt, and version', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.goto('/projects/new')
  await page.getByLabel('Project name').fill('Demo Workspace')
  await page.getByLabel('Project key').fill('demo-workspace')
  await page.getByRole('button', { name: 'Create project' }).click()
  await expect(page.getByRole('heading', { name: 'Demo Workspace' })).toBeVisible()
  await page.getByRole('link', { name: 'New prompt' }).first().click()
  await page.getByLabel('Prompt key').fill('demo-reply')
  await page.getByLabel('Prompt name').fill('Demo Reply')
  await page.getByLabel('Template').fill('Answer {{customer_message}} clearly.')
  await page.getByRole('button', { name: 'Create prompt' }).click()
  await expect(page.getByRole('heading', { name: 'Demo Reply' })).toBeVisible()
  await page.getByLabel('Commit message').fill('Clarify response')
  await page.getByRole('button', { name: 'Save new version' }).click()
  await expect(page.getByText('Version 2 was saved as an immutable snapshot.')).toBeVisible()
})

test('registration creates a user session and rejects duplicate email', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('Display name').fill('Demo Tester')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('Password123')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('alert')).toContainText('already exists')
  await page.getByLabel('Email address').fill(`tester-${Date.now()}@example.com`)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Good morning, Demo' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Demo' })).toBeVisible()
})

test('key screens have no critical accessibility violations', async ({ page }) => {
  await page.goto('/login')
  const loginAudit = await new AxeBuilder({ page }).analyze()
  expect(loginAudit.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? '')).map((item) => ({ id: item.id, nodes: item.nodes.map((node) => node.target) }))).toEqual([])
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Good morning, Jamie' })).toBeVisible()
  const dashboardAudit = await new AxeBuilder({ page }).analyze()
  expect(dashboardAudit.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? '')).map((item) => ({ id: item.id, nodes: item.nodes.map((node) => node.target) }))).toEqual([])
})

test('validation and mobile layout have no horizontal overflow', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Email address is required.')).toBeVisible()
  await expect(page.getByText('Password is required.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('workspace routes render without a blank page or horizontal overflow', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  for (const path of ['/dashboard', '/projects', '/prompts', '/playground', '/runs', '/deployments', '/costs', '/api-tokens', '/profile', '/projects/checkout', '/prompts/checkout-reply', '/versions/checkout-v3']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${path} has horizontal overflow` }).toBe(true)
  }
  await page.goto('/projects/does-not-exist')
  await expect(page.getByText('Project not found')).toBeVisible()
  await page.goto('/prompts/does-not-exist')
  await expect(page.getByText('Prompt not found')).toBeVisible()
  await page.goto('/versions/does-not-exist')
  await expect(page.getByText('Version not found')).toBeVisible()
})

test('administration routes render without a blank page or horizontal overflow', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('admin@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('Admin@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  for (const path of ['/admin', '/admin/approvals', '/admin/rollback', '/admin/users', '/admin/provider-keys', '/admin/budgets', '/admin/runs', '/admin/audit', '/admin/model-pricing', '/admin/maintenance']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${path} has horizontal overflow` }).toBe(true)
  }
})

test('top-level user screens have no serious accessibility violations', async ({ page }) => {
  test.slow()
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('User@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  const issues: string[] = []
  for (const path of ['/projects', '/prompts', '/playground', '/runs', '/deployments', '/costs', '/api-tokens', '/profile']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const audit = await new AxeBuilder({ page }).analyze()
    issues.push(...audit.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? '')).map((item) => `${path}: ${item.id} (${item.nodes.map((node) => node.target.join(' ')).join(', ')})`))
  }
  expect(issues).toEqual([])
})

test('top-level admin screens have no serious accessibility violations', async ({ page }) => {
  test.slow()
  await page.goto('/login')
  await page.getByLabel('Email address').fill('admin@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('Admin@123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  const issues: string[] = []
  for (const path of ['/admin', '/admin/approvals', '/admin/rollback', '/admin/users', '/admin/provider-keys', '/admin/budgets', '/admin/runs', '/admin/audit', '/admin/model-pricing', '/admin/maintenance']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const audit = await new AxeBuilder({ page }).analyze()
    issues.push(...audit.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? '')).map((item) => `${path}: ${item.id} (${item.nodes.map((node) => node.target.join(' ')).join(', ')})`))
  }
  expect(issues).toEqual([])
})
