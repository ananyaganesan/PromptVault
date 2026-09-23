# PromptVault

PromptVault is a prompt versioning, evaluation, deployment, and serving platform in development. The React frontend is a runnable, in-memory prototype for User and Super Admin workflows. The FastAPI backend now has a PostgreSQL schema, development seeds, health checks, and authentication endpoints; the remaining application APIs are still being built.

## Implementation status

| Area | Available now | Still to build |
| --- | --- | --- |
| Frontend | Responsive user and admin demo, typed API client, unit and browser tests | Integration with the application APIs and production authentication |
| API | Configuration, database pool, health/readiness, request logging and errors, JWT registration/login/current-user endpoints, authorization dependencies | Project, prompt, version, run, deployment, budget, Serve, and governance endpoints |
| Database | Ten migrations, constraints, triggers, functions, views, roles, and development/demo seeds | Integration of the remaining API workflows |

The frontend demo and backend development seed use the same email addresses but **different passwords**. The frontend login currently uses local demo accounts; it does not call the backend authentication endpoints. Its mock data resets on reload, while the backend uses PostgreSQL.

## Project structure

```text
PromptVault/
├── api/                  FastAPI application, domain package, and API tests
│   └── app/              Configuration, routers, services, repositories, and schemas
├── db/                   PostgreSQL migrations, seeds, maintenance SQL, and showcase queries
├── docs/                 Contracts, architecture, security, demo guide, and screenshots
├── evidence/             Locations for database and performance evidence
├── examples/             Example prompt templates and deployment requests
├── scripts/              Migration, seed, reset, and OpenAPI export commands
├── tests/                Database and other cross-service test areas
├── web/                  React, TypeScript, and Vite frontend
│   ├── e2e/              Playwright browser tests and screenshot capture
│   └── src/
│       ├── app/          Routes and application setup
│       ├── components/   Shared UI and layouts
│       ├── features/     User and admin pages and demo services
│       ├── lib/api/      Typed HTTP client
│       ├── mocks/        Frontend demo users and data
│       ├── styles/       Global styles and tokens
│       └── types/        API and domain types
├── .env.example          Backend and database settings
└── docker-compose.yml    PostgreSQL service and draft API service
```

## Frontend demo

**Prerequisites:** Node.js and npm compatible with `web/package-lock.json` (a current Node.js LTS release). The standalone demo does not need Python or PostgreSQL.

From the repository root:

```sh
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

| Frontend demo role | Email | Password |
| --- | --- | --- |
| User | `user@promptvault.dev` | `User@123` |
| Super Admin | `admin@promptvault.dev` | `Admin@123` |

The frontend covers projects and members, prompts and immutable version snapshots, version comparison and lineage, playground scenarios, run history and costs, deployments and approvals, API tokens, and administration. The mock services keep records in browser memory. Reloading restores seeded records; the signed-in account survives a reload in the same tab. These public credentials and simulated token/provider flows are for demonstration only. See the [demo runbook](docs/demo-runbook.md).

`web/.env.example` defines `VITE_API_BASE_URL` and enables `VITE_USE_MOCK_RUNS`, `VITE_USE_MOCK_DEPLOYMENTS`, and `VITE_USE_MOCK_ADMIN`. Keep the mock flags enabled for this demo. Projects, prompts, and frontend authentication are also local demo implementations. The typed API client exists, but the corresponding application endpoints are not yet available. The root `.env.example` is for backend configuration; its `VITE_API_URL` entry is not the variable currently read by the frontend client.

### Build and test the frontend

Run from `web/` after `npm ci`:

```sh
npm run typecheck
npm run lint
npm test
npm run coverage
npm run build
npx vite preview
```

`npm run build` writes the production bundle to `web/dist/`; `npx vite preview` serves that bundle locally. For browser checks and screenshots, install Google Chrome and run:

```sh
npm run test:e2e
npm run screenshots
```

Playwright starts its own Vite server on port `4173`. It covers desktop Chrome and emulated mobile/tablet viewports; it does not certify physical devices or Safari. Test artifacts appear in `web/test-results/`. See the [browser smoke record](docs/browser-smoke.md) and [frontend README](web/README.md).

## Backend and database development

**Prerequisites:** Python 3.11 or newer and Docker with Compose for PostgreSQL. The API opens its database pool on startup, so PostgreSQL must be reachable before starting Uvicorn.

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.txt
cp .env.example .env
docker compose up -d db
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
python3 -m uvicorn api.app.main:app --reload --port 8000
```

`.env` supplies `DATABASE_URL` and `SECRET_KEY` plus settings for token lifetime, CORS, and the database pool. The placeholder signing key is suitable only for local development; production configuration requires a key of at least 32 characters. `docker compose up -d db` starts only PostgreSQL. The API container cannot be built yet because `api/Dockerfile` is still a placeholder.

Available API routes:

- `GET /health`: process liveness, without a database query.
- `GET /ready`: database readiness; returns 503 when PostgreSQL is unavailable.
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and bearer-protected `GET /api/v1/auth/me`.
- `/docs`, `/redoc`, and `/openapi.json` outside production.

Backend development seed accounts:

| Backend role | Email | Password |
| --- | --- | --- |
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

The seed SQL stores Argon2id hashes. These backend accounts do not sign in to the current frontend demo.

### Database and API checks

Migration files are applied in numeric order and recorded with checksums in `schema_migrations`. The database commands load the root `.env`; see [db/README.md](db/README.md) for migration rules and reset safeguards.

```sh
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
```

The development reset command, `python3 scripts/reset-development.py --confirm-reset`, recreates the schema and data. It is restricted to the development environment.

To run the full backend suite, create a separate `promptvault_test` database once:

```sh
docker compose exec db psql -U promptvault -d postgres -c 'CREATE DATABASE promptvault_test;'
```

Then set `TEST_DATABASE_URL` and run from the repository root with the virtual environment active:

```sh
export TEST_DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault_test
ruff check api scripts tests
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml --cov-report=term-missing
python3 -m compileall -q api/app scripts tests
python3 -m pip check
```

Database and authentication integration tests skip when `TEST_DATABASE_URL` is absent. CI runs them against PostgreSQL 16. The backend coverage gate is 85% with branch coverage. The frontend has its own separate coverage command.

The current machine-readable API contract is [docs/openapi.json](docs/openapi.json); the design contract is [docs/api-contracts.md](docs/api-contracts.md). Regenerate and compare OpenAPI output with:

```sh
DATABASE_URL="$TEST_DATABASE_URL" SECRET_KEY=test-secret-that-is-at-least-32-characters python3 scripts/export-openapi.py --output /tmp/promptvault-openapi.json
diff -u docs/openapi.json /tmp/promptvault-openapi.json
```

## Further documentation

- [Frontend demo walkthrough](docs/demo-runbook.md)
- [Frontend setup and limitations](web/README.md)
- [Database migration and seed rules](db/README.md)
- [API contract](docs/api-contracts.md) and [route map](docs/route-map.md)
- [Browser verification](docs/browser-smoke.md) and [screenshots](docs/screenshots/README.md)
- [Working prototype plan](docs/working-prototype-plan.md)
