# Run PromptVault with Docker locally

This deployment runs React/nginx and FastAPI in Docker Desktop while reusing the existing PostgreSQL `localhost:5432/promptvault`, also visible in pgAdmin. Accounts and projects stay in that persistent database. Docker Desktop must be running; PostgreSQL and its command-line tools must be installed on the host. Keep the root `.env` private and use the values from [Jobin’s setup](jobin-local-setup.md).

## Start the application

From the repository root, stop any native PromptVault process using ports 5173/8000. Preserve the existing `.env`. Its `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB=promptvault` must identify the same database as `DATABASE_URL`. Keep `ENVIRONMENT=development` for the local demonstration. Preserve `SECRET_KEY` and `PROVIDER_ENCRYPTION_KEY`; changing the latter prevents decryption of existing provider keys.

Before a schema upgrade, create a verified native backup:

```bash
.venv/bin/python scripts/backup-local.py --admin-url postgresql://postgres@localhost:5432/postgres
```

Use `.pgpass` for the administrator password. The administrator needs permission to create/drop an isolated restore database. Use tools compatible with the source server (currently native PostgreSQL 18); an older destination server is not a supported restore target for its dump. Dumps are private files under `secrets/backups/`; the report contains counts, never passwords or account data.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

The migration container applies only outstanding checksummed migrations. This override **does not seed or reset** the existing database. It disables the bundled PostgreSQL container and connects through `host.docker.internal:5432`.

| Service | Local address |
|---|---|
| Website | http://localhost:5173 |
| API and readiness | http://localhost:8000/ready |
| API documentation | http://localhost:8000/docs |
| Persistent PostgreSQL | localhost:5432/promptvault |

Application ports bind to loopback only. This setup needs no public domain or paid hosting. `dev`, `staging`, and `prod` inside the deployment UI are prompt promotion labels.

## SMTP and browser links

The backend container sends SMTP messages. Existing Gmail SMTP settings in `.env` are forwarded to it: host `smtp.gmail.com`, port 587, STARTTLS true, SSL false, username, App Password and sender address. Never put SMTP credentials in frontend `VITE_*` variables or source control. Keep these URLs on the frontend port:

```dotenv
EMAIL_VERIFICATION_URL=http://localhost:5173/verify-email
PASSWORD_RESET_URL=http://localhost:5173/reset-password
PROJECT_INVITATION_URL=http://localhost:5173/project-invitations
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
VITE_API_URL=http://localhost:8000
```

After changing SMTP settings, recreate API containers with the same `up` command. Changing `VITE_API_URL` requires rebuilding the web image. For a host Mailpit inbox, set `SMTP_HOST=host.docker.internal`, port 1025, disable STARTTLS/SSL and clear SMTP credentials; keep the browser inbox at localhost:8025. A container cannot reach the host’s Mailpit using its own `localhost`.

Verification/reset/invitation flows are tested with loopback capture or simulated SMTP; verification does not send unsolicited real email. Gemini is the only LLM provider in every environment. There is no local mock adapter or paid fallback. Existing historical configurations remain readable, but retired providers cannot be executed, served or newly activated. Save a new Gemini configuration in Playground, then promote it explicitly. Removed-provider keys are deactivated; Gemini keys remain encrypted and unchanged.

## Stop, inspect, or switch back

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=100 api migrate
docker compose -f docker-compose.yml -f docker-compose.local.yml down
.venv/bin/python scripts/start-local.py
```

`down` stops app containers and leaves native PostgreSQL untouched. Do not use reset commands or delete database volumes to troubleshoot an existing installation. Diagnose migration checksum failures rather than editing an applied migration. To restore a private dump, first restore into a new isolated database with `pg_restore --no-owner --no-acl --exit-on-error`; verify it before any deliberate replacement of live data. Preserve the original encryption key with a transferred database.

## Isolated verification stack

The base `docker-compose.yml` intentionally provides a separate fresh PostgreSQL container and development seeds. Use a separate Compose project and unused ports for this stack; never run it on port 5432 while the native database is running. Its `verify` profile runs lint, mypy, backend tests with coverage, compile checks, dependency checks, OpenAPI drift and SQL showcase checks. The verification database is `promptvault_test`, separate from application data. SMTP should be disabled for that stack. The commands and test boundaries are described in the root [README](../README.md#testing).
