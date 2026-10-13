import { expect, test } from '@playwright/test'
import { invitationLink } from './support/invitations'
import { databaseRows } from './support/database'

test.skip(process.env.E2E_LIVE !== '1' || !process.env.E2E_MAILBOX_DIR || !process.env.E2E_DATABASE_URL, 'Requires isolated database and local SMTP capture.')
const api = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8005/api/v1'

test('email invitation requires recipient login and explicit acceptance before project access', async ({ page, request }) => {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  const email = `invited-${suffix}@example.com`
  const ownerEmail = `inviter-${suffix}@example.com`
  const password = 'InvitationDemo2026!'
  const owner = await request.post(`${api}/auth/register`, { data: { email: ownerEmail, display_name: 'Invitation owner', password } })
  expect(owner.status()).toBe(201)
  const ownerHeaders = { Authorization: `Bearer ${(await owner.json()).access_token}` }
  const recipient = await request.post(`${api}/auth/register`, { data: { email, display_name: 'Invited member', password } })
  expect(recipient.status()).toBe(201)
  const recipientHeaders = { Authorization: `Bearer ${(await recipient.json()).access_token}` }
  const created = await request.post(`${api}/projects`, { headers: ownerHeaders, data: { name: `Invitation ${suffix}`, key: `invitation-${suffix}` } })
  expect(created.status()).toBe(201)
  const project = await created.json()
  const invitation = await request.post(`${api}/projects/${project.id}/members`, { headers: ownerHeaders, data: { email } })
  expect(invitation.status()).toBe(201)
  expect((await request.get(`${api}/projects/${project.id}`, { headers: recipientHeaders })).status()).toBe(403)
  expect(databaseRows('SELECT count(*) AS count FROM project_members WHERE project_id=%s', [project.id])[0].count).toBe(1)
  const link = invitationLink(email, project.name)
  await page.goto(link)
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Project invitation' })).toBeVisible()
  expect((await request.get(`${api}/projects/${project.id}`, { headers: recipientHeaders })).status()).toBe(403)
  await page.getByRole('button', { name: 'Accept invitation', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Invitation accepted. You now have project access.')
  expect(databaseRows('SELECT count(*) AS count FROM project_members WHERE project_id=%s', [project.id])[0].count).toBe(2)
  await page.getByRole('link', { name: 'Open project' }).click()
  await expect(page.getByRole('heading', { name: project.name })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: project.name })).toBeVisible()
  await page.goto(link)
  await page.getByRole('button', { name: 'Accept invitation', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Invitation is expired, cancelled or already accepted')
})
