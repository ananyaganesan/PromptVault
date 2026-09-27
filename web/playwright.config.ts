import { defineConfig, devices } from '@playwright/test'

const liveStack = process.env.E2E_LIVE === '1'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: liveStack ? 1 : undefined,
  reporter: 'list',
  use: { baseURL: liveStack ? 'http://localhost:5173' : 'http://127.0.0.1:4173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
    { name: 'desktop-firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'mobile-chrome', use: { ...devices['iPhone 13'], browserName: 'chromium', channel: 'chrome' } },
    { name: 'mobile-chrome-320', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true } },
    { name: 'tablet-chrome-768', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true } },
  ],
  webServer: liveStack ? undefined : { command: 'npm run dev -- --host 127.0.0.1 --port 4173', url: 'http://127.0.0.1:4173/login', reuseExistingServer: !process.env.CI, timeout: 30_000 },
})
