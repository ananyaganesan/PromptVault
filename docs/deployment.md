# Deployment and recovery expectations

The packaged stack is intended for local development and evaluation. `docker compose up -d --build --wait` starts PostgreSQL, runs migrations and, only when `ENVIRONMENT=development`, development seeds once, starts the API after that job succeeds, and starts the web container only after API readiness succeeds. The direct seed command also refuses non-development/non-test environments.

| Service | Role | Startup gate |
|---|---|---|
| `db` | PostgreSQL 16 system of record | `pg_isready` |
| `migrate` | One-shot migration job; seeds only in development | Healthy database |
| `api` | Unprivileged Uvicorn/FastAPI process | Successful migration job; `/ready` health check |
| `web` | Nginx serving the Vite build with SPA fallback | Healthy API; HTTP health check |
| `verify` | Optional containerized backend quality suite | `verification` profile only; healthy database |

The Compose defaults are development placeholders. Copy `.env.example`, change passwords and application secrets before any shared deployment, and never use the Compose defaults in production. `VITE_API_URL` is compiled into the browser bundle and therefore must contain only a public API address, never a secret.

Production startup additionally requires `DATABASE_ROLE=promptvault_app`. Provision a dedicated non-owner login for `DATABASE_URL`, grant it membership in `promptvault_app`, and do not grant superuser, role-creation, database-creation, or schema-ownership privileges. The API sets that role on every pooled connection. Migration credentials are a separate deployment concern and should be available only to the one-shot migration job.

Password reset requires a public HTTPS `PASSWORD_RESET_URL` in production and backend SMTP settings (`SMTP_HOST`, `SMTP_FROM_EMAIL`, and, for Gmail, `SMTP_USERNAME` and a Google App Password in `SMTP_PASSWORD`). Port 587 uses STARTTLS by default; port 465 uses `SMTP_SSL=true` and `SMTP_STARTTLS=false`. These settings are passed only to the API and migration containers, never to the browser build. Verify Gmail delivery before advertising password recovery.

Container and CI installs use the fully pinned `api/requirements.lock` and `api/requirements-dev.lock`; the adjacent `.txt` files remain the human-maintained compatible dependency ranges. Regenerate and verify lock files deliberately when upgrading dependencies.

## Durable data

PostgreSQL is the system of record. API restarts are stateless: the connection pool closes during shutdown and a new pool restores access to committed projects, prompt snapshots, deployments, tokens, runs, and audit events. `tests/e2e/test_user_prompt_workflow.py` exercises that restart boundary.

The named `promptvault-data` volume survives `docker compose down`. `docker compose down -v` destroys that local database and is not recoverable unless it was backed up. The migration/seed job is idempotent on an existing development volume; a changed checksum for an already-applied migration fails closed. The sole recorded-history exception reconciles an exact, previously misnumbered password-reset migration from 011 to 015 when its table is present.

For any environment whose data matters, take a logical or managed PostgreSQL backup before migrations or reset operations. Restore into a separate database first, run migrations, and verify row counts plus the critical Serve/deployment flow before switching traffic. A production deployment should add scheduled backups, retention, encryption, restore drills, and point-in-time recovery according to its PostgreSQL provider.

## Production operations

- Terminate TLS at a trusted ingress, redirect HTTP to HTTPS, use HSTS after validation, and permit only the documented public web/API origins. PostgreSQL and SMTP connections must use transport encryption supplied by their providers.
- Keep JWT access tokens short-lived. Rotate `SECRET_KEY` through the secret manager during a planned session invalidation, never log it, and keep `JWT_ISSUER`/`JWT_AUDIENCE` environment-specific. PromptVault intentionally has no refresh-token session.
- The process-local login/reset limits are a safety floor. Enforce a shared per-IP/account limit at the ingress for multiple replicas and alert on sustained `429`, `401`, password-reset `503`, and provider-error rates.
- Monitor `/health` for process liveness and `/ready` for database readiness; ingest structured request logs by request ID without bodies or query strings. Alert on readiness failures, elevated 5xx latency, pool exhaustion, failed migration jobs, missing run partitions, stale materialized views, and backup failures.
- Create the next run partition before each month boundary and refresh reporting views on the analytics freshness schedule. Both operations are exposed through audited Super Admin maintenance endpoints/scripts. Verify the result rather than treating command exit alone as evidence.
- Take encrypted scheduled backups with retention and point-in-time recovery where available. Run recurring restore drills into an isolated database and validate migrations, row counts, login, run recording, deployment approval, and Serve retrieval.

## Reset boundaries

`python3 scripts/reset-development.py --confirm-reset` is intentionally restricted to the development environment and reconstructs schema, migrations, and seed data. Never point it at a shared or production database. Tests require a dedicated `TEST_DATABASE_URL`; clean verification drops/recreates only that disposable test schema.

The migration runner stores SHA-256 checksums in `schema_migrations`, takes an advisory lock, and applies each file atomically. Applied migration files must not be edited; introduce a later numbered migration instead. Current and next-month run partitions must exist before accepting ledger writes.

## Verification and evidence

`python3 scripts/verify-release.py` refuses a dirty tree, creates a detached checkout and uniquely named Compose project, builds the images, runs the containerized verification profile against `promptvault_test`, probes liveness/readiness/web/login, executes race demonstrations, loads the representative 2,000-run ledger, and runs showcase SQL. It writes a redacted `evidence/release/latest.txt`, then removes the isolated containers and volume. Release tags are created only after this command passes.

The `verify` profile is not part of normal startup. It contains development tooling and must not be deployed as an application service.

## Prototype limitations

TLS termination, distributed edge rate limiting, managed secret delivery, restricted-login provisioning, automated backup scheduling, multi-instance orchestration, and zero-downtime migration strategy remain infrastructure responsibilities. The application enforces production configuration, sets the restricted database role, and supplies audited maintenance operations, but local Compose intentionally connects with the development database owner.
