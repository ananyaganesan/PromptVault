# Jobin branch integration acceptance

Date: 2026-10-12. Local `Ananya` was fast-forwarded from `841a959` to
`origin/Jobin` at `89b86b5ca6aea4bf574c72601db6a909e8922331` (27 commits).
The pre-existing A2 working tree was preserved in the Git stash named
`A2 work before integrating origin/Jobin 2026-10-12` and restored after the merge.
The stash remains available; A2 and the integration fixes remain uncommitted.

## Integration changes

- Resolve run/admin-run list conflicts with A2's single-statement count/page
  snapshots and Jobin's literal search filters. Both count and item queries join
  prompts so prompt-key search applies consistently.
- Preserve the exported workspace `collectPages` helper while routing it through
  A2's bounded stable-traversal reconciliation. Incomplete results fail without
  publishing truncated workspace data; update its tests for that behavior.
- Update A2 concurrency tests for the new run search argument and exercise prompt
  search during the concurrent commit and empty-page checks.
- Fix a PostgreSQL deadlock observed in concurrent duplicate-run admission. Access
  validation previously took a shared user lock before `reserve_run_execution`
  upgraded it to an exclusive lock. Two admissions could each hold the shared
  lock while waiting for the other's upgrade. Reservation access now acquires
  the exclusive user lock immediately; ordinary run-recording access keeps its
  existing shared lock. Add a regression proving the second admission waits
  before acquiring access and proceeds after the first transaction releases.
- Regenerate OpenAPI using the locked dependencies; generated decimal validation
  patterns are included. Refresh the launch-plan baseline to reflect the incoming
  Gemini, reservation, session and cost-page implementations.

## Validation

- Backend: **394 passed**, zero skipped, **90.10% coverage** against disposable
  PostgreSQL 18. Backend Ruff and strict mypy pass.
- Frontend: **148 passed** across 28 unit-test files; lint, application typecheck
  and production build pass.
- Dependency consistency, generated OpenAPI comparison and Git whitespace checks
  pass. No unresolved merge entries remain.
- Desktop/mobile A2 browser acceptance: **10 passed** in 1.8 minutes. Runs use
  mock execution with SMTP disabled. The API process was started before the
  admission-lock fix; that fix is covered by the final full backend suite above.
  These checks do not establish hosted Gemini/email acceptance.

The initial browser attempt targeted the wrong API because `web/.env.local`
sets `VITE_API_BASE_URL`, which takes precedence over `VITE_API_URL`. The rerun
sets both variables explicitly. The test database timezone is UTC to match CI;
its initial inherited Asia/Kolkata timezone exposed a timestamp-string assertion.

## Disposable database and local stack

No existing application database was migrated, reset or repaired. A separate
cluster was initialized with UTF-8 encoding under
`/private/tmp/promptvault-integration-20261012`, listening only on `127.0.0.1:55435`.
It uses local trust authentication for disposable test data only.

- Backend database: `promptvault_integration_test` (UTC).
- Browser database: `promptvault_integration_browser_test`.
- Local API: `http://127.0.0.1:8003`.
- Local frontend: `http://127.0.0.1:5176`.
- Backend log: `/private/tmp/promptvault-integration-backend-final.txt`.
- Browser log: `/private/tmp/promptvault-integration-browser.txt`.

Re-run backend acceptance from the repository root:

```sh
TEST_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_integration_test \
  .venv/bin/python -m pytest -q api/tests tests \
  --cov=api.app --cov-config=api/pyproject.toml
```

Re-run browser acceptance against the local stack:

```sh
E2E_LIVE=1 E2E_BASE_URL=http://127.0.0.1:5176 \
E2E_API_BASE_URL=http://127.0.0.1:8003/api/v1 \
E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_integration_browser_test \
  npm --prefix web run test:e2e -- e2e/live-data-freshness.spec.ts \
  --project=desktop-chrome --project=mobile-chrome
```

This is local integration evidence, not hosted release sign-off. Re-test the exact
release revision on staging, including the restricted production database role,
real Gemini credentials, HTTPS, email verification/delivery, and recovery.
