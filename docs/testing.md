# Testing strategy

Run all checks from the repository root. Database tests require an isolated PostgreSQL database through `TEST_DATABASE_URL`; fixtures apply migrations and development seeds before tests execute.

```bash
export TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
ruff check api scripts tests
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml --cov-report=term-missing
```

## Run and budget coverage

- `api/tests/unit/test_providers_costs.py` proves deterministic provider output/usage, bounded timeout normalization, exact-variable rendering, and decimal cost rounding.
- `api/tests/integration/test_runs_dashboard.py` exercises real HTTP routes and PostgreSQL persistence for completed, failed, blocked, filtered, scoped, and aggregated run behavior, including membership removal during provider I/O and a single-connection pool-pressure check.
- `tests/database/test_budget_enforcement.py` proves zero, unlimited, exact, overlapping user/project, UTC month-boundary, and DST wall-time behavior at the database function boundary.
- `tests/concurrency/test_budget_race.py` submits 20 simultaneous charges against one budget and reconciles admitted, blocked, and stored totals.

Failure-path API tests verify that provider errors and budget rejection return a safe public envelope while the corresponding append-only ledger row commits. Unknown or inaccessible run identifiers have the same not-found behavior. Generated OpenAPI is compared byte-for-byte with `docs/openapi.json` so frontend contract drift fails CI.

## Stabilization and storyboard coverage

- `tests/security/` verifies the cross-route authorization matrix, inactive-user and escalation rejection, JWT/runtime-token boundaries, safe validation responses, write-only runtime/provider secrets, and structured-log allowlisting.
- `tests/e2e/` executes the user/project/version/run flow, staging and production approval with forbidden/conflict evidence, Serve token plus rollback/revocation, budget block/recovery, and application-pool restart persistence.
- `tests/concurrency/test_rollback_race.py` proves two same-target rollbacks serialize with one winner and one invalid stale request.
- `tests/performance/test_query_plans.py` loads 2,000 deterministic ledger rows, verifies partition pruning, and asserts user/project/prompt/version histories remain index-backed.

The representative ledger is idempotent and can be loaded manually with `python3 scripts/simulate-traffic.py --runs 2000`. Cross-layer API fixtures recreate and reseed only a database whose name ends in `_test`, giving every security/E2E case an isolated schema; their assertions use per-test identities and exact owned-state counts. Release verification executes the entire suite against a fresh disposable database rather than relying on accumulated local state.

`tests/database/test_migration_upgrade.py` creates temporary databases to verify both a fresh migration chain and the legacy password-reset migration recorded as 011. It checks migration checksums, preserves existing user/reset-token rows, and verifies the project, membership, prompt, version, and reset-token foreign keys.

## Containerized release verification

`python3 scripts/verify-release.py` is the clean-checkout acceptance command. It builds the production-target images, runs the `verification` Compose profile with lint, strict mypy, branch-aware coverage, dependency checks and OpenAPI drift detection, then performs stack smoke tests, concurrency demos, representative-data loading, an isolated PostgreSQL dump/restore drill, and showcase queries. The timestamped command transcript is written below `evidence/release/`; test tooling is absent from the runtime image.

`tests/delivery/` validates the Compose service/dependency contract and the executable demo clients. The web image build runs both TypeScript type checking and the Vite production build. Docker-backed Playwright suites then exercise the connected React/FastAPI/PostgreSQL workflows in desktop Chrome, mobile Chrome emulation, and desktop Firefox; see `docs/browser-smoke.md` for the recorded acceptance boundary.

Run a browser project against the healthy stack with `E2E_LIVE=1 npm --prefix web run test:e2e -- --project=<project>`. Live tests are serial because budget, deployment, and governance cases intentionally mutate shared seeded state. Reset and restart the API between complete browser-project runs for deterministic evidence.

For isolated workspace and admin browser checks, start a separate Compose project from the repository root:

```bash
COMPOSE_PROJECT_NAME=promptvault-ananya-check POSTGRES_PORT=5543 API_PORT=8001 WEB_PORT=5174 VITE_API_URL=http://localhost:8001 CORS_ORIGINS=http://localhost:5174 PASSWORD_RESET_URL=http://localhost:5174/reset-password docker compose up -d --build --wait
E2E_BASE_URL=http://localhost:5174 npm --prefix web run test:e2e:live -- e2e/live-workspace.spec.ts e2e/live-admin.spec.ts --project=desktop-chrome --project=mobile-chrome
COMPOSE_PROJECT_NAME=promptvault-ananya-check POSTGRES_PORT=5543 API_PORT=8001 WEB_PORT=5174 VITE_API_URL=http://localhost:8001 CORS_ORIGINS=http://localhost:5174 docker compose down -v
```

The separate Compose project gives these tests their own PostgreSQL volume. `E2E_BASE_URL` selects its packaged web address; the usual stack remains available on ports 5173 and 8000.

## A2 data freshness coverage

- `tests/concurrency/test_read_freshness.py` tests single-statement count/page
  snapshots for projects, members, prompts, versions, runs, admin runs, pending
  approvals and active deployments during committed changes. Empty/out-of-range
  pages retain their totals. Additional tests prove dashboard metrics/trend/activity
  share a read snapshot and membership removal waits for admitted detail/lineage reads.
- `web/src/lib/api/pagination.test.ts` tests bounded retries for changing offset
  pages, duplicates, missing rows and same-count updates. Workspace refresh tests
  verify failed reconciliation retains the previous snapshot.
- `web/e2e/live-data-freshness.spec.ts` reconciles all six A2 workflows to real SQL,
  creates more than 100 records, and checks cross-user refresh, unsaved drafts,
  stale responses and restricted access. See [A2 acceptance](a2-live-acceptance.md)
  for isolated stack commands, actual counts and the hosted sign-off boundary.

## Deployment and Serve coverage

- `api/tests/integration/test_deployments_tokens_serve.py` exercises staging activation, pending production requests, scoped history/detail, requester-only cancellation, Super Admin approval/rejection, review evidence, rollback, one-time token disclosure, hash-only persistence, project isolation, expiration/revocation, and conditional Serve responses.
- `api/tests/unit/test_runtime_tokens.py` proves runtime-token prefix, entropy-bearing length, uniqueness, and deterministic one-way hashing.
- `tests/concurrency/test_approval_race.py` submits two simultaneous production decisions and proves exactly one transition succeeds while the loser receives the database serialization conflict.
- `api/tests/unit/test_openapi_export.py` requires every Phase 4 path in the deterministic Swagger/OpenAPI artifact.

## Administration and governance coverage

- `api/tests/integration/test_admin_governance.py` exercises every governance route against PostgreSQL, including role/status changes and the last-active-admin safeguard, organization aggregate reconciliation, all organization-run/audit filters, timezone validation, budget validation/rollback, exact encrypted provider-key persistence, effective-dated pricing conflicts, audit attribution/redaction, missing resources, maintenance/job status, view refresh, partition idempotence, and read/write non-admin denial.
- `api/tests/unit/test_provider_key_encryption.py` proves provider secrets use randomized authenticated ciphertext and round-trip only with the configured server key.
- `tests/concurrency/test_admin_role_race.py` submits reciprocal concurrent deactivations and proves database serialization leaves exactly one active administrator.
- `tests/database/test_roles.py` verifies secret-column denial, revoked direct user updates, and the narrow application-role function privileges required for atomic, audited governance operations.

## Local free-provider and profile acceptance

See [A1 provider/Playground acceptance](a1-local-acceptance.md) for the isolated HTTP
simulator, fixed free-access catalog, API/SQL/browser tests and real-key boundary.
See [A4 profile acceptance](a4-local-acceptance.md) for self-only display-name updates,
restricted database-role checks and desktop/mobile reload persistence. Both are
local workflows; staging and production deployment are outside project scope.
Use separate Playwright `--output` directories when browser runs overlap.

## Local authentication and password-reset acceptance

See [A5 local acceptance](a5-local-acceptance.md) for the loopback SMTP capture
setup and repeatable desktop/mobile registration, login, reset and logout journey.
The harness requires a disposable `_test` database and sends no external email.
Email verification is required for new accounts; the local auth harness also captures verification mail. See [Jobin’s local setup](jobin-local-setup.md).

## Academic database acceptance

See [academic local acceptance](academic-local-acceptance.md) for the catalog
dictionary, rollback-only SQL collector, isolated final user/admin demonstration
and remaining submission boundaries. `tests/delivery/test_academic_evidence.py`
checks database-name refusal and verifies that collecting evidence preserves row
counts even though its demonstration invokes the maintenance procedure.

## Real-provider verification

[Real-provider verification](real-provider-verification.md) distinguishes live
account acceptance from simulated adapter/verifier tests. The local runner defaults
to readiness only and requires confirmed free-tier credentials for execution.
