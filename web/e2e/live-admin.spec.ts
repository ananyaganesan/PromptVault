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

async function switchAccount(page: Page, role: 'user' | 'admin') {
  await page.evaluate(() => sessionStorage.clear())
  await page.reload()
  await signIn(page, role)
}

async function setUserBudget(page: Page, amount: string) {
  await page.goto('/admin/budgets')
  await expect(page.getByRole('heading', { name: 'Budgets' })).toBeVisible()
  const userRow = page.getByRole('row').filter({ hasText: 'Demo User' })
  await expect(userRow).toBeVisible()
  await userRow.getByRole('button', { name: 'Edit' }).click()
  const dialog = page.getByRole('dialog', { name: 'Set monthly budget' })
  await dialog.getByLabel('Monthly limit (USD)').fill(amount)
  await dialog.getByRole('button', { name: 'Save budget' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(userRow.getByRole('cell').nth(2)).toHaveText(`$${Number(amount).toFixed(6)}`)
}

test('admin governance uses live users, encrypted keys, budgets, audit, pricing, runs, and maintenance APIs', async ({ page }) => {
  const suffix = Date.now().toString(36)
  const keyLabel = `Live key ${suffix}`
  const secret = `super-secret-${suffix}`
  const model = `priced-model-${suffix}`
  await signIn(page, 'admin')
  await page.goto('/admin')

  await expect(page.getByRole('heading', { name: 'Administration' })).toBeVisible()
  await expect(page.getByText('ORGANIZATION SPEND')).toBeVisible()
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

  await setUserBudget(page, '0')
  await switchAccount(page, 'user')
  await page.goto('/playground')
  await expect(page.getByRole('button', { name: 'Run prompt' })).toBeVisible()
  const variables = page.locator('.playground textarea')
  for (let index = 0; index < await variables.count(); index += 1) await variables.nth(index).fill(`Budget test ${index + 1}`)
  await page.getByRole('button', { name: 'Run prompt' }).click()
  await expect(page.getByRole('heading', { name: 'Budget limit reached' })).toBeVisible()

  await switchAccount(page, 'admin')
  await setUserBudget(page, '100')
  const blockedRuns = page.locator('.stat').filter({ hasText: 'BLOCKED RUNS' })
  await expect(blockedRuns.locator('strong')).toHaveText('1')

  await page.goto('/admin/model-pricing')
  await page.getByRole('button', { name: 'Add price' }).click()
  const priceDialog = page.getByRole('dialog', { name: 'Add model price' })
  await priceDialog.getByLabel('Provider').fill('mock')
  await priceDialog.getByLabel('Model').fill(model)
  await priceDialog.getByLabel('Token type').selectOption('input')
  await priceDialog.getByLabel('USD per million tokens').fill('1.250000')
  await priceDialog.getByRole('button', { name: 'Add price' }).click()
  await expect(page.getByRole('row').filter({ hasText: model }).first()).toContainText('1.250000')

  await page.goto('/admin/runs')
  await expect(page.getByRole('heading', { name: 'Organization runs' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'blocked', exact: true }).first()).toBeVisible()

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
})
