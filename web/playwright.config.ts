import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
    { name: 'mobile-chrome', use: { ...devices['iPhone 13'], browserName: 'chromium', channel: 'chrome' } },
    { name: 'mobile-chrome-320', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true } },
    { name: 'tablet-chrome-768', use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true } },
  ],
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4173', url: 'http://127.0.0.1:4173/login', reuseExistingServer: !process.env.CI, timeout: 30_000 },
})
