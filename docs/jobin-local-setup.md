# Jobin’s local setup and database reference

Use this guide to run the same PromptVault code on your own computer. Run commands from the repository root unless stated otherwise. Use the same Git commit/shared working copy as Ananya; migrations reproduce the schema, while an optional database transfer reproduces existing records. A source checkout alone does not include current accounts, projects or provider credentials.

## 1. Prerequisites and fixed ports

Install Python 3.11+, Node.js 22.12+ with npm, PostgreSQL 16 with its command-line tools (`psql`, `pg_dump`, `pg_restore`), and optionally pgAdmin. Docker is needed only for the optional Mailpit local inbox below. Keep PostgreSQL running on port 5432.

| Component | Host / port | Purpose |
|---|---|---|
| React/Vite frontend | `http://localhost:5173` | Open this website in the browser |
| FastAPI backend | `http://localhost:8000` | Frontend API requests; `/api/v1` application routes |
| Swagger | `http://localhost:8000/docs` | Interactive API reference |
| PostgreSQL | `localhost:5432/promptvault` | Persistent application database, also visible in pgAdmin |
| Optional local SMTP | `127.0.0.1:1025` | Backend sends verification/reset/invitation messages here |
| Optional local inbox | `http://localhost:8025` | Read captured messages and click their links |

SMTP port 1025 receives mail; port 8025 displays it; email links point back to frontend port 5173. The browser calls backend port 8000. Use `localhost` consistently for the website and link URLs. This setup is loopback-only on your own computer.

## 2. Install the project dependencies

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements-dev.lock
npm ci --prefix web
```

On a fresh checkout only, copy the environment examples:

```bash
cp -n .env.example .env
cp -n web/.env.example web/.env.local
```

If either file already exists, preserve and edit it. `.env` holds backend secrets and is ignored by Git. Frontend `VITE_*` values are public browser configuration and must never contain passwords or keys.

## 3. Create the persistent database once

For a new PostgreSQL installation, connect as its administrator (for example `psql -h localhost -p 5432 -U postgres -d postgres`, or use pgAdmin’s Query Tool against `postgres`). Run these statements separately with autocommit enabled, **only if the role/database do not already exist**:

```sql
CREATE ROLE promptvault WITH LOGIN PASSWORD 'promptvault' CREATEROLE;
CREATE DATABASE promptvault OWNER promptvault;
```

These are local example credentials. If using another password, update `.env` and percent-encode reserved characters in `DATABASE_URL`. Migrations create `promptvault_app` and `promptvault_readonly` group roles, so the migration login needs role-creation permission. The database owner must also be able to install the `pgcrypto`, `citext` and `btree_gist` extensions. Do not alter or recreate an existing role/database just to match the example password.

Set these values in the root `.env` (replace existing entries rather than creating duplicate keys):

```dotenv
ENVIRONMENT=development
DATABASE_URL=postgresql://promptvault:promptvault@localhost:5432/promptvault
DATABASE_ROLE=
POSTGRES_DB=promptvault
POSTGRES_USER=promptvault
POSTGRES_PASSWORD=promptvault
POSTGRES_PORT=5432
API_PORT=8000
WEB_PORT=5173
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
VITE_API_URL=http://localhost:8000
PASSWORD_RESET_URL=http://localhost:5173/reset-password
EMAIL_VERIFICATION_URL=http://localhost:5173/verify-email
PROJECT_INVITATION_URL=http://localhost:5173/project-invitations
```

Generate two separate local secret values with the command below and place them in `SECRET_KEY` and `PROVIDER_ENCRYPTION_KEY` in `.env`:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Keep these values stable across restarts. Copying encrypted provider records from another database requires its original `PROVIDER_ENCRYPTION_KEY`; generating a replacement prevents decryption. Sharing a database snapshot also shares account/session data, so transfer it and its required secrets privately.

In `web/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_DEMO_DATA=false
```

The launcher also enforces the backend URL and disables demo data for normal startup. Do not add `/api/v1` to the base URL; the client appends it.

Check the connection, then apply migrations:

```bash
.venv/bin/python scripts/start-local.py --check
.venv/bin/python scripts/run-migrations.py
```

For a **brand-new empty database only**, optionally load demo accounts/data:

```bash
.venv/bin/python scripts/seed-database.py
```

The seeded logins are listed in the root [README](../README.md). Seeds can update existing fixture users/passwords; skip this step on a restored or already-used database. Normal startup never seeds, resets or overwrites accounts.

In pgAdmin, register a server using host `localhost`, port `5432`, maintenance database `promptvault`, username `promptvault` and the password from your own `.env`. Expand **Databases → promptvault → Schemas → public → Tables**. pgAdmin is a client of this same server, not another database.

## 4. Configure email before registering

### Option A: local inbox, no external email account

Start Docker, then create the local capture inbox:

```bash
docker run -d --name promptvault-mailpit \
  -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 \
  axllent/mailpit
```

On subsequent runs use `docker start promptvault-mailpit`. Mailpit captures messages without delivering them to real inboxes. Its [official Docker instructions](https://mailpit.axllent.org/docs/install/docker/) document the SMTP and web ports. These settings assume the API runs natively through `start-local.py`.

Edit root `.env`:

```dotenv
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_FROM_EMAIL=promptvault@example.com
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_STARTTLS=false
SMTP_SSL=false
SMTP_TIMEOUT_SECONDS=10
```

Clear any previous SMTP username/password when switching to capture mode. Open `http://localhost:8025` to read verification, password-reset and invitation messages. Stop the inbox with `docker stop promptvault-mailpit` when finished. Capture messages contain login-related links; keep the inbox local.

### Option B: deliver to a real inbox

Use your own SMTP account credentials. The existing interactive helper writes Gmail settings without putting the password in shell history:

```bash
.venv/bin/python scripts/configure-smtp.py
```

It requires a Google App Password. Keep the frontend reset URL at `http://localhost:5173/reset-password` and check the verification and invitation URLs above too. Use port 587 with STARTTLS, or port 465 with SSL and STARTTLS disabled, as supported by your SMTP service. Restart the native launcher after editing `.env`; the helper’s Docker restart suggestion is for container users. Real inbox delivery must be checked with your own account; local capture does not prove external delivery.

## 5. Start and check the local website

```bash
.venv/bin/python scripts/start-local.py
```

Leave this terminal running. The launcher checks `localhost:5432/promptvault`, applies pending migrations, starts the API on 8000 and Vite on 5173, and refuses an occupied port instead of selecting another. Ctrl-C stops both app processes and leaves PostgreSQL/data intact.

In a second terminal:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/ready
curl --fail --output /dev/null http://localhost:5173/
```

Open `http://localhost:5173` and check the complete email path:

1. Register a new address. Open the verification message in Mailpit (or your real inbox), follow its frontend link and then log in. Verification links are hashed, one-use and expire after 30 minutes. Existing migrated and seeded accounts remain verified.
2. Request a password reset, follow the received link, set a new password and confirm login. Previously issued sessions are revoked by reset.
3. Invite another registered account to a project, open its invitation while signed in as that recipient and accept. Pending invitations alone do not grant access.
4. Reload a project or prompt to confirm it persists through the API and PostgreSQL.

Verification resend invalidates older links, uses a 60-second account cooldown and permits five attempts per rolling hour for each client/normalized-email hash. Resend/reset responses are generic; duplicate registration explicitly reports an existing account. Missing SMTP produces `503 email_delivery_unavailable` for eligible delivery attempts.

External LLM execution needs your own free-access credentials added through the admin UI. Only Gemini, OpenRouter and Groq are allowed; no paid fallback or extra provider is supported. The internal `mock` adapter is available for deterministic local/test execution only. Simulated provider HTTP success is not real account verification.

## 6. Database, schemas and tables

The application database is **`promptvault`**. Its application relations live in the **`public` schema**; `pg_catalog` and `information_schema` are PostgreSQL system metadata. A database contains schemas; a schema contains tables, views and functions. No separate per-user or per-project schema is created.

The checked-in migration chain currently runs from `001` through `029`. Its SQL is the schema source of truth; use the runner instead of manually pasting selected table definitions. The 19 logical tables below exclude monthly run partitions. Full column types, defaults, keys and indexes are in the [column dictionary](data-dictionary.md); see also the [ER diagram](erd.md) and [3NF explanation](normalization.md).

| Table in `public` | Identity / main relationships | Purpose and important rules |
|---|---|---|
| `users` | UUID `id`; unique case-insensitive email | Display name, Argon2id password hash, `user`/`admin` role, active status and `email_verified_at` |
| `auth_sessions` | UUID `id`; `user_id → users` | JWT session expiry and revocation |
| `email_verification_tokens` | UUID `id`; `user_id → users` | Unique token hash, expiry and one-use state |
| `password_reset_tokens` | UUID `id`; `user_id → users` | Hashed, expiring, one-use password-reset links |
| `password_history` | UUID `id`; `user_id → users` | Password hashes retained for reuse prevention |
| `projects` | UUID `id`; `owner_id → users`; unique key | Owned prompt workspaces |
| `project_members` | Composite PK `(project_id,user_id)` | User/project access; automatic protected owner membership |
| `project_invitations` | UUID `id`; project, recipient and inviter references | Hashed, expiring invitations with acceptance/revocation state |
| `prompts` | UUID `id`; `project_id → projects` | Prompt identity; key unique within its project |
| `prompt_versions` | UUID `id`; prompt, parent version and author references | Immutable body, variables and model config; unique per-prompt version number |
| `runs` | Composite PK `(id,created_at)`; user/project/prompt/version references | Execution ledger, output, usage, latency and exact decimal cost; range-partitioned monthly |
| `run_reservations` | UUID `id`; user/project/prompt/version and optional run references | Idempotent admission and budget reservation; unique user/idempotency key |
| `budgets` | UUID `id`; exactly one user or project target | Nonnegative monthly limits with timezone |
| `model_pricing` | UUID `id`; optional creator reference | Provider/model effective pricing windows with overlap prevention |
| `provider_keys` | UUID `id`; creator reference | Encrypted server-side credentials, alias and active state |
| `api_tokens` | UUID `id`; project and creator/revoker references | Project-scoped Serve credentials; only prefix/hash persist |
| `deployments` | UUID `id`; prompt/version, requester/reviewer and rollback references | Activation, approval and rollback history; one active per prompt/environment |
| `audit_events` | Identity bigint `id`; optional actor reference | Redacted change records and attribution |
| `schema_migrations` | Bigint `version` PK | Applied migration names, SHA-256 checksums and timestamps |

UUIDs identify most entities, `JSONB` stores variables/configuration, `TIMESTAMPTZ` stores instants and `NUMERIC(18,6)` stores monetary values. Foreign keys, unique/check constraints, triggers and transactional functions enforce integrity alongside API validation. Controlled graph deletion has explicit database paths; append-only/immutable records are protected during ordinary writes.

Other database objects:

- Extensions: `pgcrypto`, `citext`, `btree_gist`.
- Enums: `user_role`, `run_status`, `deployment_environment`, `deployment_status`. Deployment environments `dev`/`staging`/`prod` are application workflow labels and do not require hosted environments.
- Views: `prompt_version_lineage`, `deployment_history`, `monthly_costs`.
- Materialized views: `organization_monthly_metrics`, `user_monthly_metrics`; refresh via `.venv/bin/python scripts/refresh-views.py`.
- Run partitions: created by migrations and the partition helper. Before a month boundary run `.venv/bin/python scripts/create-partition.py`.
- Procedure: `perform_system_maintenance`; invoke via `.venv/bin/python scripts/run-maintenance.py` for retention, stale reservations, partitions and analytics refresh.
- Group roles: `promptvault_app` and `promptvault_readonly`. They are database privileges, distinct from account roles `user` and `admin`. Local setup leaves `DATABASE_ROLE` blank; restricted-role checks remain part of the test suite.

Read-only inspection in pgAdmin Query Tool or `psql`:

```sql
SELECT current_database(), current_schema(), inet_server_port();
SELECT version, name, applied_at FROM public.schema_migrations ORDER BY version;
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;
```

The table listing includes physical partitions; it can therefore return more than 19 rows. Never edit, rename or delete applied migration SQL or bypass checksum errors. Add a new numbered migration for a schema change. The runner serializes changes with an advisory lock and commits each migration with its history row. See [migration rules](../db/README.md) for the narrowly supported legacy numbering reconciliation.

## 7. Optional: copy the current website data

Skip this section if an empty/demo database is sufficient. To reproduce Ananya’s current records, first agree on a snapshot and transfer it privately. Stop the app during the handoff so changes after the dump do not create divergent copies. Use PostgreSQL tools compatible with the source server version.

On the source computer (password is prompted):

```bash
pg_dump -h localhost -p 5432 -U promptvault -W -d promptvault \
  --format=custom --no-owner --no-acl --file=/tmp/promptvault-transfer.dump
```

On Jobin’s computer, create a **new empty** `promptvault` database as above. Before running any migrations or seeds there, restore the transferred file:

```bash
pg_restore -h localhost -p 5432 -U promptvault -W -d promptvault \
  --no-owner --no-acl --exit-on-error /tmp/promptvault-transfer.dump
.venv/bin/python scripts/run-migrations.py
```

Do not restore into a database that already contains tables. Do not use `--clean`, drop a used database, reset development data or reseed a restored copy. The dump excludes cluster-wide roles and grants: use the local owner connection with `DATABASE_ROLE` blank, and let any pending migrations create roles they require. A fully migrated dump does not recreate restricted-role grants by itself; use a fresh migration install for restricted-role test databases. Copy the source encryption key privately if retaining encrypted provider keys, and the original `SECRET_KEY` only if deliberately preserving existing JWT compatibility; otherwise sign in again. Keep SMTP credentials specific to Jobin’s chosen setup.

Keep database dumps outside the repository. Compare source/destination migration versions and relevant table counts, log in, inspect the same project/version and test a new email link. Copying a dump does not copy the PostgreSQL server or SMTP inbox.

## 8. Troubleshooting and test isolation

| Symptom | Check / fix |
|---|---|
| Database `OperationalError` | PostgreSQL is running on 5432; credentials/database in root `.env` match pgAdmin; run launcher `--check` |
| Port 5173/8000 occupied | Stop the previous instance or process owning that port; use `lsof -nP -iTCP:5173 -iTCP:8000 -sTCP:LISTEN` on macOS; restart the launcher |
| Frontend loads but API fails | Check `http://localhost:8000/ready`, frontend base URL without `/api/v1`, CORS and backend terminal |
| Email returns 503 | SMTP host/from are set, chosen SMTP server is running, credentials/TLS match; restart API after `.env` edits |
| Email link opens wrong app/port | All three frontend link URLs must use `http://localhost:5173`; request a new message after restarting |
| Verification invalid/expired | Use the newest link within 30 minutes; resend replaces older links and is rate limited |
| Provider decrypt fails after restore | Use the encryption key belonging to that snapshot or replace the provider credentials through the admin flow |
| Migration checksum mismatch | Restore matching migration files from the same code revision; do not alter history or reset the database |

Automated tests must use an explicitly separate database ending in `_test`, never `promptvault`. See [testing](testing.md) for suite-specific setup. Do not run the acceptance harness on the persistent app database or substitute its test ports for normal startup. Avoid `reset-development.py`, `docker compose down -v` and other data resets on a database you want to preserve.
