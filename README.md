# PromptVault

PromptVault is a prompt versioning, evaluation, deployment, and serving platform in development. The runnable application today is a React/Vite **frontend prototype** with User and Super Admin workflows. It uses in-memory demo data for authentication, projects, prompts, runs, deployments, budgets, and administration. The FastAPI service currently exposes a health endpoint; the database schema and full backend workflows are still planned.

## Repository

- `api/` contains the Python API service.
- `web/` contains the Vite/React client.
- `db/` contains PostgreSQL migrations, seeds, and showcase queries.
- `tests/` contains database, concurrency, security, end-to-end, and performance test areas.
- `scripts/` contains migration, seed, reset, maintenance, and demo commands.

## Implementation status

| Batch | Scope | Status |
|---|---|---|
| 0 | Architecture, API contracts, authorization matrix, and route contract | Complete |
| 1 | FastAPI settings, database pool, request IDs, structured errors/logging, CORS, health/readiness, and test tooling | Complete |
| 2 | PostgreSQL migrations, constraints, indexes, triggers, concurrency functions, views, roles, and development seeds | Complete |
| 3 | Argon2id/JWT authentication, register/login/me endpoints, active-user checks, and reusable admin/project authorization dependencies | Complete |
| 4 | Scoped project/member CRUD, prompt metadata, immutable versions, history, diff, lineage, and concurrency-safe version saves | Complete |
| 5+ | Run, budget, deployment, Serve, and administration APIs | Not yet implemented |

The database schema covers the complete v1 data model, but the application modules for Batch 5 and later are still placeholders. The currently runnable backend surface includes `/health`, `/ready`, authentication, projects/members, prompts, and immutable prompt versions under `/api/v1`.

## API development

PromptVault requires Python 3.11 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.txt
cp .env.example .env
docker compose up -d db
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
uvicorn api.app.main:app --reload --port 8000
```

The required settings are `DATABASE_URL` and `SECRET_KEY`. `.env.example` also documents the token lifetime/issuer/audience, environment name, allowed CORS origins, database-pool bounds, and database-health timeout. Production refuses the placeholder signing secret and requires at least 32 characters.

Operational endpoints:

- `GET /health` is process liveness and never queries PostgreSQL.
- `GET /ready` runs a bounded `SELECT 1` and returns 503 when PostgreSQL is unavailable.
- `/docs`, `/redoc`, and `/openapi.json` are available outside production.

Authentication endpoints are rooted at `/api/v1/auth`: `POST /register`, `POST /login`, and bearer-protected `GET /me`. Access tokens are short-lived HS256 JWTs; the database user is reloaded on every protected request so role changes and deactivation take effect immediately.

API startup expects the configured PostgreSQL server to be reachable because the connection pool opens during application lifespan. Requests are logged as redacted JSON with their method, path, status, duration, and request ID; query strings and request bodies are not logged.

`docker compose up -d db` starts the PostgreSQL dependency. The API image is not packaged yet because `api/Dockerfile` is reserved for the stabilization/delivery batch; run Uvicorn locally as shown above.

## Database commands

The database tools load `.env` and also accept an explicit database URL:

```bash
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
python3 scripts/reset-development.py --confirm-reset
```

Migration history is stored in `schema_migrations`. Applied files are protected by SHA-256 checksums, migration execution is serialized with a PostgreSQL advisory lock, and each migration is atomic. The reset command refuses non-development environments and requires `--confirm-reset`.

The ten migrations create the complete v1 relational schema, constraints, partitions, concurrency functions, audit triggers, reporting views, and database roles. Seed files use numeric prefixes so identities are always loaded before dependent demo data.

Development seed accounts:

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These credentials are development-only. Their Argon2id hashes—not plaintext passwords—are stored in the seed SQL.

## API contract

`docs/api-contracts.md` is the human-readable contract. `docs/openapi.json` is its generated machine-readable companion and can be refreshed with:

```bash
python3 scripts/export-openapi.py
```

The generated file lets the frontend create TypeScript clients/models without waiting for a live API. CI verifies that it matches the FastAPI application.

## API verification

The full suite needs a separate PostgreSQL database. Create `promptvault_test` once in your local PostgreSQL instance, set `TEST_DATABASE_URL`, and then run:

```bash
export TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
ruff check api scripts tests
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml --cov-report=term-missing
python3 -m compileall -q api/app scripts tests
python3 -m pip check

DATABASE_URL="$TEST_DATABASE_URL" \
SECRET_KEY=test-secret-that-is-at-least-32-characters \
python3 scripts/export-openapi.py --output /tmp/promptvault-openapi.json
diff -u docs/openapi.json /tmp/promptvault-openapi.json
```

The unit suite injects a fake pool and does not require PostgreSQL. Database and authentication integration tests use `TEST_DATABASE_URL` and skip when it is not configured; CI runs them against PostgreSQL 16. Test fixtures apply migrations and idempotent seeds automatically. Coverage is branch-aware and must remain at or above 85%.

## Frontend development

```bash
npm ci --prefix web
npm run dev --prefix web
```

The frontend reads its API location from `VITE_API_URL`. Never put signing secrets or provider keys in Vite environment variables.

Frontend checks available on this branch are:

```bash
npm run typecheck --prefix web
npm run build --prefix web
```
## Project structure

```text
PromptVault/
├── api/                 FastAPI entry point and backend package skeleton
│   ├── app/             Routers, services, repositories, schemas, and providers
│   └── tests/           Backend test locations (currently placeholders)
├── db/                  PostgreSQL migration, seed, maintenance, and query locations
├── docs/                Architecture, contracts, demo guide, and verification notes
│   └── screenshots/     Captured desktop and mobile prototype screens
├── evidence/            Locations for database and performance evidence
├── examples/            Example prompt templates and deployment requests
├── scripts/             Planned database and traffic helper scripts
├── tests/               Planned API, database, security, and end-to-end tests
├── web/                 React, TypeScript, and Vite frontend
│   ├── e2e/             Playwright browser tests and screenshot capture
│   ├── public/          Static assets
│   └── src/
│       ├── app/         Route setup and application providers
│       ├── components/  Shared UI and layouts
│       ├── features/    Auth, projects, prompts, runs, deployments, and admin views
│       ├── lib/api/     Typed HTTP client
│       ├── mocks/       Demo accounts and in-memory data
│       ├── styles/      Global styles and tokens
│       └── types/       API and domain types
├── .env.example         Planned root-level API/database settings
└── docker-compose.yml   Draft PostgreSQL and API configuration
```

Several backend, database, script, and test files are empty placeholders. `docker-compose.yml` cannot build the API service yet because `api/Dockerfile` is empty; it is not the recommended way to run the demo.

## Prerequisites

- Node.js and npm compatible with the dependencies in `web/package-lock.json` (use a current Node.js LTS release).
- Google Chrome if you want to run Playwright browser tests or regenerate screenshots.
- Python 3.11 or later only if you want to run the API health endpoint locally.
- Docker only if you want to start the PostgreSQL container; the frontend demo does not need it.

## Run the frontend demo

From the repository root:

```sh
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The `VITE_USE_MOCK_*` settings in `web/.env.example` are enabled for the standalone demo. Leave them enabled: switching to real API mode requires backend endpoints that are not implemented yet. `VITE_API_BASE_URL` points to `http://localhost:8000` for future API integration. The root `.env.example` is separate and is not needed for the frontend demo.

| Demo role | Email | Password |
| --- | --- | --- |
| User | `user@promptvault.dev` | `User@123` |
| Super Admin | `admin@promptvault.dev` | `Admin@123` |

These are public demo credentials. Demo records reset on reload; the signed-in account is restored within the same browser tab. Do not enter real secrets or use this prototype as a production authentication system. See the [demo runbook](docs/demo-runbook.md) for a walkthrough and feature limitations.

## Build and check the frontend

Run these from `web/` after `npm ci`:

```sh
npm run typecheck      # TypeScript checks
npm run lint           # ESLint
npm test               # Vitest unit tests
npm run coverage       # Unit-test coverage report
npm run build          # Production bundle in web/dist/
npx vite preview       # Serve that bundle locally for inspection
```

For browser tests, install Google Chrome, then run:

```sh
npm run test:e2e       # Playwright smoke and accessibility checks
npm run screenshots    # Refresh docs/screenshots/
```

Playwright starts its own Vite server on port `4173`. It covers desktop Chrome and emulated mobile/tablet viewports, not physical devices or Safari. Browser test results are in `web/test-results/`. See the [browser smoke record](docs/browser-smoke.md) and [frontend README](web/README.md) for details.

## Run the API health endpoint (optional)

The API currently serves `GET /health`; it does not yet provide the application endpoints used by the typed frontend client. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements.txt
cd api
python3 -m uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` to check it. The frontend demo runs independently of this service. The root `.env.example` lists intended database and API settings, but the current health-only API does not use them.

If you need an empty local PostgreSQL instance for future backend work, run `docker compose up db` from the repository root. The SQL migration and seed files are placeholders, so this does not initialize a PromptVault schema.

## Further documentation

- [Demo walkthrough](docs/demo-runbook.md)
- [Frontend setup and boundaries](web/README.md)
- [API contract](docs/api-contracts.md) and [route map](docs/route-map.md) (design targets, not implemented backend endpoints)
- [Browser verification](docs/browser-smoke.md) and [screenshots](docs/screenshots/README.md)
- [Working prototype plan](docs/working-prototype-plan.md)
