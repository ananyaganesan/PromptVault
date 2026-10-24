# PromptVault

**PromptVault is a local prompt management website for creating immutable prompt versions, testing them with LLMs, and promoting approved versions for application use.** It combines a React interface, FastAPI backend and PostgreSQL database with project access controls, execution tracking, deployment approvals and a token-protected Serve API.

## Contents

1. [Project Name](#promptvault)
2. [Project Overview](#project-overview)
3. [Problem Statement](#problem-statement)
4. [Key Features](#key-features)
5. [Tech Stack](#tech-stack)
6. [System Architecture](#system-architecture)
7. [Project Structure](#project-structure)
8. [Prerequisites](#prerequisites)
9. [Installation & Setup](#installation--setup)
10. [Environment Variables](#environment-variables)
11. [Running the Project](#running-the-project)
12. [Database Setup](#database-setup)
13. [API Documentation](#api-documentation)
14. [User Workflow](#user-workflow)
15. [Testing](#testing)
16. [Development Workflow](#development-workflow)
17. [Team & Contributions](#team--contributions)

## Project Overview

PromptVault keeps a prompt's content, configuration, history and release decisions together. Teams can compare versions, test saved configurations, review production promotions and let another application fetch the currently approved prompt without embedding prompt text in application code.

The project is intended for **local development and demonstration**. You can run the frontend and API natively or in Docker Desktop. Both normal startup methods reuse the persistent PostgreSQL database on `localhost:5432/promptvault`, also visible in pgAdmin.

| Component | Local address |
|---|---|
| Website | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Interactive API documentation | http://localhost:8000/docs |
| API readiness | http://localhost:8000/ready |
| PostgreSQL | `localhost:5432/promptvault` |

For a fresh-machine walkthrough, start with [Jobin’s local setup and database reference](docs/jobin-local-setup.md). For containers, see [Docker local deployment](docs/docker-local.md).

## Problem Statement

Prompts stored in chat histories, documents or application source files are difficult to track and reuse. A team can lose the connection between a tested prompt, its model settings and the version an application actually uses. Uncontrolled edits also make failures, costs and release decisions difficult to explain.

PromptVault addresses this by storing immutable versions, recording execution results and separating editing from approval and activation. Project membership controls access, while release history and audit records explain how the current configuration was selected.

## Key Features

| Area | Functionality |
|---|---|
| Authentication | Registration, email verification, login/logout, password reset, session revocation and self-profile updates |
| Projects | Super Admin project creation; ownership, scoped membership and recipient-accepted email invitations |
| Prompt versioning | Immutable numbered snapshots, template variables, saved model settings, commit messages, comparisons and ancestry |
| Playground | Select a project first, then one of its prompt versions; supply variables and execute the saved configuration |
| Execution records | Persisted output, status, token usage, latency, recorded cost and idempotent admission/results |
| Prompt deployments | Development/staging activation, production approval or rejection, history and rollback with a reason |
| Serve API | Fetch the active prompt using an expiring/revocable project-scoped token; plaintext tokens are disclosed once |
| Administration | Account access management, encrypted provider credentials, budgets, pricing, redacted audit records and maintenance |
| Database integrity | Normalized relations, foreign keys, constraints, immutable records, partitioned run history and transactional concurrency controls |
| Local operation | Fixed ports, data-preserving startup, Docker support, native backup/restore and isolated automated tests |

Account roles are stored as `user` and `admin`; the interface calls an administrator **Super Admin**. Members work within accessible projects, owners manage project access, and Super Admins perform administration and production reviews. The backend enforces these permissions on every request.

Execution is restricted to **Gemini only in every environment**, using verified free-access configurations. There is no other provider, local mock adapter or paid fallback. Automated tests simulate Gemini HTTP without adding a selectable runtime provider; simulation does not establish real free-tier account execution; use `.venv/bin/python scripts/verify-real-providers.py --help` for the guarded verification command.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript 6, Vite 8, React Router 7, Tailwind CSS 4 and Lucide icons |
| Backend | Python 3.11+, FastAPI, Pydantic settings/validation and Uvicorn |
| Persistence | SQLAlchemy 2 async ORM with psycopg; ordered, checksummed SQL migrations |
| Database | PostgreSQL 16+; native local server currently PostgreSQL 18 |
| Database features | `pgcrypto`, `citext`, `btree_gist`, PL/pgSQL functions/procedure, triggers, views, materialized views and range partitions |
| Authentication/security | Argon2id password hashes, JWTs backed by revocable sessions, hashed one-use links and encrypted provider keys |
| LLM adapters | Gemini only; free-access configuration with no fallback |
| Email | SMTP for verification, password resets, password-change notifications and project invitations |
| Containers | Docker Compose, Python runtime image and unprivileged nginx frontend image |
| Verification | pytest/coverage, Ruff, mypy, Vitest, Testing Library, ESLint, TypeScript and Playwright |
| CI | GitHub Actions for frontend checks, API checks and isolated Docker verification |

Exact JavaScript dependencies are pinned in [web/package-lock.json](web/package-lock.json). Python runtime and development versions are pinned in [api/requirements.lock](api/requirements.lock) and [api/requirements-dev.lock](api/requirements-dev.lock).

## System Architecture

```text
Browser / React :5173
        |
        | JSON HTTP + user Bearer JWT
        v
FastAPI :8000
  Routers -> authentication/authorization -> services -> repositories
                                                    |       |
                                                    |       +-> SQLAlchemy async session
                                                    |                     |
                                                    |                     v
                                                    |              PostgreSQL :5432
                                                    |              persistent promptvault DB
                                                    |
                                                    +-> Gemini
                                                    +-> SMTP server

External application -> project-scoped Serve token -> /serve/v1/prompts/{key}
```

Services orchestrate business transactions. Repositories use mapped ORM entities for ordinary persistence. PostgreSQL procedures/functions retain advanced operations such as version allocation, budget admission, deployment decisions and guarded deletion; recursive and snapshot-consistent analytical queries retain explicit SQL.

In native mode, Vite and Uvicorn run on the host. In normal Docker mode, nginx and FastAPI run in containers and connect to the same host database through `host.docker.internal:5432`. A one-shot migration container completes before the API starts. Email links return to the frontend on port 5173.

The deployment labels `dev`, `staging` and `prod` describe **prompt release environments** inside the application. They do not require separate hosted websites. See the [database relationships](docs/erd.md) for the relational design.

## Project Structure

```text
PromptVault/
├── api/
│   ├── app/
│   │   ├── db/                  ORM models, sessions, migrations and transactions
│   │   ├── dependencies/        Authentication and authorization dependencies
│   │   ├── providers/           Fixed-scope LLM adapters and policies
│   │   ├── repositories/        Database persistence and queries
│   │   ├── routers/             HTTP endpoints
│   │   ├── schemas/             Request/response validation
│   │   └── services/            Business workflows
│   ├── tests/                   API unit and integration tests
│   ├── Dockerfile
│   └── requirements*.{txt,lock}
├── web/
│   ├── src/                     React application, features and UI tests
│   ├── e2e/                     Playwright browser checks
│   └── package.json
├── db/
│   ├── migrations/              Ordered SQL schema changes
│   ├── seeds/                   Explicit development fixtures
│   └── showcase/                SQL demonstrations and query plans
├── scripts/                     Startup, migrations, backup, maintenance and checks
├── tests/                       Database, security, concurrency and delivery tests
├── docker/                      nginx, frontend image and isolated DB initialization
├── docs/                        Essential local setup, database and API references
├── evidence/                    Generated verification output (ignored by Git)
├── examples/                    Example templates and Serve consumer
├── .github/workflows/ci.yml     Automated checks
├── docker-compose.yml           Isolated database/application stack
├── docker-compose.local.yml     Normal Docker override: reuse host PostgreSQL
├── .env.example                 Backend/Compose configuration template
├── AGENTS.md                    Project constraints for coding agents
└── README.md
```

Local `.env` files and `secrets/` are ignored by Git. Database dumps are retained privately under `secrets/backups/`.

## Prerequisites

| Requirement | Version / purpose |
|---|---|
| Git | Clone the repository and work with team branches |
| Python | 3.11 or newer; current host checks also run on 3.12 |
| Node.js and npm | Node 22.12+ and its compatible npm; install dependencies with `npm ci` |
| PostgreSQL | 16+ on port 5432, with `psql`, `pg_dump` and `pg_restore` |
| Database privileges | Database ownership, extension installation and role creation for initial migrations |
| Docker Desktop / Compose | Required for container startup; optional for native app startup |
| pgAdmin | Optional graphical client for the same local database |
| SMTP account or local inbox | Required for new-account verification, resets and invitation delivery |

The commands below assume a macOS/Linux shell and execution from the repository root. When transferring the existing PostgreSQL 18 database, use compatible PostgreSQL tools and a compatible destination server; do not restore its dump into an older PostgreSQL 16 server. Fresh migrations are tested separately on PostgreSQL 16.

## Installation & Setup

### 1. Clone and select your branch

```bash
git clone https://github.com/ananyaganesan/PromptVault.git
cd PromptVault
git fetch origin
git switch Ananya
```

Use `Jobin` instead for that contributor’s work, or the agreed review branch. Reproduce the same commit when comparing results across machines. Repository access may require your own GitHub credentials.

### 2. Install dependencies

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements-dev.lock
npm ci --prefix web
```

### 3. Create local configuration

On a fresh checkout, copy the examples without overwriting existing files:

```bash
cp -n .env.example .env
cp -n web/.env.example web/.env.local
```

Edit the settings described below. Generate **two separate values**, running this command once for each secret, and put them in `SECRET_KEY` and `PROVIDER_ENCRYPTION_KEY`:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Preserve existing secret values when using an existing database. Its original encryption key is necessary to decrypt stored provider credentials.

### 4. Prepare the database and email

Follow [Database Setup](#database-setup) to create a fresh database once and apply migrations. Configure a local SMTP inbox or your own SMTP account using [Jobin’s email setup](docs/jobin-local-setup.md#4-configure-email-before-registering).

For Gmail, the interactive helper stores an App Password privately:

```bash
.venv/bin/python scripts/configure-smtp.py
```

Then choose native or Docker startup under [Running the Project](#running-the-project).

## Environment Variables

Root `.env` supplies backend and Compose settings. `web/.env.local` supplies Vite settings for native development. The full template is [.env.example](.env.example); the table below covers connection settings, secrets and the main operational controls.

| Variable(s) | Purpose / local value |
|---|---|
| `ENVIRONMENT` | `development` for normal local use; `test` for isolated automated checks |
| `DATABASE_URL` | Persistent host DSN: `postgresql://promptvault:<password>@localhost:5432/promptvault` |
| `DATABASE_ROLE` | Leave blank for the documented local setup; optional restricted role is `promptvault_app` |
| `TEST_DATABASE_URL` | Separate disposable database whose name ends in `_test`; never the application database |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose connection values; must match the persistent database for the local override |
| `POSTGRES_PORT` | `5432` for normal local PostgreSQL; isolated stacks use a different port |
| `API_PORT`, `WEB_PORT` | Normal application ports: `8000`, `5173`; the native launcher fixes these ports |
| `SECRET_KEY` | Private JWT signing secret; replace example value and keep stable |
| `PROVIDER_ENCRYPTION_KEY` | Separate private key used to encrypt provider credentials; retain it with database transfers |
| `CORS_ORIGINS` | Comma-separated browser origins, e.g. `http://localhost:5173,http://127.0.0.1:5173` |
| `ACCESS_TOKEN_TTL_MINUTES`, `JWT_ISSUER`, `JWT_AUDIENCE` | User-session token lifetime and validation settings |
| `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, `DB_POOL_TIMEOUT_SECONDS` | Database pool configuration; maximum size and checkout timeout bound concurrent access |
| `PROVIDER_TIMEOUT_SECONDS`, `MAX_CONCURRENT_RUNS_PER_USER` | Provider request timeout and execution concurrency limit |
| `GEMINI_API_BASE_URL` | Gemini endpoint; retain the example default for real execution |
| `MAX_REQUEST_BODY_BYTES` | Request size cap; default 1 MiB |
| `AUTH_RATE_LIMIT_*`, `PASSWORD_RESET_RATE_LIMIT_*` | Authentication/reset request limits and time windows |
| `EMAIL_VERIFICATION_URL` | `http://localhost:5173/verify-email` |
| `EMAIL_VERIFICATION_TTL_MINUTES` | Verification lifetime; `30` |
| `EMAIL_VERIFICATION_RESEND_*` | Account cooldown and resend limits; defaults 60 seconds and five attempts/hour |
| `PASSWORD_RESET_URL`, `PASSWORD_RESET_TTL_MINUTES` | Frontend reset page and token lifetime; local URL ends in `/reset-password` |
| `PROJECT_INVITATION_URL` | `http://localhost:5173/project-invitations` |
| `SMTP_HOST`, `SMTP_PORT` | Mail server and port; Gmail commonly uses 587 with STARTTLS; local capture uses 1025 |
| `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | SMTP credentials and sender; Gmail requires an App Password |
| `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_TIMEOUT_SECONDS` | Transport mode and timeout; use STARTTLS or implicit SSL as appropriate |
| `LOG_LEVEL` | `INFO` by default |
| `VITE_API_URL` | Root Compose web build argument: `http://localhost:8000` |
| `VITE_API_BASE_URL` | Native `web/.env.local` API origin: `http://localhost:8000`; omit `/api/v1` |
| `VITE_USE_DEMO_DATA` | `false` for the connected local application |

Provider API keys are added through **Super Admin → Provider keys** and stored encrypted in PostgreSQL. Frontend `VITE_*` variables are public build configuration and must never contain SMTP passwords, JWT secrets or provider keys.

For a native Mailpit inbox, use `SMTP_HOST=127.0.0.1`, port `1025`, no credentials and both TLS flags false; open the inbox on `http://localhost:8025`. For an API container connecting to host Mailpit, use `SMTP_HOST=host.docker.internal`. Keep verification/reset/invitation links on frontend port **5173**, not the SMTP or API port.

## Running the Project

### Option A: native frontend and backend

Keep PostgreSQL running on port 5432, then run:

```bash
.venv/bin/python scripts/start-local.py
```

The launcher validates the persistent connection, applies pending checksum-validated migrations and starts Uvicorn on 8000 and Vite on 5173. It refuses occupied ports and does not seed or reset data. Leave the terminal open; Ctrl-C stops both app processes and leaves PostgreSQL running.

To check the database without starting the application:

```bash
.venv/bin/python scripts/start-local.py --check
```

### Option B: Docker frontend and backend with the same database

Stop the native app first. Start Docker Desktop, keep native PostgreSQL running, and verify that root `POSTGRES_*` values match `DATABASE_URL`.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

This override uses the host database, runs migrations without seeding and binds the app to loopback ports 5173/8000. The base Compose file alone includes its own database and development seeds; use the override for your existing local data.

Inspect or stop the app with:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=100 api migrate
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

After changing root environment settings, rerun `up -d --build --wait` to recreate affected containers. The compiled web API URL needs a rebuild. See [Docker local deployment](docs/docker-local.md) for details.

### Check the running services

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/ready
curl --fail --output /dev/null http://localhost:5173/login
```

Open http://localhost:5173. Normal native and Docker startup use the same ports; run one mode at a time.

## Database Setup

### Create a fresh database once

Connect as a PostgreSQL administrator through `psql` or pgAdmin. With autocommit enabled, run these statements separately **only when the role/database do not already exist**:

```sql
CREATE ROLE promptvault WITH LOGIN PASSWORD 'promptvault' CREATEROLE;
CREATE DATABASE promptvault OWNER promptvault;
```

The password above is a local example; match your own `.env` values. The migration login must be able to install `pgcrypto`, `citext` and `btree_gist` and create the application group roles. Never recreate an existing database to match the example.

Apply ordered migrations:

```bash
.venv/bin/python scripts/run-migrations.py
```

The current chain is **001–031**. Migrations use `NNN_lowercase_name.sql` filenames and record SHA-256 checksums in `schema_migrations`; applied SQL must not be edited, renamed or removed. An advisory lock serializes migration runners, and each migration/history row commits atomically. The runner supports the historical 011/015 password-reset numbering collision only when the recorded checksum matches migration 015 and the reset table exists; all other mismatches stop migration. Normal startup applies only outstanding migrations. ORM `create_all` is not used.

### Schema and relations

Application objects live in PostgreSQL’s **`public` schema**. There are **24 logical tables**; physical monthly run partitions and views are counted separately.

| Domain | Tables |
|---|---|
| Accounts and authentication | `users`, `auth_sessions`, `email_verification_tokens`, `password_reset_tokens`, `password_history` |
| Project access | `projects`, `project_members`, `project_invitations` |
| Prompts and versions | `prompts`, `prompt_versions`, `prompt_version_parents`, `prompt_version_variables` |
| Execution and budgets | `runs`, `run_inputs`, `run_reservations`, `reservation_results`, `spend_limits` |
| Deployments and runtime access | `deployments`, `deployment_rollbacks`, `api_tokens` |
| Administration and infrastructure | `provider_keys`, `model_pricing`, `audit_events`, `schema_migrations` |

Revision 030 stores atomic configuration/input values and derives repeated scope through joins. `version_context`, `run_context`, `reservation_context` and `deployment_context` reconstruct API representations. Additional views provide lineage, release history and monthly costs; materialized views cache metrics. Primary/foreign keys, checks, unique constraints, indexes, triggers and transactional routines enforce integrity.

See the [ER diagram and relational mapping](docs/erd.md), [3NF analysis](docs/normalization.md), [column dictionary](docs/data-dictionary.md).

### Optional development seeds

For a **new, empty development database only**:

```bash
.venv/bin/python scripts/seed-database.py
```

| Seeded role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

These are public development fixtures, not the credentials of an existing installation. Seed SQL can update fixture identities/passwords, so skip it for restored or already-used databases. New registrations require email verification; migrated/seeded accounts are verified.

### Backup and restore verification

```bash
.venv/bin/python scripts/backup-local.py --admin-url postgresql://postgres@localhost:5432/postgres
```

Use your administrator DSN and `.pgpass`. The script creates a private native `pg_dump` archive, restores it into an isolated temporary `_test` database, checks every logical table count and removes the temporary database. It leaves the source database intact. Keep the dump and original provider encryption key private when transferring data. The script writes a fresh verification report under `evidence/database/`; generated reports are not required inputs.

## API Documentation

| Reference | Location |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Runtime OpenAPI JSON | http://localhost:8000/openapi.json |
| Checked-in OpenAPI | [docs/openapi.json](docs/openapi.json) |

Application routes use `/api/v1`. Requests/responses use JSON, UUID strings, UTC timestamps and decimal strings for money. Protected application endpoints require `Authorization: Bearer <access_token>`. JWTs are checked against current account/session state. Runtime Serve credentials are separate project-scoped tokens.

Representative endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register an account and request verification |
| `POST` | `/api/v1/auth/email-verification/confirm` | Consume the verification link |
| `POST` | `/api/v1/auth/login` | Create an authenticated session |
| `POST` | `/api/v1/auth/logout` | Revoke the current session |
| `GET`, `POST` | `/api/v1/projects` | List accessible projects; create as Super Admin |
| `GET`, `PATCH`, `DELETE` | `/api/v1/projects/{project_id}` | Scoped details, authorized edits and guarded deletion |
| `GET`, `POST` | `/api/v1/projects/{project_id}/prompts` | List/create project prompts |
| `GET`, `POST` | `/api/v1/prompts/{prompt_id}/versions` | Read history or create an immutable version |
| `GET` | `/api/v1/versions/{version_id}/diff?against={other_id}` | Compare same-prompt versions |
| `GET` | `/api/v1/versions/{version_id}/lineage` | Read ancestry |
| `GET` | `/api/v1/providers/models` | Discover the fixed provider catalog and availability |
| `POST` | `/api/v1/runs` | Execute a saved version with input variables |
| `GET`, `POST` | `/api/v1/deployments` | Read release records or request a deployment |
| `GET`, `POST` | `/api/v1/api-tokens` | Manage authorized project-scoped runtime tokens |
| `GET` | `/serve/v1/prompts/{key}?env=prod` | Fetch the active prompt using a Serve token |

For example, log in using an existing verified account:

```bash
curl --request POST http://localhost:8000/api/v1/auth/login \
  --header 'Content-Type: application/json' \
  --data '{"email":"user@promptvault.dev","password":"UserDemo2026!"}'
```

The sample credentials work only on an explicitly seeded development database. Login returns an access token and user/session information. Use your own token in subsequent requests, such as a run body:

```json
{
  "version_id": "<saved-version-uuid>",
  "variables": {
    "customer_name": "Priya"
  }
}
```

The variable names must match the selected version. A run response includes its ID, status, output, usage, latency and recorded cost. Errors use `code`, `message`, optional `field_errors` and `request_id`; authorization, conflicts and validation retain distinct HTTP statuses. Swagger documents the complete request/response schemas and permissions.

## User Workflow

1. **Register and verify:** create an account, open its emailed verification link and sign in. Verification links expire after 30 minutes and can be used once.
2. **Receive project access:** a Super Admin creates the project; the owner invites an existing account. The recipient accepts while signed in. A pending invitation grants no access.
3. **Create a prompt:** save a template, its variable declarations and an allowed provider/model configuration.
4. **Version changes:** each save creates another immutable snapshot with a commit message. Compare versions and inspect ancestry.
5. **Test in Playground:** choose the project, select one of its versions, enter variable values and execute. Execution requires a configured free-access Gemini credential. Historical versions from removed providers must be saved as new Gemini versions before running.
6. **Promote a version:** activate in development/staging, or submit a production request for Super Admin review. Prompt activation changes the version served for that environment.
7. **Consume the prompt:** create a project-scoped Serve token, retain its one-time plaintext value privately and fetch the active version from another application.
8. **Review and recover:** inspect deployment history, audit and usage records; perform an authorized rollback with a reason when required. Revoke runtime tokens when no longer needed.

To prepare sample Gemini project/template metadata without provider calls, mail or release changes, run `.venv/bin/python scripts/prepare-demo.py` with an existing active administrator.

## Testing

Run commands from the repository root. Database tests can recreate fixture schemas and require an **isolated `_test` database**. They must never point at `promptvault`.

### Backend unit, integration, security and database checks

Create `promptvault_test` once using your PostgreSQL administrator (only if it does not exist):

```sql
CREATE DATABASE promptvault_test OWNER postgres;
```

The example below uses the local administrator `postgres`; substitute your own test runner where needed. Configure its password privately in `.pgpass` with an entry covering `promptvault_test`. The runner needs database creation and role-management privileges for migration-upgrade checks; the ordinary application login may not have them. Set both URLs explicitly so no test command inherits the application DSN:

```bash
export ENVIRONMENT=test
export DATABASE_URL=postgresql://postgres@localhost:5432/promptvault_test
export TEST_DATABASE_URL="$DATABASE_URL"
export SECRET_KEY=test-secret-that-is-at-least-32-characters
export PROVIDER_ENCRYPTION_KEY=test-provider-encryption-key
export PGOPTIONS='-c timezone=UTC'
export SMTP_HOST= SMTP_USERNAME= SMTP_PASSWORD= SMTP_FROM_EMAIL=

.venv/bin/ruff check api scripts tests
.venv/bin/mypy --config-file api/pyproject.toml api/app
.venv/bin/python -m pytest -q --cov=api.app --cov-config=api/pyproject.toml
.venv/bin/python -m pip check
```

Use a separate test terminal; close it before normal app startup to avoid carrying exported test settings into the application. Migration-upgrade tests also require permission to create/drop temporary test databases. The suite covers authorization, email flows with isolated capture/mocks, immutable history, provider restrictions, budgets, idempotency, races, migration preservation and query plans. Coverage must meet the configured 85% threshold.

### Frontend checks

```bash
npm run lint --prefix web
npm run typecheck --prefix web
npm test --prefix web
npm run build --prefix web
```

### Browser checks

Playwright checks can mutate application data. Use a separate seeded `_test` application stack with known test credentials and SMTP capture where email flows require it. Use `tests/tools/gemini_http_simulation.py` against a disposable database to simulate Gemini HTTP; this test tool is separate from the normal application. Against that isolated simulator, supply its frontend/API addresses:

```bash
E2E_LIVE=1 \
E2E_PROVIDER_SIMULATION=1 \
E2E_BASE_URL=http://127.0.0.1:5177 \
E2E_API_BASE_URL=http://127.0.0.1:8004/api/v1 \
npm --prefix web run test:e2e -- e2e/live-docker-normalization.spec.ts \
  --project=desktop-chrome --project=mobile-chrome
```

Those are example isolated test ports, not normal startup ports. The selected projects use installed Google Chrome; other browser projects require their Playwright browser installations. The simulator requires `E2E_DATABASE_URL` ending in `_test`; email browser flows also require the local capture harness in `scripts/run-local-auth-acceptance.py`.

### OpenAPI contract drift

```bash
.venv/bin/python scripts/export-openapi.py --output /tmp/promptvault-openapi.json
diff -u docs/openapi.json /tmp/promptvault-openapi.json
```

GitHub Actions runs frontend, API and Docker verification jobs on pushes and pull requests. Local results do not imply that a hosted GitHub check has run; inspect the workflow status for the relevant commit.

## Development Workflow

The current contributor branches are **`Ananya`** and **`Jobin`**, with **`main`** as the shared integration target. Agree on the target branch before starting a shared change; do not assume an additional `dev` branch exists.

1. Fetch remote changes and check your working tree before switching branches. Preserve uncommitted work.
2. Work on your contributor branch or a focused feature branch based on the agreed target.
3. Keep changes scoped. Describe user-visible behavior and the reason for the change in the commit message; do not include secrets or private dumps.
4. Run checks relevant to the change. Backend/schema changes need isolated database tests; UI changes need lint/type checks and relevant UI/browser checks.
5. Regenerate OpenAPI for API schema changes. Update ER/relational design and normalization documentation before a new database change, then add a new migration and evidence.
6. Push your branch and open a pull request against the agreed integration target. Explain the change, validation and any remaining limitations; review CI before merging.

Example for a feature branch after your working tree is ready:

```bash
git fetch origin
git switch Ananya
git pull --ff-only origin Ananya
git switch -c feature/describe-the-change
```

Python changes follow Ruff and mypy; frontend changes follow ESLint and TypeScript. Keep HTTP routes, services and repositories separated. Authorization must be enforced by the backend, and advanced concurrency/data-integrity rules must remain transactional. Do not edit applied migrations, broaden the fixed provider allowlist or introduce paid fallback execution. Follow [AGENTS.md](AGENTS.md) when using a coding agent.

## Team & Contributions

| Contributor | Collaboration area |
|---|---|
| **Ananya Ganesan** — `Ananya` branch | Application workflows, frontend integration, local demonstration and shared acceptance review |
| **Jobin** — `Jobin` branch | Database design, relational schema, migrations, SQL evidence and backend integration |
| **Shared ownership** | Cross-layer API contracts, security/data integrity, integration testing, documentation and pull-request review |

The ownership areas summarize the current collaboration and database acceptance responsibilities; they do not prevent either contributor from improving another layer. Use [Jobin’s setup guide](docs/jobin-local-setup.md) to reproduce the same application and the [relational mapping](docs/erd.md) for schema ownership.

Contributions should include the problem being solved, focused implementation changes, relevant verification and updated documentation. Discuss changes to authorization, database invariants or project scope before broadening them. Keep credentials, SMTP messages containing authentication links and real database exports private. Existing accounts and project data must be preserved during ordinary startup and upgrades.

The repository’s license is recorded in [LICENSE](LICENSE).
