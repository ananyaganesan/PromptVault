# PromptVault

PromptVault is a prompt versioning, evaluation, deployment, and serving platform in development. The runnable application today is a React/Vite **frontend prototype** with User and Super Admin workflows. It uses in-memory demo data for authentication, projects, prompts, runs, deployments, budgets, and administration. The FastAPI service currently exposes a health endpoint; the database schema and full backend workflows are still planned.

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
