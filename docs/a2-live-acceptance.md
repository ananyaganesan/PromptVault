# A2 repository audit and live acceptance

Audit date: 2026-10-11. Baseline revision: `841a95924045e221bd7042af176f0000cfeccdee`.
The backend, frontend, acceptance suite and plan changes are uncommitted additions to
that baseline; this is local integration evidence, not a production release sign-off.

## Why A2 starts first

The repository already integrates the six workflows with real APIs. Frontend
generation guards, mutation notifications, controlled refresh, pagination helpers,
and dirty-editor protection have unit coverage. `web/e2e/live-data-freshness.spec.ts`
existed but its live SQL and browser acceptance had not been closed. Running that
suite is the shortest path to verifying existing work and finding actual defects.

The audit covered the repository inventory, frontend services/pages/tests, FastAPI
routers/services/repositories/providers, migrations/seeds, security/concurrency
tests, Docker/CI/release configuration, and requirements/design documentation.

| Task | Repository evidence | Resulting priority/change |
|---|---|---|
| A1 | `providers/factory.py` only selects mock; `gemini.py` is empty. `RunExecutionService.execute` calls the provider before the budget record. The UI already executes `/runs` and renders persisted details. | Split into agreed discovery/execution contract and integration after J1/J2. Do not enable paid execution before admission/idempotency. |
| A2 | Existing live suite, refresh controls, all-page workspace loading, stale-response guards, dirty editor protections. | Run isolated acceptance first; retain staging and concurrency gates. |
| A3 | No verification columns/token table/routes/template; public registration currently issues a session immediately. Reset tokens/mail provide a reusable pattern. | Agree signup, verification and access behavior; design ER/schema/contract before migration. |
| A4 | `users.display_name` exists; Profile is read-only; no self-profile update endpoint. | A bounded independent follow-on after agreeing editable fields and authorization. No new table needed for display name. |
| A5 | Login, `/auth/me`, tab session storage, reset page/email and history already exist; no session revocation integration. | Reuse existing work; production session behavior depends on J3 and verification policy. |
| A6 | Live browser/accessibility/mobile suites exist. | Extend and execute on staging after integrations; avoid duplicating prototype work. |
| A7 | Migrations/showcase/ER/normalization exist; academic checklist identifies missing auth-table mapping and explicit PROCEDURE/CALL evidence. | Maintain design/dictionary alongside changes; collect final evidence last. |
| A8 | Vite API configuration, Nginx SPA fallback, CI and clean-checkout backend verifier exist. | Add production configuration/reporting/support and CI live-browser gates; routing setup precedes final hosted acceptance. |

## Implemented acceptance changes

- Require the reconciliation database name to end in `_test`; SQL assertions use a
  read-only transaction. New fixture IDs must exist in the selected SQL database.
- Correct revoked-project access expectation to the existing 403 contract. Version
  access remains 404. No authorization behavior was loosened to make tests pass.
- Check an unsaved template and commit survive a member's new version; saving stays
  blocked until the user explicitly resolves the stale parent.
- Create 101 projects/prompts, completed mock runs, active development deployments,
  pending production requests, and 101 versions of one prompt. Compare complete
  API page traversal to SQL IDs/counts and check uniqueness. Verify the UI discovers
  the oldest project/version/active deployment and all pending approvals beyond 100.
- Verify an unrelated newly registered account receives empty scoped lists and
  dashboard counts, cannot read project/version/run details or the admin queue, and
  cannot display private run output in the browser.
- Reconcile dashboard month counts using the API's month and budget timezone,
  rather than assuming the PostgreSQL server's month/timezone.
- Delay a real failed-run list response until a newer completed-run filter response
  has rendered; verify the old response cannot replace newer results or filters.
- Retain original persisted output/token/latency/timestamp, recent activity, retry,
  pagination, approval, active deployment, and token revocation checks.

## Reproduce

Run from the repository root. This creates a dedicated Compose project and volume;
it does not reset or repair the original or preview databases. SMTP is disabled.
The credentials below are public development fixtures, only for this local stack.

```sh
COMPOSE_PROJECT_NAME=promptvault-a2-20261011 \
POSTGRES_DB=promptvault_a2_final_test POSTGRES_PORT=55434 \
API_PORT=8002 WEB_PORT=5175 VITE_API_URL=http://localhost:8002 \
CORS_ORIGINS=http://localhost:5175 \
SMTP_HOST= SMTP_USERNAME= SMTP_PASSWORD= SMTP_FROM_EMAIL= \
docker compose up -d --build --wait

E2E_LIVE=1 E2E_BASE_URL=http://localhost:5175 \
E2E_API_BASE_URL=http://localhost:8002/api/v1 \
E2E_DATABASE_URL=postgresql://promptvault:promptvault@localhost:55434/promptvault_a2_final_test \
npm --prefix web run test:e2e -- e2e/live-data-freshness.spec.ts --project=desktop-chrome --project=mobile-chrome
```

Python defaults to `.venv/bin/python` and requires psycopg; `E2E_PYTHON` can select
another installed interpreter. API, browser and SQL must target the same isolated
stack. The suite creates uniquely named fixtures on every run; records intentionally
remain for inspection. Use a new Compose project/database/ports for a fresh run.
Playwright retains traces/screenshots on failures in ignored `web/test-results`.

## Verification

- Backend: all **325 tests passed**, including the eleven new PostgreSQL concurrency
  regressions. The backend test database is `promptvault_a2_backend_test`, separate
  from browser acceptance data. Backend lint and strict mypy passed.
- Frontend: all **132 unit tests passed**; lint, application typecheck and production
  build passed. The packaged Docker frontend also passed typecheck/build.
- Generated OpenAPI matches `docs/openapi.json`; `git diff --check` passed. No schema,
  endpoint, query-filter or JSON response contract change was required.
- The initial desktop/mobile browser run passed nine cases and found one desktop-only
  navigation selector in the mobile project. The test now opens the real mobile menu.
  The failed run is retained in `evidence/a2/2026-10-11-browser-before-mobile-navigation-fix.json`.
- Final browser acceptance: **10 passed, zero skipped/failing/flaky**, in 1.8 minutes
  on a fresh `promptvault_a2_final_test` database against the rebuilt final working
  tree. The corrected mobile navigation case passed. See the
  [final browser report](../evidence/a2/2026-10-11-browser-final.json) and
  [final reconciliation/source fingerprints](../evidence/a2/2026-10-11-final-reconciliation.json).

| Final scope | API | PostgreSQL |
|---|---:|---:|
| User-accessible projects | 211 | 211 |
| Accessible completed deterministic runs | 234 | 234 |
| Active development deployments | 202 | 202 |
| Global pending production approvals (admin) | 202 | 202 |
| Selected prompt's version history | 101 | 101 |
| Personal October runs (UTC budget timezone) | 234 | 234 |

The four most recent personal run IDs matched exactly. Source SHA-256 values identify
the tested changed/new application and test files in the uncommitted working tree.

The [initial API/SQL capture](../evidence/a2/2026-10-11-reconciliation.json) is retained
as historical evidence from the first acceptance batch. Final evidence uses the fresh
database and is captured after final browser acceptance. Counts include development
seeds and acceptance fixtures, never production records. Credentials, password hashes,
tokens and output bodies are excluded from reconciliation evidence. Negative access
checks assert exact expected denials rather than accepting any error response.

Application TypeScript checks cover `web/src`. The checkout lacks `@types/node` for
a separate strict Playwright check; Playwright successfully executes its transpiled
tests. This does not substitute for application typecheck.

To reproduce backend verification, create a separate disposable `_test` database in
the isolated container before running tests (the root fixtures rebuild its schema):

```sh
docker compose -p promptvault-a2-20261011 exec -T db \
  createdb -U promptvault promptvault_a2_backend_test
TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:55434/promptvault_a2_backend_test \
  .venv/bin/python -m pytest -q api/tests tests
```

Use the existing backend database on subsequent runs; omit `createdb` if it exists.
Do not point backend reset fixtures at the browser acceptance or original database.

## Concurrency gaps resolved

1. Projects, members, prompts, versions, runs (including admin runs), deployments
   and pending approvals now use `repositories/pagination.py::read_page`: one SQL
   statement returns both count and rows, with the original stable ordering and
   filters. Its LEFT JOIN preserves totals for empty and out-of-range pages. Other
   admin lists outside A2 retain their previous implementation. No migration or new
   read endpoint was needed; all API response/query shapes remain unchanged.
2. Workspace loading, active deployment selection and approval queues share
   `readAllPages`. Multi-page reads require two identical complete traversals.
   Drifting totals, duplicates, missing rows and same-count replacements/updates
   trigger a restart, with at most four traversals and 10,000 pages per traversal.
   Persistently changing data produces a retryable error; the previous workspace
   snapshot and unsaved editor fields remain available rather than publishing a
   truncated result. Single-page reads need only one coherent response.
3. Prompt detail and lineage hold existing project-membership KEY SHARE locks
   through their read transaction. A membership removal either precedes the access
   check (denial) or waits until that admitted read finishes. Subsequent requests
   after removal are denied. Existing write locks and race coverage are retained.
4. Personal dashboard authentication, budget/timezone, metrics, trend and recent
   runs share one dedicated read-only REPEATABLE READ transaction. Ordinary write
   and locking workflows keep their existing READ COMMITTED isolation. The explicit
   dependency works independently of hosted URL prefixes and uses one pool connection.

`tests/concurrency/test_read_freshness.py` supplies eleven PostgreSQL regressions:
eight list cases commit a change between SQL execution and row consumption, one
inserts a run between dashboard metric/activity reads, and two attempt membership
revocation during prompt/lineage assembly. It also covers empty/out-of-range pages
and verifies that the next read sees the committed change. Frontend pagination
regressions test retries, unchanged-count updates, bounded failure, and preservation
of the previous workspace after a failed refresh.

Refresh semantics are **eventual across independent HTTP resources**. Each API page
is coherent, the dashboard is a coherent transaction snapshot, and multi-page reads
are validated for stability. The application does not claim a historical database
snapshot spanning every screen or guarantee convergence during continuous writes.
Controlled refresh after writes settle reconciles the six workflows with SQL;
sustained drift is surfaced instead of silently truncating or overwriting drafts.

Run ownership intentionally also permits access to one's own recorded runs; loss of
project membership does not automatically revoke the author's own ledger access.
Independent organizations are not implemented: the current administrator is global.
Tenancy decisions and J4 review remain necessary before promising tenant isolation.

## Completion boundary

A2's implementation and isolated PostgreSQL acceptance are complete. Hosted sign-off
remains pending: no staging
URL, isolated staging SQL connection or staging account has been supplied, and no
hosted target is configured in the repository. Repeat the same checks on the exact
release revision once staging exists; keep that release gate unchecked. Joint review
of authorization remains part of J4. Hosted HTTPS, Gemini, verification, session
revocation, backup recovery, and joint product decisions are outside this batch.
