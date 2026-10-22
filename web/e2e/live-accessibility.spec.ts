import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test.skip(process.env.E2E_LIVE !== '1', 'Runs only against the Docker-backed live stack.')
test.setTimeout(90_000)

async function signIn(page: Page, role: 'user' | 'admin') {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(`${role}@promptvault.dev`)
  await page.getByLabel('Password', { exact: true }).fill(role === 'admin' ? 'AdminDemo2026!' : 'UserDemo2026!')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

async function verifyRoutes(page: Page, routes: string[]) {
  const issues: string[] = []
  for (const route of routes) {
    await page.goto(route)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `${route} has horizontal overflow` }).toBe(true)
    const tableIssues = await page.locator('.table-panel table').evaluateAll((tables) => tables.flatMap((table) => {
      const headings = [...table.querySelectorAll('thead th')]
      const cells = [...(table.querySelector('tbody tr')?.querySelectorAll('td') ?? [])]
      if (!cells.length) return []
      return cells.flatMap((cell, index) => {
        const heading = headings[index]
        if (!heading) return [`missing heading for column ${index + 1}`]
        const headerBox = heading.getBoundingClientRect()
        const cellBox = cell.getBoundingClientRect()
        return Math.abs(headerBox.left - cellBox.left) > 2 || Math.abs(headerBox.width - cellBox.width) > 2
          ? [`column ${index + 1} is misaligned`]
          : []
      })
    }))
    expect(tableIssues, `${route} table columns`).toEqual([])
    const result = await new AxeBuilder({ page }).analyze()
    issues.push(...result.violations
      .filter((item) => item.impact === 'critical' || item.impact === 'serious')
      .map((item) => `${route}: ${item.id} (${item.nodes.map((node) => node.target.join(' ')).join(', ')})`))
  }
  expect(issues).toEqual([])
}

async function typography(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      color: style.color,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
      lineHeight: style.lineHeight,
    }
  })
}

test('user routes are responsive and have no serious automated accessibility violations', async ({ page }) => {
  await page.goto('/login')
  const login = await new AxeBuilder({ page }).analyze()
  expect(login.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious')).toEqual([])
  await signIn(page, 'user')
  await verifyRoutes(page, ['/dashboard', '/projects', '/prompts', '/playground', '/runs', '/deployments', '/api-tokens', '/profile'])
})

test('admin routes are responsive and have no serious automated accessibility violations', async ({ page }) => {
  await signIn(page, 'admin')
  await verifyRoutes(page, ['/admin/approvals', '/admin/rollback', '/admin/users', '/admin/provider-keys', '/admin/runs', '/admin/audit'])
})

test('project members use the global typography hierarchy', async ({ page }) => {
  await signIn(page, 'admin')
  await page.goto('/projects')
  await page.locator('.project-card').first().click()
  await page.getByRole('button', { name: /Members/ }).click()

  await expect(page.locator('.members-panel')).toBeVisible()
  expect(await typography(page, '.member-subheading')).toEqual(await typography(page, '.members-panel .panel-head h2'))

  const secondary = await typography(page, '.page-header p')
  expect(await typography(page, '.member-invitation-note')).toEqual(secondary)
  expect(await typography(page, '.member-email')).toEqual(secondary)
  if (await page.locator('.member-empty-invitations').count()) {
    expect(await typography(page, '.member-empty-invitations')).toEqual(secondary)
  }

  const primary = await typography(page, '.members-panel')
  expect(await typography(page, '.member-name')).toEqual(primary)

  const tokens = await page.locator(':root').evaluate((root) => {
    const style = getComputedStyle(root)
    return {
      caption: style.getPropertyValue('--pv-type-caption').trim(),
      label: style.getPropertyValue('--pv-type-table-heading').trim(),
      semibold: style.getPropertyValue('--pv-weight-semibold').trim(),
    }
  })
  const avatar = await typography(page, '.member-avatar')
  expect(avatar.fontSize).toBe(tokens.caption)
  expect(avatar.fontWeight).toBe(tokens.semibold)
  const role = await typography(page, '.member-role')
  expect(role.fontSize).toBe(tokens.label)
  expect(role.fontWeight).toBe(tokens.semibold)
})
