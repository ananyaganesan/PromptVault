# PromptVault frontend prototype demo

## Setup

From `web/`, run `npm ci`, copy `.env.example` to `.env.local`, set `VITE_USE_MOCK_AUTH=true`, and run `npm run dev`. Open the URL printed by Vite. Leave the other `VITE_USE_MOCK_*` flags set to `true`; the backend is not required for this UI demo. Use a fresh browser tab if you want the seeded starting state. The mock stores live in memory, so reloading resets projects, runs, deployments, and tokens created during the demo.

Demo credentials:

| Role | Email | Password | Landing page |
| --- | --- | --- | --- |
| User | `user@promptvault.dev` | `UserDemo2026!` | Dashboard |
| Alice | `alice@promptvault.dev` | `AliceDemo2026!` | Dashboard |
| Bob | `bob@promptvault.dev` | `BobDemo2026!` | Dashboard |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` | Administration overview |
| Inactive user | `inactive@promptvault.dev` | `InactiveDemo2026!` | Login denied |

These credentials are public prototype fixtures. Never use them in a deployed environment.

## Suggested walkthrough (10–12 minutes)

1. Sign in as User. Show the live dashboard counts, run activity, spend trend, and responsive navigation. Reload to demonstrate session restore.
2. Open Projects. Create a project, add a member, and show duplicate-member feedback. Create a prompt with a `{{customer_message}}` variable.
3. Save a new prompt version. Open version detail, compare, and lineage. Explain that versions are immutable snapshots in the frontend store.
4. Open Playground. Choose the checkout prompt, enter required variables, and execute a successful mock run. Repeat with Provider failure and Budget limit scenarios; show the run history and detail pages.
5. Open Costs. Show recorded mock spend and budget utilization.
6. Open Deployments. Create a staging deployment, then request a production deployment. Show the pending state. Issue an API token and explain that its secret is shown once; revoke it after copying is no longer needed.
7. Sign out and sign in as Super Admin. Review the pending production request, inspect the evidence, and approve or reject it. Show rollback, user/role management, budgets, model pricing, provider-key metadata, audit log, and maintenance views.
8. Sign out. Show that a User cannot open `/admin` and that unauthenticated visits to `/dashboard` return to login.

## Recovery and caveats

- Refresh to restore the seeded mock data if a demo action leaves an undesirable state. Sign out if you need to switch roles.
- Mock registration creates a User account only in the current running tab. Password recovery does not send email.
- The provider output, spending, approvals, and token flows are frontend simulations. They do **not** prove real provider calls, server-side budget enforcement, persistent storage, backend authorization, or secure token serving.
- Real API login and registration are available when `VITE_USE_MOCK_AUTH=false` and FastAPI is running. The remaining application API mode flags depend on backend endpoints that are not implemented yet; keep those flags `true` for this walkthrough.
- No production secrets should be entered into the prototype.

## Verification and visuals

Run `npm run typecheck`, `npm run lint`, `npm test`, `npm run coverage`, `npm run build`, and `npm run test:e2e` from `web/`. The browser suite covers desktop Chrome and an iPhone-sized Chrome viewport. See the [browser smoke record](browser-smoke.md). Recreate the eight committed screenshots with `npm run screenshots`; see [screenshots](screenshots/README.md).
