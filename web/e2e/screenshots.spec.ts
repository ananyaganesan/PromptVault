import { expect, test } from '@playwright/test'

test.skip(!process.env.CAPTURE_SCREENSHOTS, 'Run npm run screenshots to refresh demo images.')

test('capture live-stack screens', async ({ page }, testInfo) => {
  const size = testInfo.project.name.startsWith('mobile') ? 'mobile' : 'desktop'
  const capture = (name: string) => page.screenshot({ path: `../docs/screenshots/${name}-${size}.png`, fullPage: true })
  await page.goto('/login')
  await capture('login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Good morning, Demo' })).toBeVisible()
  await capture('user-dashboard')
  await page.goto('/projects')
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  await capture('projects')
  await page.evaluate(() => sessionStorage.clear())
  await page.reload()
  await page.goto('/login')
  await page.getByLabel('Email address').fill('admin@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('AdminDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await capture('admin-dashboard')
})
