# Deployment and recovery expectations

The current prototype is intended for local/evaluation environments. The final delivery batch packages the complete web/API/database stack; until then, start PostgreSQL with Docker Compose and run the API locally as documented in the README.

## Durable data

PostgreSQL is the system of record. API restarts are stateless: the connection pool closes during shutdown and a new pool restores access to committed projects, prompt snapshots, deployments, tokens, runs, and audit events. `tests/e2e/test_user_prompt_workflow.py` exercises that restart boundary.

For any environment whose data matters, take a logical or managed PostgreSQL backup before migrations or reset operations. Restore into a separate database first, run migrations, and verify row counts plus the critical Serve/deployment flow before switching traffic. A production deployment should add scheduled backups, retention, encryption, restore drills, and point-in-time recovery according to its PostgreSQL provider.

## Reset boundaries

`python3 scripts/reset-development.py --confirm-reset` is intentionally restricted to the development environment and reconstructs schema, migrations, and seed data. Never point it at a shared or production database. Tests require a dedicated `TEST_DATABASE_URL`; clean verification drops/recreates only that disposable test schema.

The migration runner stores SHA-256 checksums in `schema_migrations`, takes an advisory lock, and applies each file atomically. Applied migration files must not be edited; introduce a later numbered migration instead. Current and next-month run partitions must exist before accepting ledger writes.

## Prototype limitations

TLS termination, edge rate limiting, managed secrets, a dedicated login inheriting `promptvault_app`, automated backups, multi-instance orchestration, and zero-downtime migration strategy are infrastructure responsibilities deferred to production packaging. Race-sensitive version/run/deployment writes have tested function-only grants, while ordinary trusted-server repository CRUD retains direct grants; local Compose currently connects with the development database owner.
