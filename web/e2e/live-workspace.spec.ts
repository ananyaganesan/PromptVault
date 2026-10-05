import { expect, test } from '@playwright/test'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('project, member, prompt, and immutable versions survive reloads through FastAPI', async ({ page }) => {
  const suffix = Date.now().toString(36)
  const projectName = `Live Workspace ${suffix}`
  const projectKey = `live-workspace-${suffix}`
  const promptName = `Live Reply ${suffix}`
  const promptKey = `live-reply-${suffix}`
  await signIn(page)

  await page.goto('/projects/new')
  await page.getByLabel('Project name').fill(projectName)
  await page.getByLabel('Project key').fill(projectKey)
  await page.getByRole('button', { name: 'Create project' }).click()
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible()

  const updatedProjectName = `${projectName} Updated`
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByLabel('Project name').fill(updatedProjectName)
  await page.getByLabel('Description').fill('Updated through the live project settings API.')
  await page.getByRole('button', { name: 'Save settings' }).click()
  await expect(page.getByText('Project settings saved.')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: updatedProjectName })).toBeVisible()

  await page.getByRole('button', { name: /Members/ }).click()
  await page.getByLabel('Member email').fill('admin@promptvault.dev')
  await page.getByRole('button', { name: 'Add member' }).click()
  await expect(page.getByText('admin@promptvault.dev was added to the project.')).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: /Members/ }).click()
  await expect(page.locator('.member-row').filter({ hasText: 'admin@promptvault.dev' })).toBeVisible()

  await page.getByRole('link', { name: 'New prompt' }).first().click()
  await page.getByLabel('Prompt key').fill(promptKey)
  await page.getByLabel('Prompt name').fill(promptName)
  await page.getByLabel('Template').fill('Answer {{customer_message}} for order {{order_id}}.')
  await page.getByRole('button', { name: 'Create prompt' }).click()
  await expect(page.getByRole('heading', { name: promptName })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: promptName })).toBeVisible()

  for (const [index, commit] of ['Clarify response', 'Add escalation guidance'].entries()) {
    await page.getByLabel('Commit message').fill(commit)
    await page.getByRole('button', { name: 'Save new version' }).click()
    await expect(page.getByText(`Version ${index + 2} was saved as an immutable snapshot.`)).toBeVisible()
  }
  await page.reload()
  await expect(page.getByText('v3 Current')).toBeVisible()
  await page.getByRole('link', { name: /v3 Current/ }).click()
  await expect(page.getByRole('heading', { name: 'Version 3' })).toBeVisible()
  await page.getByRole('button', { name: 'Compare versions' }).click()
  await expect(page.getByRole('heading', { name: 'Compare versions' })).toBeVisible()
  await expect(page.getByText('v2 base')).toBeVisible()
  await page.goBack()
  await page.goBack()
  await page.getByRole('link', { name: 'View lineage' }).click()
  await expect(page.getByRole('heading', { name: 'Version lineage' })).toBeVisible()
  await expect(page.getByText(/descends through 2 earlier versions/)).toBeVisible()
})
