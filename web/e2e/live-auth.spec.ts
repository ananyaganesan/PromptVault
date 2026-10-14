import { expect, test } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against a local live API/database stack.')

test('seeded user signs in through FastAPI and restores the session', async ({ page, isMobile }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Good morning, Demo' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Demo' })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('registration creates a pending account without a browser session', async ({ page }) => {
  const suffix = Date.now().toString(36)
  await page.goto('/register')
  await page.getByLabel('Display name').fill(`Live Tester ${suffix}`)
  await page.getByLabel('Email address').fill(`live-${suffix}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('LiveTester2026!')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))).toBeNull()
})

test('a normal user is recovered to the forbidden screen for admin routes', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/403$/)
  await expect(page.getByRole('heading', { name: 'Access restricted' })).toBeVisible()
})
