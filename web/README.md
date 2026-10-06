# PromptVault web client

This React/Vite client authenticates through FastAPI and loads workspace data from PostgreSQL through the API by default. Example workspace data is used in isolated tests or when `VITE_USE_DEMO_DATA=true` is explicitly set for local development; it never accepts credentials or creates sessions. The Docker web build always uses the live API data path.

## Development

Start the API and database from the repository root, then run the frontend:

```bash
docker compose up -d db migrate api --wait
npm ci --prefix web
cp web/.env.example web/.env.local
npm run dev --prefix web
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000`; the client appends `/api/v1`. Keep `VITE_USE_DEMO_DATA=false` to use persisted workspace data. Login always calls `/api/v1/auth/login`, and saved tokens are checked with `/api/v1/auth/me` before a user is restored. The packaged full stack is available with `docker compose up -d --build --wait` and serves the web application at `http://localhost:5173`. Docker excludes local Vite override files and uses its `VITE_API_URL` build argument for the packaged API address.

Development accounts:

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These accounts are local fixtures. JWTs are stored in tab-scoped `sessionStorage`, while authorization is enforced by FastAPI.

## Routes

- `/dashboard`, `/projects`, `/prompts`, `/playground`, `/runs`, `/deployments`, and `/api-tokens` are authenticated User experiences.
- `/admin/*` contains approval and governance experiences and requires the Super Admin role.
- `/403` is the authenticated forbidden-state recovery route.
- Unknown resources display explicit not-found states.

Password-recovery email delivery works when SMTP is configured; without SMTP, the API reports that delivery is unavailable. The mock provider is deterministic. Runs, deployments, and audit records persist through the backend. The web interface omits monetary reporting and administration; the backend ledger remains available for execution safeguards.

## Verification

```bash
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run coverage --prefix web
npm run build --prefix web
```

Run the live workflows against the Docker stack:

```bash
npm exec --prefix web playwright install firefox
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=mobile-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-firefox
```

The live suites cover real persistence, authorization recovery, the version/run/deployment/governance workflows, responsive layout, and serious/critical axe-core accessibility checks. Generated traces and failure images are written below `web/test-results/`.

Refresh the committed live-stack screenshots with:

```bash
npm run screenshots --prefix web
```

See the [demo runbook](../docs/demo-runbook.md) and [browser smoke record](../docs/browser-smoke.md).
