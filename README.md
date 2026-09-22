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

Database migrations and schema creation are delivered in Batch 2. Until then, API startup expects the configured PostgreSQL server to be reachable because the connection pool opens during application lifespan.

## API verification

```bash
pytest -q api/tests
ruff check api
python3 -m compileall -q api/app api/tests
```

The tests inject a fake pool and do not require a running database for the Batch 1 foundation suite.

## Frontend development

```bash
npm install --prefix web
npm run dev --prefix web
```

The frontend reads its API location from `VITE_API_URL`. Never put signing secrets or provider keys in Vite environment variables.
