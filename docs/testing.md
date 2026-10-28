# Testing strategy

PromptVault is a local application backed by the persistent `promptvault` database
on `localhost:5432`. Automated database tests must use a separate database whose
name ends in `_test`; never point `TEST_DATABASE_URL` at `promptvault`.

The application supports Gemini only. Tests may intercept Gemini HTTP or inject a
test double under test code, but no simulated provider is selectable through the
runtime API or UI.

## Install development dependencies

Use Python 3.11 or later and Node.js 22:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements-dev.lock
npm ci --prefix web
```

Keep local secrets in `.env`. The test suite uses explicit test settings and must
not reuse real Gemini credentials, SMTP credentials, JWTs, or runtime tokens.

## Backend verification

Create an isolated PostgreSQL database once, then run the same checks as CI:

```bash
createdb -h localhost -p 5432 -U promptvault promptvault_test

export ENVIRONMENT=test
export DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
export TEST_DATABASE_URL="$DATABASE_URL"
export SECRET_KEY=ci-secret-that-is-long-enough

.venv/bin/ruff check api scripts tests
.venv/bin/mypy --config-file api/pyproject.toml api/app
.venv/bin/pytest -q --cov=api.app --cov-config=api/pyproject.toml
.venv/bin/python -m compileall -q api/app api/tests scripts tests
.venv/bin/python -m pip check
.venv/bin/python scripts/export-openapi.py --output /tmp/promptvault-openapi.json
```

The migration runner validates names and checksums before applying pending files.
If a disposable test database belongs to an older incompatible migration history,
recreate only that `_test` database. Never repair, drop, reset, or reseed the
persistent `promptvault` database to make tests pass.

Coverage must remain at or above the threshold configured in `api/pyproject.toml`.
The OpenAPI export command proves that the current application schema can be
generated; the repository no longer stores a generated `docs/openapi.json` copy.

## Frontend verification

Run from the repository root:

```bash
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run build --prefix web
```

Run `npm ci --prefix web` after pulling a changed `web/package-lock.json`. A passing
unit suite does not replace the production build because CSS imports, fonts, and
bundler-only failures may appear only during `vite build`.

## Test layers

### API and unit tests

- `api/tests/unit/` covers configuration, security, request limits, migration
  planning, model validation, Gemini request/response handling, encryption,
  evaluation scoring, embeddings, runtime tokens, and OpenAPI generation.
- `api/tests/integration/` exercises authenticated FastAPI routes against real
  PostgreSQL transactions: accounts, projects, invitations, prompts, immutable
  versions, Gemini runs, evaluations, release validation, deployments, Serve
  tokens, roles, approvals, administration, and health checks.
- `api/tests/integration/test_evaluations.py` verifies bounded comparison setup,
  persisted results, recommendations, history, usage, and improvement drafts.
- `api/tests/integration/test_release_validation.py` verifies that releases use a
  passing report for the exact version and environment, and that stale or failing
  evidence cannot activate a deployment.

### Database, concurrency, security, and performance

- `tests/database/` covers the full migration chain, upgrade preservation,
  constraints, immutability, partitions, audit triggers, restricted roles, budget
  reservations, maintenance, normalization, and Gemini-only historical upgrades.
- `tests/concurrency/` covers racing version saves, budget reservations,
  membership removal, deployment reviews, rollbacks, dashboard reads, and the
  last-active-administrator boundary.
- `tests/security/` covers cross-account authorization, inactive users, role
  escalation, secret redaction, token scope, profile updates, and rejection of
  removed providers in every environment.
- `tests/performance/test_query_plans.py` verifies representative index-backed
  history queries and partition pruning.
- `tests/e2e/` drives complete API workflows such as prompt execution, budget
  blocking, production approval, Serve retrieval, rollback, and application-pool
  restart persistence.

### Frontend unit and browser tests

- `web/src/**/*.test.ts(x)` covers API clients, authentication and email
  verification, projects and invitations, prompts and versions, Playground,
  evaluations, runs, deployments, release validation, tokens, administration,
  accessibility-sensitive UI components, and stale-response protection.
- `web/e2e/*.spec.ts` contains local browser journeys for registration,
  verification, password reset, workspace activity, evaluations, release
  validation, deployments, administration, accessibility, and data freshness.

Start the normal local application with:

```bash
.venv/bin/python scripts/start-local.py
```

Then run a selected browser workflow from `web/`:

```bash
E2E_LIVE=1 \
E2E_BASE_URL=http://localhost:5173 \
E2E_API_BASE_URL=http://localhost:8000/api/v1 \
npx playwright test e2e/evaluations.spec.ts --project=desktop-chrome
```

Browser tests that write directly to PostgreSQL require an explicit isolated
`E2E_DATABASE_URL` ending in `_test`; they must not use the persistent application
database. Run stateful browser suites serially unless the test explicitly creates
separate accounts and projects.

## Authentication and email testing

Email verification is required for new accounts. Verification links are hashed,
single-use, expire after 30 minutes, and are protected by resend cooldown and
rolling-hour limits. Account approval remains a separate administrator decision.

Use the loopback SMTP acceptance harness with a dedicated `_test` database:

```bash
export E2E_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_auth_test
export E2E_MAILBOX_DIR=/tmp/promptvault-auth-mailbox

createdb -h localhost -p 5432 -U promptvault promptvault_auth_test
.venv/bin/python scripts/run-migrations.py --database-url "$E2E_DATABASE_URL"
ENVIRONMENT=test .venv/bin/python scripts/seed-database.py \
  --database-url "$E2E_DATABASE_URL"

# Keep Terminal 1 running: isolated API and SMTP capture
.venv/bin/python scripts/run-local-auth-acceptance.py
```

The harness listens on API port 8005 and SMTP port 1026. Start the matching web
frontend in a second terminal:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8005 \
VITE_API_URL=http://127.0.0.1:8005 \
VITE_USE_DEMO_DATA=false \
npm --prefix web run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178` to run the flow manually: register, open the captured
verification link, then sign in as the disposable seeded super administrator
(`admin@promptvault.dev` / `AdminDemo2026!`) and approve the verified account.
Those credentials belong only to a deliberately seeded `_test` database and must
never be enabled in the persistent application database. Continue with login,
reset, session revocation, and logout. The existing
`web/e2e/live-auth-reset.spec.ts` must not be used as acceptance evidence until it
includes the required administrator-approval step.

The captured mailbox is local test data. Do not commit messages, verification
links, reset links, JWTs, or credentials. Integration tests must also preserve
logout, password-reset session revocation, password-history rejection, duplicate
registration errors, and generic resend responses that do not reveal account state.

## Gemini verification

Automated Gemini tests use controlled HTTP responses and never prove that a real
free-tier account works. Check catalog and credential readiness without sending an
external inference request:

```bash
read -r -p 'Verified super-administrator email: ' PV_VERIFY_EMAIL
read -r -s -p 'PromptVault password: ' PV_VERIFY_PASSWORD; echo
export PV_VERIFY_EMAIL PV_VERIFY_PASSWORD

.venv/bin/python scripts/verify-real-providers.py \
  --local-development-database \
  --provider gemini \
  --output /tmp/promptvault-real-provider-check.json
```

After confirming that the configured account and selected model are genuinely
free-tier, execute the real verification call explicitly. The supplied account
must be active, verified, approved, and have the `super_admin` role because the
verifier creates an isolated verification project:

```bash
.venv/bin/python scripts/verify-real-providers.py \
  --local-development-database \
  --provider gemini \
  --execute \
  --free-tier-accounts-confirmed \
  --output /tmp/promptvault-real-provider-check.json
```

Run either command in the same shell where the verification credentials were
exported. Remove them when finished:

```bash
unset PV_VERIFY_EMAIL PV_VERIFY_PASSWORD
```

Do not claim real Gemini execution from simulated tests. Do not add alternate
providers, paid fallback, or a runtime-selectable mock adapter.

## Delivery checks

- `tests/delivery/test_local_startup.py` protects fixed local ports, the persistent
  database name, checksum-preserving migration startup, and safe error output.
- `tests/delivery/test_macos_launcher.py` checks the optional macOS launcher.
- `tests/delivery/test_serve_client.py` checks the runtime prompt client without
  exposing bearer tokens.
- `tests/delivery/test_smtp_setup.py` checks safe SMTP configuration handling.
- `tests/delivery/test_real_provider_verification.py` checks the verifier with
  simulated Gemini HTTP; it is not evidence of a real account call.

## Before committing

At minimum, run the focused tests for the files changed. Before integrating a
feature branch, run backend lint and type checks, the full backend suite against a
fresh `_test` database, all frontend unit checks, and the Vite production build.
Report failures as failures; do not treat coverage from a partially failing suite
as a passing result.
