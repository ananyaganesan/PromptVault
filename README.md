# PromptVault

PromptVault is a local prompt versioning and execution website built with React/Vite, FastAPI and PostgreSQL. It includes verified-email authentication, projects and invitations, immutable prompt versions, execution history, deployment approvals, project-scoped Serve tokens and administration.

**Jobin: follow [the local setup and database guide](docs/jobin-local-setup.md)** for a fresh-machine installation, the schema/table reference, SMTP, copying existing data and troubleshooting.

## Run locally

After the one-time setup in the guide, start from the repository root:

```bash
.venv/bin/python scripts/start-local.py
```

| Component | Address |
|---|---|
| Website | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |
| PostgreSQL / pgAdmin connection | localhost:5432, database `promptvault` |

The launcher applies pending checksum-validated migrations, preserves existing data and refuses busy app ports. It never resets or seeds the database automatically. Ctrl-C stops the frontend/backend and leaves PostgreSQL running. Check the database connection alone with `--check`.

Do not start a second PostgreSQL container on port 5432. Normal startup uses the existing server and root `.env`; isolated `_test` databases are for automated tests.

## Local demo accounts

These accounts exist only after explicitly seeding a **new, empty** development database:

| Role | Email | Password |
|---|---|---|
| User | `user@promptvault.dev` | `UserDemo2026!` |
| Super Admin | `admin@promptvault.dev` | `AdminDemo2026!` |

Do not reseed an existing database to obtain these accounts: seed SQL can overwrite fixture identities and password hashes. New registrations must follow their emailed verification link before login. Verification, password reset and project invitations require backend SMTP configuration; the setup guide includes a local inbox.

## Providers

External execution is restricted to **Gemini, OpenRouter and Groq**, using verified free-access configurations only. There is no paid fallback. `mock` is an internal deterministic development/test adapter and is rejected in production. OpenRouter/Groq adapter HTTP simulation is covered; real account execution requires separate validation with free-tier credentials. See [provider verification](docs/real-provider-verification.md).

## Documentation

Start with [your prepared demo and complete walkthrough](docs/demo-walkthrough.md) for the sample projects, presentation steps and system explanation.

- [Jobin’s local setup, database, schemas and tables](docs/jobin-local-setup.md)
- [Column dictionary](docs/data-dictionary.md), [entity relationships](docs/erd.md) and [normalization](docs/normalization.md)
- [Database migration rules](db/README.md) and [academic database requirements](docs/database-design-requirements.md)
- [Architecture](docs/architecture.md), [API contract](docs/api-contracts.md), [OpenAPI](docs/openapi.json) and [API examples](docs/api-examples.md)
- [Authorization](docs/authorization-matrix.md), [security](docs/security.md) and [data lifecycle](docs/data-lifecycle.md)
- [Testing](docs/testing.md), [demo walkthrough](docs/demo-runbook.md) and [local integration acceptance](docs/jobin-integration-acceptance.md)

Current contracts, database references and acceptance evidence are retained. Superseded phase plans, the old contract decision log and public-hosting instructions have been removed. This project is for local use and demonstration; a public domain or hosted deployment is not required.

## Repository

```text
api/        FastAPI routes, services, providers and backend tests
web/        React/Vite frontend and browser tests
db/         Ordered SQL migrations, seeds and queries
scripts/    Local startup, migrations, maintenance and verification
tests/      Database, security, concurrency, delivery and end-to-end tests
docs/       Current reference documentation and local acceptance records
evidence/   Recorded verification artifacts
```
