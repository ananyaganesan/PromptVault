import { expect, test, type Page } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')
test.setTimeout(90_000)

async function signIn(page: Page, role: 'user' | 'admin') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'admin' ? 'AdminDemo2026!' : 'UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

test('admin governance uses live users, encrypted keys, audit, runs, and maintenance APIs', async ({ page }) => {
  const suffix = Date.now().toString(36)
  const keyLabel = `Live key ${suffix}`
  const secret = `super-secret-${suffix}`
  await signIn(page, 'admin')
  await page.goto('/admin')

  await expect(page.getByRole('heading', { name: 'Administration' })).toBeVisible()
  await expect(page.getByText('TOTAL RUNS')).toBeVisible()
  await expect(page.getByText('Prototype data')).toHaveCount(0)

  await page.goto('/admin/users')
  await expect(page.getByRole('row').filter({ hasText: 'admin@promptvault.dev' })).toContainText('Super Admin')
  await expect(page.getByRole('row').filter({ hasText: 'user@promptvault.dev' })).toContainText('User')

  await page.goto('/admin/provider-keys')
  await page.getByRole('button', { name: 'Add provider key' }).click()
  const keyDialog = page.getByRole('dialog', { name: 'Add provider key' })
  await keyDialog.getByLabel('Provider').selectOption('gemini')
  await keyDialog.getByLabel('Label').fill(keyLabel)
  await keyDialog.getByLabel('Secret key').fill(secret)
  await keyDialog.getByRole('button', { name: 'Save key' }).click()
  const keyRow = page.getByRole('row').filter({ hasText: keyLabel })
  await expect(keyRow).toContainText('Active')
  await expect(page.getByText(secret, { exact: true })).toHaveCount(0)

  await page.goto('/admin/runs')
  await expect(page.getByRole('heading', { name: 'Organization runs' })).toBeVisible()
  await expect(page.locator('tbody tr').first()).toBeVisible()

  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
  await expect(page.locator('tbody tr').first()).toBeVisible()

  await page.goto('/admin/maintenance')
  await expect(page.getByText('healthy', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Refresh materialized views' }).click()
  await expect(page.getByText('Analytics views refreshed.')).toBeVisible()

  await page.goto('/admin/provider-keys')
  const currentKeyRow = page.getByRole('row').filter({ hasText: keyLabel })
  await currentKeyRow.getByRole('button', { name: 'Deactivate' }).click()
  await page.getByRole('dialog', { name: 'Deactivate provider key' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(currentKeyRow).toContainText('Inactive')

  await page.goto('/admin/users')
  const memberRow = page.getByRole('row').filter({ hasText: 'user@promptvault.dev' })
  await memberRow.getByRole('button', { name: 'Make admin' }).click()
  await page.getByRole('dialog', { name: 'Confirm user change' }).getByRole('button', { name: 'Confirm' }).click()
  await page.reload()
  await expect(memberRow).toContainText('Super Admin')

  const ownRow = page.getByRole('row').filter({ hasText: 'admin@promptvault.dev' })
  await ownRow.getByRole('button', { name: 'Make user' }).click()
  await page.getByRole('dialog', { name: 'Confirm user change' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await signIn(page, 'user')
  await page.goto('/admin/users')
  const formerAdmin = page.getByRole('row').filter({ hasText: 'admin@promptvault.dev' })
  await formerAdmin.getByRole('button', { name: 'Make admin' }).click()
  await page.getByRole('dialog', { name: 'Confirm user change' }).getByRole('button', { name: 'Confirm' }).click()
  await page.reload()
  await expect(formerAdmin).toContainText('Super Admin')
  const currentAdmin = page.getByRole('row').filter({ hasText: 'user@promptvault.dev' })
  await currentAdmin.getByRole('button', { name: 'Make user' }).click()
  await page.getByRole('dialog', { name: 'Confirm user change' }).getByRole('button', { name: 'Confirm' }).click()
  await expect(page).toHaveURL(/\/login$/)
})
