import { expect, test } from '@playwright/test'
import { databaseRows } from './support/database'

test.skip(process.env.E2E_LIVE !== '1' || !process.env.E2E_DATABASE_URL, 'Requires a local isolated stack.')
const api = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8003/api/v1'

test('self display-name changes persist and refresh navigation identity', async ({ page, request }) => {
  expect(String(databaseRows('SELECT current_database() AS name')[0].name)).toMatch(/_test$/)
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const email = `profile-${suffix}@example.com`
  const displayName = `Ananya ${suffix}`
  const registration = await request.post(`${api}/auth/register`, { data: { email, password: 'ProfilePassword2026!', display_name: 'Profile original' } })
  expect(registration.status()).toBe(201)
  const account = (await registration.json()).user
  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill('ProfilePassword2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/profile')
  await page.getByLabel('Display name').fill(displayName)
  await page.getByRole('button', { name: 'Save display name' }).click()
  await expect(page.getByText('Display name saved.')).toBeVisible()
  await expect(page.getByRole('heading', { name: displayName, exact: true })).toBeVisible()
  expect(databaseRows('SELECT display_name, email, role FROM users WHERE id=%s', [account.id])[0]).toMatchObject({ display_name: displayName, email, role: 'user' })
  await page.reload()
  await expect(page.getByLabel('Display name')).toHaveValue(displayName)
  await expect(page.getByRole('heading', { name: displayName, exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save display name' })).toBeDisabled()
})
