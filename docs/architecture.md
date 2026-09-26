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
- Every protected write opens one database transaction and sets local `app.user_id` and `app.request_id` values before audited mutations.

### Implemented API foundation

- `api.app.config` validates environment, database, CORS, pool, timeout, and production-secret settings.
- `api.app.main.create_app` builds the service and owns the pool lifespan; `api.app.main:app` is the Uvicorn entrypoint.
- `api.app.db.pool` constructs one asynchronous Psycopg pool and exposes it through request state.
- `api.app.db.migrations` discovers ordered SQL files, validates immutable checksums, serializes runners with an advisory lock, and records each applied migration transactionally.
- `api.app.db.commands` provides atomic seed and guarded development-reset operations.
- `api.app.dependencies.request_context` validates or creates request IDs and returns them on responses.
- `api.app.errors` provides the public error envelope and redacts validation inputs and unexpected failures.
- `api.app.logging_config` emits allowlisted JSON request/error events without request bodies, query strings, secrets, or exception messages.
- `api.app.routers.health` separates process liveness from bounded database readiness.
- `api.app.openapi` produces the deterministic `docs/openapi.json` frontend contract artifact.
- `api.app.security` owns Argon2id password handling and issuer/audience-bound HS256 access tokens.
- `api.app.repositories.users` performs parameterized identity and project-scope lookups.
- `api.app.services.auth` implements register/login without accepting a client role.
- `api.app.dependencies.auth` reloads the active database user for every protected request.
- `api.app.dependencies.authorization` provides active Super Admin and project member/owner guards.
- `api.app.repositories.projects`, `prompts`, and `versions` provide parameterized, membership-scoped persistence and deterministic pagination.
- `api.app.services.projects` owns project/member workflows and audit attribution.
- `api.app.services.prompt_versioning` owns prompt metadata, variable extraction, immutable version creation, structured diff, and recursive lineage.
- `api.app.routers.projects`, `prompts`, and `versions` expose the Phase 2 HTTP contract.
- `api.app.providers` defines the bounded provider interface and deterministic mock behavior.
- `api.app.repositories.runs`, `pricing`, and `budgets` resolve scoped targets, effective prices, and append-only ledger data.
- `api.app.services.playground`, `budget_enforcement`, and `analytics` orchestrate safe rendering, execution, atomic admission, and live personal aggregates.
- `api.app.routers.runs` and `dashboard` expose the Phase 3 HTTP contract.
- `api.app.repositories.deployments` and `api.app.services.deployments` implement scoped history, cancellation, evidence-backed review, and database-serialized production transitions.
- `api.app.repositories.tokens` stores only SHA-256 runtime-token hashes and resolves active prompts inside the credential's project scope.
- `api.app.routers.deployments`, `admin`, `tokens`, and `serve` expose the Phase 4 deployment, review, rollback, token, and runtime contract.
- `api.app.repositories.admin` and `api.app.services.admin` implement user governance, live organization analytics, budget management, encrypted provider-key metadata, effective-dated pricing, and maintenance operations.
- `api.app.repositories.audit` and `api.app.services.audit` expose filterable, defensively redacted audit history to Super Admins.

Operational, authentication, project/member, prompt/version, run, dashboards, deployment, approval, rollback, runtime-token, Serve, and organization-governance routes are implemented.

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
2. The effective provider/model price is selected for the execution timestamp.
3. The selected provider adapter executes within a configured timeout.
4. Token usage and the effective price produce a six-decimal historical cost snapshot.
5. The run ledger insertion locks applicable user/project budgets, performs the authoritative admission check, and records success, failure, or blocked status atomically.

### Deploy and serve

1. Development and staging requests atomically supersede the active deployment and activate the selected version.
2. Production requests are always inserted as `pending`.
3. An admin approves or rejects through a locking database procedure; repeated or competing reviews return a conflict.
4. Rollback inserts a new deployment pointing to an earlier immutable version.
5. The Serve endpoint hashes the presented token, resolves its project scope, and returns the active version for the requested environment.

### Administer governance controls

1. The reusable Super Admin dependency reloads the active database user and rejects stale roles or inactive accounts.
2. User role/status transitions execute exclusively through a serialized database function that blocks self-lockout and preserves at least one active Super Admin.
3. Provider secrets are encrypted before persistence; API responses contain metadata only.
4. Budget, pricing, provider-key, and user changes set actor/request context so audit triggers capture attributable, redacted events.
5. Analytics reconcile directly from the run ledger, while least-privilege security-definer maintenance functions refresh views or create partitions and append attributed audit events.

## Error handling and observability

Every request receives a request ID. Clients may supply `X-Request-ID`; otherwise the API creates one. The same identifier is returned in the response and included in structured logs. Non-success responses use the envelope in `api-contracts.md`. Database constraint names and provider secrets never appear in client messages or logs.

Expected application failures map to 400, 401, 403, 404, 409, or 422. Provider availability failures map to 502 or 504. Unexpected failures return a generic 500 response. Readiness returns 503 when PostgreSQL cannot complete `SELECT 1` within its timeout.

## Consistency and concurrency

- Prompt version numbering locks one prompt row, allowing unrelated prompts to proceed concurrently.
- A partial unique index guarantees one active deployment per prompt and environment.
- Approval and rollback lock the deployment state and run atomically.
- Pending cancellation is a conditional atomic transition; a concurrent cancellation/review cannot both succeed.
- Runtime-token authentication performs a hash lookup constrained to non-revoked, non-expired credentials, and prompt lookup is constrained to that token's project.
- Budget admission locks the applicable target/month before evaluating ledger spend.
- Admin role/status transitions use a transaction advisory lock so concurrent changes cannot remove every active Super Admin.
- Runs and audit records are append-only from application roles.
- Monthly run partitions are created explicitly for the current and next month.

### Implemented database foundation

The executable migrations in `db/migrations/` now provide the complete v1 storage shape. UUID-backed identity, project, prompt, governance, token, deployment, and audit tables are normalized; the append-only run ledger is partitioned monthly. Composite foreign keys prevent cross-prompt parent/deployment references, effective-date exclusion constraints prevent overlapping prices, and partial unique indexes enforce one active deployment and one budget per target.

Concurrency-sensitive writes use database functions rather than read-then-write application sequences. Prompt rows serialize version numbering, prompt/deployment rows serialize activation and review, and budget rows serialize spend admission. Immutable version/run history and audit attribution are enforced with triggers even if a future repository attempts an unsafe write.

Project-member and prompt-member access rows are locked for the lifetime of scoped write transactions. Concurrent membership removal therefore waits for an already-authorized mutation to commit, while a mutation that begins after removal is rejected. Direct prompt/version reads include membership scope in the lookup and use the same not-found result for inaccessible and unknown identifiers.

Provider execution uses no database connection: short transactions load the immutable version and effective price before the call, then revalidate and lock current user/membership access while recording the result. Completed run insertion uses the `SECURITY DEFINER` `record_run` function as the application role's only budget-admission boundary. Applicable budget rows are locked in deterministic order before timezone-correct monthly spend is read, so concurrent executions cannot overspend either a user or project limit. Failure and blocked rows commit before the client receives a normalized 502/504 or 409 response.

## Testing boundaries

- Unit tests cover security helpers, template parsing/rendering, provider normalization, and cost/error mapping.
- Database tests prove constraints, triggers, functions, procedures, partitions, and grants against PostgreSQL 16.
- API tests cover every endpoint's happy path, validation, anonymous, forbidden, missing, conflict, and safe database-failure behavior.
- End-to-end tests prove the storyboard in `demo-storyboard.md`.
- Concurrency tests run 20 competing version saves, 100 competing approvals, and parallel budget-consuming runs.

## Ownership and integration

Ananya owns `web/`. Jobin owns `api/`, `db/`, root `tests/`, `scripts/`, and backend-related documentation. `api-contracts.md`, `route-map.md`, and `authorization-matrix.md` are shared interfaces: changes require a short entry in `contract-questions.md` before either side depends on a different shape.
