import { expect, test } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')

test('playground execution persists tokens, latency, cost, and history through FastAPI', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.goto('/playground')

  await expect(page.getByRole('button', { name: 'Run prompt' })).toBeVisible()
  const selectedPromptLabel = await page.getByLabel('Prompt version').locator('option:checked').textContent()
  const selectedPromptKey = selectedPromptLabel?.split(' · ')[0]
  expect(selectedPromptKey).toBeTruthy()
  const variables = page.locator('.playground textarea')
  for (let index = 0; index < await variables.count(); index += 1) {
    await variables.nth(index).fill(`Live value ${index + 1}`)
  }
  await page.getByRole('button', { name: 'Run prompt' }).click()
  await expect(page.getByText('completed', { exact: true })).toBeVisible()
  await expect(page.getByText('PROMPT TOKENS')).toBeVisible()
  await expect(page.getByText('LATENCY')).toBeVisible()
  await expect(page.getByText('COST', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: /View run details/ }).click()
  await expect(page.getByText('Charged for this run')).toBeVisible()
  const runUrl = page.url()
  await page.reload()
  await expect(page).toHaveURL(runUrl)
  await expect(page.getByText('Charged for this run')).toBeVisible()

  await page.goto('/runs')
  await expect(page.getByRole('cell', { name: selectedPromptKey!, exact: false }).first()).toBeVisible()
  await page.goto('/costs')
  await expect(page.getByText('All recorded runs')).toBeVisible()
})
