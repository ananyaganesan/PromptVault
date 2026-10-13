# PromptVault live demo runbook

## Setup

From the repository root:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Open `http://localhost:5173`. Swagger UI is available at `http://localhost:8000/docs`.

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These are local-development fixtures. Use separate browser tabs when showing both roles because sessions are tab-scoped.

## Presentation walkthrough (10–12 minutes)

1. **Authentication (1 minute).** Sign in as User, reload `/dashboard` to show session restoration, then briefly show that `/admin` resolves to the access-restricted screen.
2. **Project and membership (1 minute).** Open Projects, create a uniquely named project, and invite a registered teammate using an inbox you can access. Show the pending invitation and unchanged member count. Open the emailed link, sign in as the recipient, and click Accept invitation before showing project access. Re-inviting a pending or existing member demonstrates conflict feedback. Use local SMTP capture for seeded example addresses.
3. **Prompt versions (1.5 minutes).** Create a prompt containing `{{customer_message}}`. Save v2 and v3 with commit messages, then open history, v3 detail, diff, and lineage. Reload to demonstrate persistence and immutable snapshots.
4. **Run history (1 minute).** Open Playground, provide every variable, and run the selected version. Show output, token counts, latency, and status; then open its run detail and Runs.
5. **Staging and production (1.5 minutes).** Create a staging deployment and show immediate activation. Create a production deployment and show that it remains pending.
6. **Runtime token (1 minute).** Open API Tokens, issue a project-scoped token, and call out that its secret is visible once. Keep it temporarily for the Serve check.
7. **Atomic approval (1 minute).** In the Super Admin tab, open Approvals, inspect the pending release, add evidence, and approve it. A repeated decision is rejected as a conflict rather than rewriting history.
8. **Serve and rollback (1 minute).** Fetch the active production prompt with the runtime token using the example in Swagger or `examples/production-deployment/`. Perform an admin rollback to the prior version and fetch again; the served version changes while deployment history remains append-only.
9. **Recent activity (1 minute).** Open the User dashboard and show four persisted runs in Recent activity. Filter Deployments by project, then clear the filter.
10. **Governance (1 minute).** Show users, organization runs, encrypted provider-key metadata, audit filters, and maintenance status. Provider and runtime secrets never appear in list views.
11. **Revocation (30 seconds).** Revoke the runtime token and show that the same Serve request returns `401`.
12. **Logout (30 seconds).** Sign out and show that an unauthenticated `/dashboard` visit returns to login.

## Expected evidence

- Created records survive reloads and appear in PostgreSQL-backed lists.
- A normal user cannot open Super Admin routes, and the API independently returns forbidden responses.
- Version saves, production decisions, budget consumption, and rollback use transaction-safe database operations.
- Run totals reconcile with personal costs; blocked runs remain visible without adding spend.
- Provider-key plaintext and runtime-token plaintext are never returned by list endpoints.

## Recovery and fallback

Reset to deterministic development data, then refresh the API connection pool:

```bash
docker compose run --rm migrate python scripts/reset-development.py --confirm-reset \
  && docker compose restart api \
  && docker compose up -d --wait
```

If the browser keeps an old identity, sign out or clear the tab's session storage. If a service is unhealthy, inspect `docker compose ps` and `docker compose logs api`. The deterministic mock provider does not require an external LLM key, so the core walkthrough remains reproducible offline after images and dependencies are present.

Password-recovery email requires SMTP settings in `.env`; the core walkthrough does not depend on email delivery. Do not enter production secrets into the demo stack.

## Verification

The exact automated commands and coverage boundaries are documented in [testing.md](testing.md). Cross-browser results are recorded in [browser-smoke.md](browser-smoke.md), and committed visuals are listed in [screenshots/README.md](screenshots/README.md).
