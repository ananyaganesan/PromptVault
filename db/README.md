# Database

PostgreSQL migrations are applied in numeric order from `migrations/` by `scripts/run-migrations.py`.

## Migration rules

- Filenames use `NNN_lowercase_name.sql`; versions must be unique.
- A migration must not be empty.
- `schema_migrations` records the version, name, SHA-256 checksum, and application time.
- An applied migration must never be edited, renamed, removed, or reordered. Add a new migration instead.
- A PostgreSQL advisory lock prevents two deploys from migrating concurrently.
- Each migration and its tracking row are committed in the same transaction.

The migration chain currently covers extensions/enums, normalized tables, constraints/indexes, monthly run partitions, immutable/audit triggers, concurrency-sensitive functions, views, materialized aggregates, roles/grants, and baseline model pricing.

## Seeds and reset

Seed files live in `seeds/`, use numeric prefixes, and are idempotent. `001_development.sql` creates the two demo identities; `002_demo.sql` creates a project, membership, prompt/version, and budget. Apply them with `scripts/seed-database.py`. The development reset recreates the `public` schema, migrates, and seeds in one outer transaction:

```bash
python3 scripts/reset-development.py --confirm-reset
```

Reset refuses any `ENVIRONMENT` other than `development` and refuses to run without explicit confirmation. Use `--database-url` only when the target has been independently verified.
