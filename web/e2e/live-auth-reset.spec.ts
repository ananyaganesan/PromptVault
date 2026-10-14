import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { databaseRows, executeTestDatabase } from './support/database'

test.skip(process.env.E2E_LIVE !== '1' || !process.env.E2E_MAILBOX_DIR || !process.env.E2E_DATABASE_URL, 'Requires local SMTP capture and an isolated database.')
const api = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8005/api/v1'
type CapturedMessage = { recipient: string; subject: string; text: string }

function capturedMessages(email: string, subject: string): CapturedMessage[] {
  const mailbox = process.env.E2E_MAILBOX_DIR!
  return readdirSync(mailbox)
    .filter((name) => name.endsWith('.json'))
    .map((name) => JSON.parse(readFileSync(join(mailbox, name), 'utf8')) as CapturedMessage)
    .filter((message) => message.recipient === email && message.subject === subject)
}

test('registration, reset email, password history, revoked sessions and logout work together', async ({ page, request, isMobile }) => {
  expect(String(databaseRows('SELECT current_database() AS name')[0].name)).toMatch(/_test$/)
  const email = `auth-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`
  const original = 'OriginalPassword2026!'
  const replacement = 'ReplacementPassword2026!'
  await page.goto('/register')
  await page.getByLabel('Display name').fill('Auth acceptance')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(original)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText(email)).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))).toBeNull()

  const firstVerification = capturedMessages(email, 'Verify your PromptVault email')
  expect(firstVerification).toHaveLength(1)
  const firstVerificationUrl = firstVerification[0].text.match(/http:\/\/127\.0\.0\.1:5178\/verify-email\?token=[\w-]+/)![0]
  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(original)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toHaveText('Verify your email before signing in')
  executeTestDatabase(
    "UPDATE email_verification_tokens SET created_at=now()-interval '2 seconds' WHERE user_id=(SELECT id FROM users WHERE email=%s)",
    [email],
  )
  await page.getByRole('button', { name: 'Resend verification email' }).click()
  await expect(page.getByText('If this account is awaiting verification, we sent a new link.')).toBeVisible()
  const verifications = capturedMessages(email, 'Verify your PromptVault email')
  expect(verifications).toHaveLength(2)
  const secondVerificationUrl = verifications
    .map((message) => message.text.match(/http:\/\/127\.0\.0\.1:5178\/verify-email\?token=[\w-]+/)![0])
    .find((url) => url !== firstVerificationUrl)!
  await page.goto(firstVerificationUrl)
  await expect(page.getByRole('alert')).toHaveText('Email verification link is invalid or expired')
  await page.goto(secondVerificationUrl)
  await expect(page.getByText('Your email has been verified.')).toBeVisible()
  await page.getByRole('link', { name: 'Sign in' }).click()
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(original)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Auth' })).toBeVisible()
  const oldToken = await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))
  const secondSession = await request.post(`${api}/auth/login`, { data: { email, password: original } })
  expect(secondSession.status()).toBe(200)
  const secondToken = (await secondSession.json()).access_token

  const expiredEmail = `expired-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`
  const expiredRegistration = await request.post(`${api}/auth/register`, {
    data: { email: expiredEmail, password: original, display_name: 'Expired verification' },
  })
  expect(expiredRegistration.status()).toBe(202)
  const expiredVerification = capturedMessages(expiredEmail, 'Verify your PromptVault email')
  expect(expiredVerification).toHaveLength(1)
  const expiredUrl = expiredVerification[0].text.match(/http:\/\/127\.0\.0\.1:5178\/verify-email\?token=[\w-]+/)![0]
  executeTestDatabase(
    'UPDATE email_verification_tokens SET expires_at=now()-interval \'1 second\' WHERE user_id=(SELECT id FROM users WHERE email=%s)',
    [expiredEmail],
  )
  await page.goto(expiredUrl)
  await expect(page.getByRole('alert')).toHaveText('Email verification link is invalid or expired')

  await page.goto('/forgot-password')
  await page.getByLabel('Email address').fill(email)
  await page.getByRole('button', { name: 'Send reset link' }).click()
  await expect(page.getByText(/If this email belongs to an active account/)).toBeVisible()
  const delivered = capturedMessages(email, 'Reset your PromptVault password')[0]
  expect(delivered).toBeDefined()
  const resetUrl = delivered!.text.match(/http:\/\/127\.0\.0\.1:5178\/reset-password\?token=[\w-]+/)![0]
  const token = new URL(resetUrl).searchParams.get('token')!
  expect(databaseRows('SELECT t.used_at IS NULL AS unused, t.token_hash=%s AS hashed FROM password_reset_tokens t JOIN users u ON u.id=t.user_id WHERE u.email=%s', [createHash('sha256').update(token).digest('hex'), email])).toEqual([{ unused: true, hashed: true }])
  await page.goto(resetUrl)
  await page.getByLabel('New password', { exact: true }).fill(original)
  await page.getByLabel('Confirm password').fill(original)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByRole('alert')).toHaveText('Choose a password you have never used for this account')
  await page.getByLabel('New password', { exact: true }).fill(replacement)
  await page.getByLabel('Confirm password').fill(replacement)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByText('Your password has been reset. You can now sign in.')).toBeVisible()
  for (const revoked of [oldToken, secondToken]) {
    expect((await request.get(`${api}/auth/me`, { headers: { Authorization: `Bearer ${revoked}` } })).status()).toBe(401)
  }
  await page.goto('/dashboard')
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto(resetUrl)
  await page.getByLabel('New password', { exact: true }).fill('AnotherPassword2026!')
  await page.getByLabel('Confirm password').fill('AnotherPassword2026!')
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByRole('alert')).toHaveText('Password reset link is invalid or expired')

  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(original)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password.')
  await page.getByLabel('Password', { exact: true }).fill(replacement)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  const currentToken = await page.evaluate(() => sessionStorage.getItem('promptvault.api.session'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Good morning, Auth' })).toBeVisible()
  if (isMobile) await page.getByRole('button', { name: 'Open navigation' }).click()
  const logout = page.waitForResponse((response) => response.url().endsWith('/auth/logout') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Sign out' }).click()
  expect((await logout).status()).toBe(204)
  await expect(page).toHaveURL(/\/login$/)
  expect((await request.get(`${api}/auth/me`, { headers: { Authorization: `Bearer ${currentToken}` } })).status()).toBe(401)
  expect(databaseRows('SELECT t.used_at IS NOT NULL AS consumed FROM password_reset_tokens t JOIN users u ON u.id=t.user_id WHERE u.email=%s', [email])).toEqual([{ consumed: true }])
  await page.goto('/reset-password')
  await expect(page.getByRole('heading', { name: 'Invalid reset link' })).toBeVisible()
})
