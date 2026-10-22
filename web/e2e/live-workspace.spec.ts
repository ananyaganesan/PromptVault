import { invitationLink } from './support/invitations'
import { expect, test } from '@playwright/test'
import { createVerifiedTestAccount } from './support/auth'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')
test.setTimeout(90_000)

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Email address').fill('user@promptvault.dev')
  await page.getByLabel('Password', { exact: true }).fill('UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

test('project, member, prompt, and immutable versions survive reloads through FastAPI', async ({ page, request }) => {
  const suffix = Date.now().toString(36)
  const projectName = `Live Workspace ${suffix}`
  const projectKey = `live-workspace-${suffix}`
  const promptName = `Live Reply ${suffix}`
  const promptKey = `live-reply-${suffix}`
  const memberAccount = await createVerifiedTestAccount(request, `member-${suffix}`)
  const memberEmail = memberAccount.email
  const memberPage = await page.context().newPage()
  await signIn(page)

  await page.goto('/projects/new')
  await page.getByLabel('Project name').fill(projectName)
  await page.getByLabel('Project key').fill(projectKey)
  await page.getByRole('button', { name: 'Create project' }).click()
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible()
  const projectUrl = page.url()
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
  await page.getByRole('button', { name: 'Invite member' }).click()
  await expect(page.getByText('Invitation emailed to admin@promptvault.dev. They will get access after accepting.')).toBeVisible()
  await page.getByLabel('Member email').fill(memberEmail)
  await page.getByRole('button', { name: 'Invite member' }).click()
  await expect(page.getByText(`Invitation emailed to ${memberEmail}. They will get access after accepting.`)).toBeVisible()
  await memberPage.goto(invitationLink(memberEmail, updatedProjectName))
  await memberPage.getByRole('button', { name: 'Accept invitation', exact: true }).click()
  await expect(memberPage.getByText('Invitation accepted. You now have project access.')).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: /Members/ }).click()
  await expect(page.locator('.member-row').filter({ hasText: 'admin@promptvault.dev' })).toBeVisible()
  await expect(page.locator('.member-row').filter({ hasText: memberEmail })).toBeVisible()
  await memberPage.goto('/login')
  await memberPage.evaluate((token) => sessionStorage.setItem('promptvault.api.session', token), memberAccount.session.access_token)
  await memberPage.goto('/projects')
  await expect(memberPage.getByRole('heading', { name: updatedProjectName })).toBeVisible()

  await page.getByRole('link', { name: 'New prompt' }).first().click()
  await page.getByLabel('Prompt key').fill(promptKey)
  await page.getByLabel('Prompt name').fill(promptName)
  await page.getByRole('textbox', { name: 'Template', exact: true }).fill('Answer {{customer_message}} for order {{order_id}}.')
  await page.getByRole('button', { name: 'Create prompt' }).click()
  await expect(page.getByRole('heading', { name: promptName })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: promptName })).toBeVisible()

  for (const [index, commit] of ['Clarify response', 'Add escalation guidance'].entries()) {
    await page.getByRole('textbox', { name: 'Prompt template' }).fill(`Answer {{customer_message}} for order {{order_id}}. ${commit}.`)
    await page.getByLabel('Commit message').fill(commit)
    await page.getByRole('button', { name: 'Save new version' }).click()
    await expect(page.getByText(`Version ${index + 2} was saved as an immutable snapshot.`)).toBeVisible()
  }
  await page.reload()
  await expect(page.getByText('v3 Current')).toBeVisible()
  await page.getByRole('link', { name: /v3 Current/ }).click()
  await expect(page.getByRole('heading', { name: 'Version 3' })).toBeVisible()
  await expect(page.getByLabel('Template snapshot')).toHaveValue('Answer {{customer_message}} for order {{order_id}}. Add escalation guidance.')
  await page.getByRole('button', { name: 'Compare versions' }).click()
  await expect(page.getByRole('heading', { name: 'Compare versions' })).toBeVisible()
  await expect(page.getByText('v2 base')).toBeVisible()
  await page.getByLabel('Base version').selectOption({ index: 2 })
  await expect(page.getByText('v1 base')).toBeVisible()
  await expect(page.getByLabel('Template snapshot').nth(0)).toHaveValue('Answer {{customer_message}} for order {{order_id}}.')
  await expect(page.getByLabel('Template snapshot').nth(1)).toHaveValue('Answer {{customer_message}} for order {{order_id}}. Add escalation guidance.')
  await page.goBack()
  await page.goBack()
  await page.getByRole('link', { name: 'View lineage' }).click()
  await expect(page.getByRole('heading', { name: 'Version lineage' })).toBeVisible()
  await expect(page.getByText(/descends through 2 earlier versions/)).toBeVisible()

  await page.goto(projectUrl)
  await page.getByRole('button', { name: /Members/ }).click()
  await page.locator('.member-row').filter({ hasText: memberEmail }).getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByText(`Member ${suffix} was removed.`)).toBeVisible()
  await memberPage.reload()
  await expect(memberPage.getByRole('heading', { name: updatedProjectName })).toHaveCount(0)
  await memberPage.close()
})
