# Deployment and recovery expectations

The default packaged stack is intended for local development and evaluation. `docker compose up -d --build --wait` starts PostgreSQL, runs migrations and, only when `ENVIRONMENT=development`, development seeds once, starts the API after that job succeeds, and starts the web container only after API readiness succeeds. The direct seed command also refuses non-development/non-test environments.

| Service | Role | Startup gate |
|---|---|---|
| `db` | PostgreSQL 16 system of record | `pg_isready` |
| `migrate` | One-shot migration job; seeds only in development | Healthy database |
| `api` | Unprivileged Uvicorn/FastAPI process | Successful migration job; `/ready` health check |
| `web` | Nginx serving the Vite build with SPA fallback | Healthy API; HTTP health check |
| `verify` | Optional containerized backend quality suite | `verification` profile only; healthy database |

The Compose defaults are development placeholders. Copy `.env.example`, change passwords and application secrets before any shared deployment, and never use the Compose defaults in production. `VITE_API_URL` is compiled into the browser bundle and therefore must contain only a public API address, never a secret.

Production startup additionally requires `DATABASE_ROLE=promptvault_app`. `docker-compose.production.yml` separates the owner-only migration URL from the runtime URL and runs the idempotent `provision-production-role.py` job between migrations and API startup. The runtime login receives membership in `promptvault_app`, bounded statement/idle-transaction timeouts, and no superuser, role-creation, database-creation, or schema ownership. The API sets the restricted role on every pooled connection.

## Production Compose deployment

Point the public DNS name at the host and permit inbound TCP 80/443 plus UDP 443. Copy `.env.production.example` to an operator-managed environment file. Create an owner-only `SECRET_DIR` containing files named `postgres_owner_password`, `migration_database_url`, `runtime_database_password`, `runtime_database_url`, `secret_key`, `provider_encryption_key`, `redis_password`, `rate_limit_redis_url`, `smtp_password`, `alert_webhook_url`, `restic_password`, and `restic_credentials`; set every file to mode `0400` or `0600`. `alert_webhook_url` contains the HTTPS receiver URL. `restic_credentials` uses the AWS shared-credentials format for S3-compatible storage. The two database URLs must use the owner and `promptvault_runtime` passwords respectively, and the Redis URL must contain the same password used by the Redis service. Percent-encode URI-reserved password characters in URL files.

Run the offline preflight before starting containers, then rerun it without `--offline` after DNS points at the host and Caddy has obtained its certificate:

```bash
set -a; . ./.env.production; set +a
python3 scripts/production-preflight.py --offline
python3 scripts/production-preflight.py
```

The preflight prints only failing field/file names, never secret contents. SMTP, alerting, and off-site backup checks are required by default; `--skip-smtp`, `--skip-alerting`, and `--skip-offsite` make an intentionally omitted integration explicit.

```bash
DOMAIN=promptvault.example.com SECRET_DIR=/secure/promptvault \
  docker compose -f docker-compose.production.yml up -d --build --wait
```

Caddy obtains and renews public certificates, redirects HTTP to HTTPS, adds HSTS and security headers, and exposes only ports 80/443. PostgreSQL, Redis, the API, web server, Prometheus, and `/metrics` remain on an internal Docker network. Because the API has no published port and only Caddy can reach it on that network, Uvicorn trusts Caddy's forwarded client address for per-client throttling. Application, Redis, database, and SMTP password secrets are mounted as files rather than committed or placed in Compose YAML.

Prometheus scrapes the internal low-cardinality `/metrics` endpoint and loads alerts for API availability, 5xx ratio, and mean latency. The packaged Alertmanager groups alerts by name/severity and sends firing and resolved notifications to the HTTPS URL stored in `alert_webhook_url`. Aggregate the API's structured JSON container logs in the platform's log destination before accepting production traffic.

The `operations` profile starts an always-on scheduler that writes an atomic custom-format dump every `BACKUP_INTERVAL_SECONDS` and removes expired dumps. The one-shot command remains available for release or migration checkpoints:

```bash
DOMAIN=promptvault.example.com SECRET_DIR=/secure/promptvault \
  docker compose -f docker-compose.production.yml --profile operations run --rm backup
```

Enable the `offsite-backup` profile to start the same scheduler plus restic replication. Restic encrypts each snapshot before sending it to `RESTIC_REPOSITORY`, applies daily/weekly/monthly retention, and ignores incomplete `.partial` dumps:

```bash
docker compose -f docker-compose.production.yml --profile offsite-backup up -d --wait
```

Object-storage immutability/retention lock and alert delivery remain provider controls and must be verified in the target account.

Password reset requires a public HTTPS `PASSWORD_RESET_URL` in production and backend SMTP settings (`SMTP_HOST`, `SMTP_FROM_EMAIL`, and, for Gmail, `SMTP_USERNAME` and a Google App Password in `SMTP_PASSWORD`). Port 587 uses STARTTLS by default; port 465 uses `SMTP_SSL=true` and `SMTP_STARTTLS=false`. These settings are passed only to the API and migration containers, never to the browser build. Verify Gmail delivery before advertising password recovery.

Gemini execution is optional. Keep `GEMINI_API_BASE_URL` at Google's HTTPS endpoint, create an active provider key whose provider is `gemini` through the admin API, and add effective-dated pricing for each enabled model before saving a Gemini-backed prompt version. PromptVault decrypts the newest active key only for the outbound request and sends it in the `x-goog-api-key` header; it never places the plaintext key in API responses, logs, or run records. The deterministic `mock` provider remains available for offline verification.

Container and CI installs use the fully pinned `api/requirements.lock` and `api/requirements-dev.lock`; the adjacent `.txt` files remain the human-maintained compatible dependency ranges. Regenerate and verify lock files deliberately when upgrading dependencies.

## Durable data

PostgreSQL is the system of record. API restarts are stateless: the connection pool closes during shutdown and a new pool restores access to committed projects, prompt snapshots, deployments, tokens, runs, and audit events. `tests/e2e/test_user_prompt_workflow.py` exercises that restart boundary.

The named `promptvault-data` volume survives `docker compose down`. `docker compose down -v` destroys that local database and is not recoverable unless it was backed up. The migration/seed job is idempotent on an existing development volume; a changed checksum for an already-applied migration fails closed. The sole recorded-history exception reconciles an exact, previously misnumbered password-reset migration from 011 to 015 when its table is present.

For any environment whose data matters, take a logical or managed PostgreSQL backup before migrations or reset operations. Restore into a separate database first, run migrations, and verify row counts plus the critical Serve/deployment flow before switching traffic. With the local Compose database running, `python3 scripts/verify-backup.py` automates a non-destructive drill: it creates a custom-format dump, restores it into a randomly named scratch database, compares critical table counts, and removes the scratch database in a `finally` cleanup. The release verifier runs this after loading the representative 2,000-run ledger. A production deployment should add scheduled backups, retention, encryption, restore drills, and point-in-time recovery according to its PostgreSQL provider.

## Production operations

- Terminate TLS at a trusted ingress, redirect HTTP to HTTPS, use HSTS after validation, and permit only the documented public web/API origins. PostgreSQL and SMTP connections must use transport encryption supplied by their providers.
- Keep JWT access tokens short-lived. Rotate `SECRET_KEY` through the secret manager during a planned session invalidation, never log it, and keep `JWT_ISSUER`/`JWT_AUDIENCE` environment-specific. PromptVault intentionally has no refresh-token session.
- Production authentication/reset limits use Redis so multiple API replicas share counters. Retain a coarser ingress/WAF limit and alert on sustained `429`, `401`, password-reset `503`, and provider-error rates.
- Monitor `/health` for process liveness and `/ready` for database readiness; ingest structured request logs by request ID without bodies or query strings. Alert on readiness failures, elevated 5xx latency, pool exhaustion, failed migration jobs, missing run partitions, stale materialized views, and backup failures.
- Create the next run partition before each month boundary and refresh reporting views on the analytics freshness schedule. Both operations are exposed through audited Super Admin maintenance endpoints/scripts. Verify the result rather than treating command exit alone as evidence.
- Take encrypted scheduled backups with retention and point-in-time recovery where available. Run recurring restore drills into an isolated database and validate migrations, row counts, login, run recording, deployment approval, and Serve retrieval.

## Reset boundaries

`python3 scripts/reset-development.py --confirm-reset` is intentionally restricted to the development environment and reconstructs schema, migrations, and seed data. Never point it at a shared or production database. Tests require a dedicated `TEST_DATABASE_URL`; clean verification drops/recreates only that disposable test schema.

The migration runner stores SHA-256 checksums in `schema_migrations`, takes an advisory lock, and applies each file atomically. Applied migration files must not be edited; introduce a later numbered migration instead. Current and next-month run partitions must exist before accepting ledger writes.

## Verification and evidence

`python3 scripts/verify-release.py` refuses a dirty tree, creates a detached checkout and uniquely named Compose project, builds the images, runs the containerized verification profile against `promptvault_test`, probes liveness/readiness/web/login, executes race demonstrations, loads the representative 2,000-run ledger, and runs showcase SQL. It writes a redacted `evidence/release/latest.txt`, then removes the isolated containers and volume. Release tags are created only after this command passes.

The `verify` profile is not part of normal startup. It contains development tooling and must not be deployed as an application service.

## Deployment boundaries

The repository supplies TLS termination, Redis-backed application throttling, file-mounted secret wiring, restricted-login provisioning, Prometheus plus Alertmanager webhook routing, scheduled atomic dumps, optional encrypted restic replication, and production preflight checks. DNS ownership, real SMTP/Gemini credentials, the Alertmanager receiver, object-storage account/retention lock, log destination, multi-host orchestration, and zero-downtime migration strategy must be supplied and tested in the target platform. The default local Compose stack intentionally remains development-oriented.
