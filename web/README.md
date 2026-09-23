# PromptVault frontend

This is a React/Vite frontend prototype with User and Super Admin screens. Login and registration use the PostgreSQL-backed FastAPI endpoints by default. Projects, runs, deployments, budgets, and administration remain in-memory demo workflows until their backend APIs are implemented. Prompt and version workflows are available through the backend API only.

## Start

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Start the backend first using the [root README](../README.md), then sign in with one of the [seeded database accounts](../README.md#frontend-with-database-backed-login), including `user@promptvault.dev` / `UserDemo2026!` and `admin@promptvault.dev` / `AdminDemo2026!`. The seed also includes Alice and Bob accounts plus an inactive account for testing denied login. Registration sends `display_name`, `email`, and a password of at least 12 non-whitespace characters to FastAPI. The backend stores an Argon2 password hash and assigns the `user` role. Spaces are removed from the password field, and the registration API rejects whitespace. The browser keeps the returned JWT in tab session storage and validates it on refresh, so a valid session remains signed in within that tab. Signing out clears the token.

For a standalone UI demo without FastAPI, set `VITE_USE_MOCK_AUTH=true` in `.env.local` and restart Vite. That mode uses browser-only copies of the same development credentials listed above. The other `VITE_USE_MOCK_*` flags stay enabled for the prototype workflows. See [the demo runbook](../docs/demo-runbook.md).

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

- FastAPI authenticates database users and enforces access for its implemented endpoints. UI route guards are presentation only; future application APIs must enforce their own permissions.
- Project, prompt, run, deployment, budget, and admin records still live in browser memory and reset on reload. They are not persisted to PostgreSQL yet.
- `VITE_USE_MOCK_AUTH=true` is only for the standalone demo and never writes users to PostgreSQL.
- Password recovery is deliberately marked unavailable instead of claiming an email was sent.
- Never use the demo accounts or mock token flow for production traffic.
