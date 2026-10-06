# PromptVault

PromptVault is a full-stack prompt versioning, execution, deployment, and governance prototype. The React/Vite client is connected to a FastAPI service and PostgreSQL database; demo-critical workflows persist through the API rather than browser-local stores.

## What is implemented

- Email/password registration and login, Argon2id password hashes, JWT sessions, active-user checks, User/Super Admin route guards, and `/auth/me` session restoration.
- Project ownership/membership, prompt metadata, immutable version snapshots, concurrent version numbering, history, diff, and lineage.
- Deterministic provider execution with variable rendering, token/latency/cost ledger records, effective-dated pricing, personal analytics, and atomic user/project budgets.
- Development/staging activation, pending production approval, atomic admin review, cancellation, project-scoped runtime tokens, authenticated Serve API, and auditable rollback.
- Admin users, organization analytics/runs, encrypted provider keys, budgets, pricing history, audit search, partition status, and materialized-view refresh.
- Docker startup/migrations/seeds, Swagger/OpenAPI, database/security/concurrency/performance suites, and live Playwright workflows.

The implementation sequence and acceptance criteria are tracked in [docs/working-prototype-plan.md](docs/working-prototype-plan.md).

## Current status and remaining boundaries

The working-prototype scope is implemented across the React client, FastAPI service, and PostgreSQL schema. A clean detached checkout builds the production-target containers, applies migrations and deterministic seeds, passes lint and strict type checking, runs the complete backend/database/security/concurrency/performance suite, verifies OpenAPI drift, starts a healthy stack, exercises seeded login and race demonstrations, loads 2,000 representative runs, and executes the showcase queries. The latest redacted transcript is in [`evidence/release/latest.txt`](evidence/release/latest.txt); connected cross-browser acceptance is recorded in [`docs/browser-smoke.md`](docs/browser-smoke.md).

The remaining boundaries are deployment-specific rather than unfinished prototype workflows: Gmail password-reset delivery requires a real sender address and Google App Password; the bundled deterministic model provider is not an external LLM integration; production needs managed TLS, secret rotation, backups, monitoring, and a distributed edge rate limiter. Safari/WebKit, physical-device, screen-reader, and manual accessibility certification are also outside the automated acceptance boundary.

## Quick start

Docker Engine with the Compose plugin is the only prerequisite for the packaged stack:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Open:

- Web application: `http://localhost:5173`
- Swagger UI: `http://localhost:8000/docs`
- API readiness: `http://localhost:8000/ready`

Startup waits for PostgreSQL, applies all checksum-tracked migrations, runs idempotent development seeds only when `ENVIRONMENT=development`, and then starts the API and Nginx-served web build. The seed command also refuses production mode when invoked directly.

Development accounts:

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These credentials are local-development fixtures only. Their Argon2id hashes, not plaintext passwords, are stored in seed SQL.

Stop the stack without deleting data:

```bash
docker compose down
```

Reset a running development stack to deterministic seed data and refresh the API connection pool:

```bash
docker compose run --rm migrate python scripts/reset-development.py --confirm-reset \
  && docker compose restart api \
  && docker compose up -d --wait
```

`docker compose down -v` also removes the database volume and is intentionally destructive.

## Frontend development

```bash
npm ci --prefix web
cp web/.env.example web/.env.local
npm run dev --prefix web
```

The client reads `VITE_API_BASE_URL` (or `VITE_API_URL`) and appends `/api/v1`. The default is `http://localhost:8000`. Browser sessions are tab-scoped through `sessionStorage`; authorization is always rechecked by FastAPI.
Workspace data also uses the API by default. `VITE_USE_DEMO_DATA=true` is an explicit local example-data mode; the Docker web build keeps it disabled.

## Password reset email

The **Forgot password?** form calls `POST /api/v1/auth/password-reset`. For an active account, the API stores a hashed, one-use token and sends a link to the public `/reset-password` page. The link expires after `PASSWORD_RESET_TTL_MINUTES` (default 30).

To send through Gmail or Google Workspace, enable 2-Step Verification and create a Google App Password for this application. Set `PASSWORD_RESET_URL` to the frontend's public absolute URL and configure these backend variables in the ignored `.env` file or a deployment secret store:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-address@gmail.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

Use the same Gmail address for `SMTP_USERNAME` and `SMTP_FROM_EMAIL`. For port 465, use `SMTP_SSL=true` and `SMTP_STARTTLS=false`. Restart the API after changing the settings. Without a configured SMTP server, reset requests return `503 email_delivery_unavailable`; login remains available. Gmail delivery has not been verified until an address and App Password are supplied.

Frontend verification:

```bash
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run coverage --prefix web
npm run build --prefix web
```

Live browser workflows require the Docker stack:

```bash
npm exec --prefix web playwright install firefox
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=mobile-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-firefox
```

The live suites cover authentication/session recovery, forbidden routes, project/member/prompt/version persistence, real diff/lineage, runs/costs, database budget rejection, deployments/approval, one-time runtime tokens, Serve, rollback, governance, responsive layouts, and axe-core serious/critical accessibility checks. Mocks remain only in isolated Vitest service/component tests.

## API development

PromptVault requires Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.lock
cp .env.example .env
docker compose up -d db
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
uvicorn api.app.main:app --reload --port 8000
```

Important endpoints:

- `GET /health` — process liveness.
- `GET /ready` — bounded PostgreSQL readiness check.
- `/api/v1/auth/*` — registration, login, current user.
- `/api/v1/projects`, `/prompts`, `/versions` — versioned prompt library.
- `/api/v1/runs`, `/dashboard/me` — execution ledger and personal analytics.
- `/api/v1/deployments`, `/api-tokens` — control plane and runtime credentials.
- `GET /serve/v1/prompts/{key}?env=prod` — project-scoped active prompt retrieval.
- `/api/v1/admin/*` — approvals and governance.

The human-readable contract is [docs/api-contracts.md](docs/api-contracts.md); [docs/openapi.json](docs/openapi.json) is generated and checked for drift.

## Database and demo commands

```bash
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
python3 scripts/reset-development.py --confirm-reset
python3 scripts/create-partition.py
python3 scripts/refresh-views.py
python3 scripts/simulate-traffic.py --runs 2000
python3 scripts/run-showcase.py
python3 scripts/version-race-demo.py --workers 20
python3 scripts/approval-race-demo.py
```

Migration history is stored in `schema_migrations`; checksums prevent already-applied files from changing. Migrations are ordered, advisory-lock serialized, and transactional. The only history reconciliation recognizes a version-011 password-reset record with exactly the current SQL checksum and an existing reset table, then records it as version 015 so the missing run-budget migration can apply. All other history mismatches fail closed. Development seed commands refuse production mode; reset refuses non-development environments and requires explicit confirmation.

## Backend verification

Use an isolated database whose name ends in `_test`:

```bash
export TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
ruff check api scripts tests
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml --cov-report=term-missing
python3 -m compileall -q api/app scripts tests
python3 -m pip check
python3 scripts/export-openapi.py --output /tmp/promptvault-openapi.json
diff -u docs/openapi.json /tmp/promptvault-openapi.json
```

Containerized verification is also available:

```bash
docker compose --profile verification run --rm verify
```

`python3 scripts/verify-release.py` performs the backend clean-checkout release workflow in an isolated Compose project and writes a redacted transcript below `evidence/release/`.

## Security and prototype boundaries

- FastAPI enforces all authorization; hidden UI controls are not security boundaries.
- Provider secrets are encrypted at rest and never returned by list endpoints.
- Runtime tokens are displayed once, stored only as hashes, project-scoped, and revocable.
- Structured logs exclude query strings, request bodies, passwords, tokens, and provider keys.
- Login/registration and password recovery have configurable per-client throttles; production still requires a distributed edge limiter.
- Production rejects placeholder secrets and unrestricted database-role configuration; pooled API connections run as `promptvault_app`.
- Password reset uses one-use database tokens and a configurable SMTP provider; provider setup and live delivery are deployment responsibilities.
- The included provider is deterministic for reproducible evaluation; external production LLM reliability is outside prototype scope.
- JWT storage is tab-scoped for the prototype. A production deployment should evaluate an HTTPS-only cookie/BFF session model and rotate all example secrets.

## Repository layout

```text
api/        FastAPI routers, schemas, services, repositories, providers, tests
db/         PostgreSQL migrations, seeds, maintenance, and showcase queries
web/        React/Vite client, unit tests, and Playwright live workflows
scripts/    Migration, reset, traffic, partition, showcase, and race tools
tests/      Database, security, concurrency, E2E, delivery, and performance tests
docs/       Architecture, contract, security, testing, deployment, and demo docs
evidence/   Release transcripts, query plans, concurrency output, screenshots
examples/   Prompt versioning and deployment examples
```

See [docs/demo-runbook.md](docs/demo-runbook.md) for the presentation flow and [docs/testing.md](docs/testing.md) for the complete test strategy.
