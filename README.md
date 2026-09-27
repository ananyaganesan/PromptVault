# PromptVault

Prompt versioning, evaluation, deployment, and serving platform.

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
| 5 | Deterministic providers, run ledger, effective pricing, atomic budgets, scoped run APIs, and personal dashboard | Complete |
| 6 | Deployment requests/history/cancellation, atomic production review, runtime tokens, Serve API, and auditable rollback | Complete |
| 7 | Super Admin users, organization analytics/runs, budgets, encrypted provider keys, pricing history, audit queries, and maintenance operations | Complete |
| 8 | End-to-end integration, security hardening, performance, containers, and delivery evidence | Delivery candidate implemented; clean tagged verification pending |

The database schema covers the complete v1 data model. The runnable backend surface includes `/health`, `/ready`, authentication, projects/members, prompts, immutable prompt versions, deterministic execution, scoped run history, dashboards, deployment control plane, runtime-token lifecycle, Serve API, and the Super Admin governance surface. The local container stack and automated release verifier are implemented; clean tagged evidence is the remaining Jobin release gate. The current React container still renders Ananya's visual prototype and is not yet wired to these APIs; do not treat its hard-coded screens as end-to-end acceptance evidence.

## Quick start with Docker

Docker Engine with the Compose plugin is the only runtime prerequisite for the complete local stack:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Open the web prototype at `http://localhost:5173`, Swagger UI at `http://localhost:8000/docs`, and API readiness at `http://localhost:8000/ready`. Startup waits for PostgreSQL, then applies all checksum-tracked migrations and idempotent development seeds before starting the API and web services.

`docker compose down` stops containers but preserves the named `promptvault-data` volume. To restore deterministic demo data without removing the volume:

```bash
docker compose run --rm migrate python scripts/reset-development.py --confirm-reset
```

`docker compose down -v` also deletes the local database volume and is intentionally destructive. Use it only when the local development data can be discarded.

## API development

PromptVault requires Python 3.11 or newer. From the repository root:

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

The required settings are `DATABASE_URL` and `SECRET_KEY`. `.env.example` also documents `PROVIDER_ENCRYPTION_KEY`, token lifetime/issuer/audience, environment name, allowed CORS origins, database-pool bounds, database-health timeout, provider timeout, and the global request-body limit. Production refuses placeholder secrets, requires HTTPS CORS origins, and requires separate signing and provider-encryption secrets of at least 32 characters.

Operational endpoints:

- `GET /health` is process liveness and never queries PostgreSQL.
- `GET /ready` runs a bounded `SELECT 1` and returns 503 when PostgreSQL is unavailable.
- `/docs`, `/redoc`, and `/openapi.json` are available outside production.

Authentication endpoints are rooted at `/api/v1/auth`: `POST /register`, `POST /login`, and bearer-protected `GET /me`. Access tokens are short-lived HS256 JWTs; the database user is reloaded on every protected request so role changes and deactivation take effect immediately.

Run endpoints are rooted at `/api/v1/runs`. `POST /runs` renders an immutable version using exact variable keys, executes the deterministic mock provider through a bounded provider interface, snapshots tokens/latency/model/cost, and records completed, failed, or budget-blocked ledger rows. `GET /runs` and `GET /runs/{id}` enforce owner/project-member scope; `GET /api/v1/dashboard/me` returns live personal monthly aggregates and recent runs.

Deployment endpoints are rooted at `/api/v1/deployments`. Development and staging activate immediately; production requests remain pending until a Super Admin uses `/api/v1/admin/deployments`. Approval/rejection and rollback execute through locking PostgreSQL functions, so competing reviews have one winner. Project owners manage hash-only runtime credentials at `/api/v1/api-tokens`; consumers present the one-time plaintext token to `GET /serve/v1/prompts/{key}?env=prod`, which returns the project-scoped active version with `ETag` and private cache headers.

Super Admin governance endpoints are rooted at `/api/v1/admin`. They provide safe user role/status transitions with self-lockout and last-admin protection, live organization analytics and run filters, budget management, encrypted provider-key metadata, append-only pricing history, redacted audit search, maintenance/job status, audited materialized-view refresh, and idempotent next-month partition creation. Provider-key plaintext is accepted only on creation and is never returned.

API startup expects the configured PostgreSQL server to be reachable because the connection pool opens during application lifespan. Requests are logged as redacted JSON with their method, path, status, duration, and request ID; query strings and request bodies are not logged.

`docker compose up -d db` starts only PostgreSQL when developing the API on the host. The packaged API runs as an unprivileged user and the packaged web build is served by Nginx.

## Database commands

The database tools load `.env` and also accept an explicit database URL:

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

Migration history is stored in `schema_migrations`. Applied files are protected by SHA-256 checksums, migration execution is serialized with a PostgreSQL advisory lock, and each migration is atomic. The reset command refuses non-development environments and requires `--confirm-reset`.

The fourteen migrations create the complete v1 relational schema, constraints, partitions, concurrency functions, audit triggers, reporting views, and database roles. The boundary migrations make budget enforcement DST-safe, remove direct application-role ledger insertion, require rollback targets to be earlier than the active version, serialize user-role transitions so the final active Super Admin cannot be removed, and add final cross-entity/lifecycle integrity checks plus query-driven indexes. Seed files use numeric prefixes so identities are always loaded before dependent demo data.

Development seed accounts:

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These credentials are development-only. Their Argon2id hashes—not plaintext passwords—are stored in the seed SQL.

The seed also creates the stable `Checkout Assistant` project, the `support-reply` prompt and version `55555555-5555-4555-8555-555555555555`, plus a User budget. The demo CLIs create uniquely named temporary race records, so they can be rerun safely.

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

For reproducible release verification, run:

```bash
python3 scripts/verify-release.py
```

The command refuses a dirty tree, creates a detached checkout and uniquely named Compose project, builds the web/API images, starts a health-gated stack on unused host ports, creates a disposable `promptvault_test` database, runs lint, type checking, the full backend suite with coverage, OpenAPI drift detection, HTTP/login smoke checks, both race demonstrations, a 2,000-run representative ledger, and every showcase query. It redacts sensitive output, archives the transcript to `evidence/release/latest.txt`, and removes the isolated containers and volume.

## Frontend development

```bash
npm ci --prefix web
npm run dev --prefix web
```

The frontend reads its API location from `VITE_API_URL`. Never put signing secrets or provider keys in Vite environment variables.

The current frontend is a visual/mock implementation: it does not yet call `VITE_API_URL`. API-backed routes, session behavior, and browser E2E checks remain frontend-owned release work.

Frontend checks available on this branch are:

```bash
npm run typecheck --prefix web
npm run build --prefix web
```
