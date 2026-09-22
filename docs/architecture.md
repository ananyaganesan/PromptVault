# PromptVault v1 architecture

## Purpose and scope

PromptVault is a two-role prompt versioning, execution, and deployment platform. Users create projects and immutable prompt versions, execute versions, and deploy to development or staging. Production changes require an administrator review. External consumers fetch an active prompt through a project-scoped Serve token.

The v1 roles are stored as `user` and `admin`; the UI labels `admin` as **Super Admin**. A/B testing, semantic search, LLM-as-judge, SSO, prompt branches, and row-level-security multi-tenancy are outside v1.

## Runtime components

| Component | Responsibility | Must not own |
|---|---|---|
| React web client | Pages, input validation, session-aware navigation, API calls, cached server state | Authorization decisions, secrets, version numbers, cost calculation |
| FastAPI routers | HTTP parsing, Pydantic validation, dependencies, status codes, response schemas | Raw SQL or multi-step business rules |
| Application services | Transaction boundaries and orchestration of repositories, providers, and database procedures | Browser state or duplicated database invariants |
| Repositories | Parameterized SQL and row-to-schema mapping | HTTP behavior or provider calls |
| Provider adapters | Deterministic mock and Gemini execution behind one interface | Database writes or API responses |
| PostgreSQL 16 | Durable state, referential integrity, immutable history, concurrency control, cost and budget rules, audit | HTTP authentication or presentation formatting |

## Dependency direction

```text
web -> HTTP contract -> routers -> services -> repositories -> PostgreSQL
                                  |-> provider adapter
```

Dependencies point inward. Routers may depend on schemas, services, and authorization dependencies. Services may depend on repositories and provider interfaces. Repositories do not import routers or services. Database procedures are the only write path for approval and rollback transitions.

## API boundaries

- Application endpoints are rooted at `/api/v1`.
- Process liveness and readiness are `/health` and `/ready`.
- Runtime prompt delivery remains `/serve/v1/prompts/{key}` so consumers are not coupled to the application API namespace.
- Browser authentication uses a short-lived bearer JWT in v1. The client keeps it in memory; page refresh requires signing in again. Refresh tokens and cookie sessions are deferred.
- Serve authentication uses a separate high-entropy bearer token. Only its SHA-256 hash is stored.
- Every protected write opens one database transaction and runs `SET LOCAL app.user_id = ...` before audited mutations.

### Implemented API foundation

- `api.app.config` validates environment, database, CORS, pool, timeout, and production-secret settings.
- `api.app.main.create_app` builds the service and owns the pool lifespan; `api.app.main:app` is the Uvicorn entrypoint.
- `api.app.db.pool` constructs one asynchronous Psycopg pool and exposes it through request state.
- `api.app.dependencies.request_context` validates or creates request IDs and returns them on responses.
- `api.app.errors` provides the public error envelope and redacts validation inputs and unexpected failures.
- `api.app.routers.health` separates process liveness from bounded database readiness.

The application currently has only operational routes. Versioned product routers begin after the migration and authentication foundations.

## Primary data flow

### Save a prompt version

1. The router validates the request and resolves the active user.
2. The membership dependency establishes access to the prompt's project.
3. The service extracts and validates `{{variable_name}}` placeholders.
4. The repository inserts the version and variables in one transaction.
5. PostgreSQL locks the parent prompt row and assigns the next version number.
6. The inserted snapshot is immutable; no update or delete endpoint exists.

### Execute a version

1. Authorization and exact variable matching are checked before provider use.
2. Applicable user and project budgets are pre-checked to avoid a known charge.
3. The selected provider adapter executes the rendered prompt.
4. PostgreSQL calculates historical cost from the effective model price.
5. The run ledger insertion performs the authoritative budget check and records success, failure, or blocked status.

### Deploy and serve

1. Development and staging requests atomically supersede the active deployment and activate the selected version.
2. Production requests are always inserted as `pending`.
3. An admin approves or rejects through a locking database procedure; repeated or competing reviews return a conflict.
4. Rollback inserts a new deployment pointing to an earlier immutable version.
5. The Serve endpoint hashes the presented token, resolves its project scope, and returns the active version for the requested environment.

## Error handling and observability

Every request receives a request ID. Clients may supply `X-Request-ID`; otherwise the API creates one. The same identifier is returned in the response and included in structured logs. Non-success responses use the envelope in `api-contracts.md`. Database constraint names and provider secrets never appear in client messages or logs.

Expected application failures map to 400, 401, 403, 404, 409, or 422. Provider availability failures map to 502 or 504. Unexpected failures return a generic 500 response. Readiness returns 503 when PostgreSQL cannot complete `SELECT 1` within its timeout.

## Consistency and concurrency

- Prompt version numbering locks one prompt row, allowing unrelated prompts to proceed concurrently.
- A partial unique index guarantees one active deployment per prompt and environment.
- Approval and rollback lock the deployment state and run atomically.
- Budget admission locks the applicable target/month before evaluating ledger spend.
- Runs and audit records are append-only from application roles.
- Monthly run partitions are created explicitly for the current and next month.

## Testing boundaries

- Unit tests cover security helpers, template parsing/rendering, provider normalization, and cost/error mapping.
- Database tests prove constraints, triggers, functions, procedures, partitions, and grants against PostgreSQL 16.
- API tests cover every endpoint's happy path, validation, anonymous, forbidden, missing, conflict, and safe database-failure behavior.
- End-to-end tests prove the storyboard in `demo-storyboard.md`.
- Concurrency tests run 20 competing version saves, 100 competing approvals, and parallel budget-consuming runs.

## Ownership and integration

Ananya owns `web/`. Jobin owns `api/`, `db/`, root `tests/`, `scripts/`, and backend-related documentation. `api-contracts.md`, `route-map.md`, and `authorization-matrix.md` are shared interfaces: changes require a short entry in `contract-questions.md` before either side depends on a different shape.
