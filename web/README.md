# PromptVault frontend

This is a React/Vite frontend prototype. Routes cover User and Super Admin screens. Authentication, projects, prompts, runs, deployments, budgets, and administration currently have in-memory demo implementations; the typed API client and real-mode service paths are present but require a running backend.

## Start

```sh
npm ci
cp .env.example .env.local
npm run dev
```

The default `.env.example` enables mock runs, deployments, and admin data. Keep those flags on for the standalone demo. See [the demo runbook](../docs/demo-runbook.md) for credentials and a walkthrough.

## Quality checks

```sh
npm run typecheck
npm run lint
npm test
npm run coverage
npm run build
npm run test:e2e
```

`test:e2e` launches Vite and system Chrome, covering desktop and mobile viewports. Install Google Chrome locally for browser tests. `npm run screenshots` refreshes [demo images](../docs/screenshots/README.md). Browser traces and failure images appear under `test-results/`; these are generated artifacts, not source files.

## Frontend boundaries

- Demo login credentials and role routing are frontend-only. Real security requires server-issued sessions and server-enforced permissions.
- Demo records are in memory and reset on reload. Session restoration in the current tab is for presentation only.
- Password recovery is deliberately marked unavailable instead of claiming an email was sent.
- Never use the demo accounts or mock token flow for production traffic.
