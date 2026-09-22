# PromptVault

Prompt versioning, evaluation, deployment, and serving platform.

## Repository

- `api/` contains the Python API service.
- `web/` contains the Vite/React client.
- `db/` contains PostgreSQL migrations, seeds, and showcase queries.

## API development

PromptVault requires Python 3.11 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.txt
cp .env.example .env
uvicorn api.app.main:app --reload --port 8000
```

The required settings are `DATABASE_URL` and `SECRET_KEY`. `.env.example` also documents the environment name, allowed CORS origins, database-pool bounds, and database-health timeout. Production refuses the placeholder signing secret and requires at least 32 characters.

Operational endpoints:

- `GET /health` is process liveness and never queries PostgreSQL.
- `GET /ready` runs a bounded `SELECT 1` and returns 503 when PostgreSQL is unavailable.
- `/docs`, `/redoc`, and `/openapi.json` are available outside production.

API startup expects the configured PostgreSQL server to be reachable because the connection pool opens during application lifespan. Requests are logged as redacted JSON with their method, path, status, duration, and request ID; query strings and request bodies are not logged.

## Database commands

The database tools load `.env` and also accept an explicit database URL:

```bash
python3 scripts/run-migrations.py
python3 scripts/seed-database.py
python3 scripts/reset-development.py --confirm-reset
```

Migration history is stored in `schema_migrations`. Applied files are protected by SHA-256 checksums, migration execution is serialized with a PostgreSQL advisory lock, and each migration is atomic. The reset command refuses non-development environments and requires `--confirm-reset`.

The SQL migration and seed files are Batch 2 placeholders at present. Empty files are deliberately rejected, so these commands become runnable when the schema SQL is filled in rather than silently marking an empty schema as complete.

## API contract

`docs/api-contracts.md` is the human-readable contract. `docs/openapi.json` is its generated machine-readable companion and can be refreshed with:

```bash
python3 scripts/export-openapi.py
```

The generated file lets the frontend create TypeScript clients/models without waiting for a live API. CI verifies that it matches the FastAPI application.

## API verification

```bash
ruff check api scripts
mypy --config-file api/pyproject.toml api/app
pytest -q --cov=api.app --cov-config=api/pyproject.toml
python3 -m compileall -q api/app api/tests scripts
```

The unit suite injects a fake pool and does not require PostgreSQL. Database tests use `TEST_DATABASE_URL` and skip when it is not configured. Coverage is branch-aware and must remain at or above 85%.

## Frontend development

```bash
npm install --prefix web
npm run dev --prefix web
```

The frontend reads its API location from `VITE_API_URL`. Never put signing secrets or provider keys in Vite environment variables.
