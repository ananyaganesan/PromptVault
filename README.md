# PromptVault

PromptVault is a prompt versioning, evaluation, deployment, and serving platform in development. The React frontend supports database-backed authentication and uses in-memory prototype data for the remaining workflows. The FastAPI backend has a PostgreSQL schema, development seeds, health checks, authentication, projects, prompts, and immutable prompt versions; later application APIs are still being built.

## Implementation status

| Area | Available now | Still to build |
| --- | --- | --- |
| Frontend | Responsive user and admin demo, database-backed login and registration through FastAPI, typed API client, unit and browser tests | Integration of projects, prompts, runs, deployments, and governance with their future APIs |
| API | Configuration, database pool, health/readiness, request logging and errors, JWT authentication, scoped projects and members, prompts, and immutable versions | Run, deployment, budget, Serve, and governance endpoints |
| Database | Ten migrations, constraints, triggers, functions, views, roles, and development/demo seeds | Integration of the remaining API workflows |

Login and registration use the FastAPI authentication endpoints by default. The other frontend workflows still use in-memory prototype data. A separate opt-in demo auth mode retains the old browser-only accounts for walkthroughs and UI tests.

Backend batches 0–4 are complete. Batch 4 adds project/member CRUD, prompt metadata, immutable versions, history, diff, lineage, and concurrency-safe version saves. Run, budget, deployment, Serve, and administration APIs remain unimplemented.

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

## Frontend with database-backed login

**Prerequisites:** Node.js and npm compatible with `web/package-lock.json` (a current Node.js LTS release), a migrated and seeded PostgreSQL database, and the FastAPI server running on port `8000`. Follow the backend setup below first.

From the repository root:

```sh
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`. `VITE_USE_MOCK_AUTH=false` makes login and registration call FastAPI. The browser never connects to PostgreSQL directly. New registrations save `email`, `display_name`, an Argon2 password hash, the default `user` role, active status, and timestamps in the `users` table.

| Seeded database role | Email | Password | Login |
| --- | --- | --- | --- |
| User | `user@promptvault.dev` | `UserDemo2026!` | Allowed |
| User | `alice@promptvault.dev` | `AliceDemo2026!` | Allowed |
| User | `bob@promptvault.dev` | `BobDemo2026!` | Allowed |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` | Allowed |
| Inactive user | `inactive@promptvault.dev` | `InactiveDemo2026!` | Denied (403) |

The API returns a JWT on login or registration. The frontend keeps it in tab session storage and verifies it with `/api/v1/auth/me` after a refresh, so a valid session stays signed in within that tab. Signing out clears the saved token; an expired or invalid token requires signing in again. Login succeeds only for active users with matching database credentials. An unknown email shows “Email address not found.”; a password mismatch shows “Incorrect password.” Passwords are never stored in browser storage. New passwords must have at least 12 non-whitespace characters; spaces are ignored in the form and rejected by the registration API.

Projects, prompts, runs, deployments, budgets, and admin workflows still use local prototype stores until their backend APIs are implemented. Their changes do not persist to PostgreSQL. `web/.env.example` sets `VITE_API_BASE_URL=http://localhost:8000`; the root `.env.example` is for backend settings. The root `VITE_API_URL` value is not used by the current frontend client.

For the standalone UI walkthrough without the API, set `VITE_USE_MOCK_AUTH=true` in `web/.env.local` and restart Vite. That mode uses the same listed development credentials as the database seed, restores the demo account within the same tab, and does not create database users. See the [demo runbook](docs/demo-runbook.md).

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

**Prerequisites:** Python 3.11 or newer and PostgreSQL. You can use a local PostgreSQL installation or Docker Compose. The API opens its database pool on startup, so PostgreSQL must be reachable before starting Uvicorn.

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.txt
cp .env.example .env
# Start PostgreSQL first; use `docker compose up -d db` if using Docker.
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
python3 -m uvicorn api.app.main:app --reload --port 8000
```

`.env` supplies `DATABASE_URL` and `SECRET_KEY` plus settings for token lifetime, CORS, and the database pool. The placeholder signing key is suitable only for local development; production configuration requires a key of at least 32 characters. `docker compose up -d db` starts only PostgreSQL. The API container cannot be built yet because `api/Dockerfile` is still a placeholder.

Available API routes:

- `GET /health`: process liveness, without a database query.
- `GET /ready`: database readiness; returns 503 when PostgreSQL is unavailable.
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and bearer-protected `GET /api/v1/auth/me`.
- Project/member, prompt, and immutable version endpoints under `/api/v1`.
- `/docs`, `/redoc`, and `/openapi.json` outside production.

Backend development seed accounts are listed in the [login table above](#frontend-with-database-backed-login). Rerun `python3 scripts/seed-database.py` to add or restore them.

The seed SQL stores Argon2id hashes. These accounts sign in when `VITE_USE_MOCK_AUTH=false`; the standalone demo has separate browser-only credentials.

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
- [API contract](docs/api-contracts.md)
- [Browser verification](docs/browser-smoke.md) and [screenshots](docs/screenshots/README.md)
- [Working prototype plan](docs/working-prototype-plan.md)
