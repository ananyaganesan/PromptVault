# Database

PostgreSQL migrations are applied in numeric order from `migrations/` by `scripts/run-migrations.py`.

## Migration rules

- Filenames use `NNN_lowercase_name.sql`; versions must be unique.
- A migration must not be empty.
- `schema_migrations` records the version, name, SHA-256 checksum, and application time.
- An applied migration must never be edited, renamed, removed, or reordered. Add a new migration instead.
- A PostgreSQL advisory lock prevents two deploys from migrating concurrently.
- Each migration and its tracking row are committed in the same transaction.

The existing SQL files are reserved placeholders for the schema batch. The runner intentionally rejects them while empty.

## Seeds and reset

Seed files live in `seeds/` and should be idempotent. Apply them with `scripts/seed-database.py`. The development reset recreates the `public` schema, migrates, and seeds in one outer transaction:

```bash
python3 scripts/reset-development.py --confirm-reset
```

Reset refuses any `ENVIRONMENT` other than `development` and refuses to run without explicit confirmation. Use `--database-url` only when the target has been independently verified.
