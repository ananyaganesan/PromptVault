# PromptVault on Supabase PostgreSQL

The existing local database was copied into the free PromptVault Supabase project
on 2026-10-31. An automatic one-way worker now reconciles committed local data
changes to Supabase every 10 seconds while this Mac is awake, logged in, and online.
Local PostgreSQL remains the source of truth and the application's database.

- Project: `ehnufhcdgxllubnpjfuc`
- [Open the database tables](https://supabase.com/dashboard/project/ehnufhcdgxllubnpjfuc/editor)
- Target PostgreSQL: 17.11; source PostgreSQL: 18.4.
- 28 logical tables, plus two run partitions: 30 table-content hashes verified.
- All 45 application migration records and checksums preserved.
- Four existing application accounts preserved, with their password hashes and
  authentication records unchanged.

PromptVault continues to own authentication. Its accounts are in `public.users`;
they are separate from Supabase Auth accounts.

## Access and integrity

The imported database retains the source functions, indexes, constraints, triggers,
and backend/read-only grants. Extension grants use the routines actually present
in the destination's `citext` and `btree_gist` versions. Supabase's existing
`pgcrypto` extension stays in its managed `extensions` schema.

All imported tables, including partitions, have row-level security enabled with
policies for the existing `promptvault_app` and `promptvault_readonly` roles. SQL
grants still control which operations those roles may perform. The `anon`,
`authenticated`, and `service_role` roles have no access to the public schema,
its tables, or application functions. New public objects do not automatically
grant those API roles access. Browser clients must use the PromptVault backend.

The three Gemini provider checks remain `NOT VALID`, matching the source. This
preserves immutable historical provider metadata while enforcing Gemini-only
checks on new rows. The execution and activation guard triggers are preserved.

## Connecting a backend

The database import does not switch the local application to Supabase. Keep the
root `.env` and `scripts/start-local.py` on `localhost:5432/promptvault`.

For a backend intended to use this hosted copy, configure its separate environment:

```dotenv
DATABASE_URL=<Supabase direct or Session pooler PostgreSQL URI with SSL>
DATABASE_ROLE=promptvault_app
DB_POOL_MIN_SIZE=0
DB_POOL_MAX_SIZE=2
```

Obtain the URI from Supabase **Connect → Direct → Session pooler**, using port
5432 and SSL (`sslmode=require` or a certificate-verified configuration). Use a
direct or session connection for migrations and the current backend's session
settings. The migration administrator must be able to set `promptvault_app`.

Keep database credentials in private environment settings, never frontend build
variables. To decrypt the copied Gemini credential, preserve the source
`PROVIDER_ENCRYPTION_KEY`; if the source used the `SECRET_KEY` encryption fallback,
use that same effective encryption key. A new random encryption key cannot
decrypt existing provider credentials. Preserve the JWT signing configuration if
existing sessions should remain usable.

## Automatic local-to-Supabase synchronization

The installed macOS LaunchAgent is
`~/Library/LaunchAgents/com.promptvault.supabase-sync.plist`. It starts at login
and runs independently of the web/API launcher. Each run uses a read-only,
repeatable-read snapshot of `localhost:5432/promptvault`, checks the destination's
schema and migration history, and compares table-content hashes. It sends only
changed rows and copies inserts, updates, and deletions in one destination
transaction. It also carries forward identity sequences and creates missing
run-style partitions with row-level security enabled.

The destination session suppresses application and foreign-key triggers only
within the mirror transaction, then restores normal trigger execution. This
preserves the source audit/authentication records without creating duplicate audit
events or rejecting an authorized source-side graph deletion. The full destination
table hashes must match the committed source snapshot before commit. Normal
application writes retain their original triggers, Gemini restrictions, grants,
and row-level security. Sequence values are never rewound; rollback can leave
ordinary PostgreSQL sequence gaps.

Supabase is a mirror: write application data locally. If an independent edit is
detected in the destination, the worker pauses instead of discarding it. New
application schema migrations must be applied to both databases before data sync
continues; the worker does not guess how to transform mismatched schemas. Offline
or failed runs leave local data untouched and retry on the next scheduled run.
After sleep or an outage, the next successful run catches up to a fresh snapshot.

Credentials are read from the ignored, private `secrets/supabase.env` file:

```dotenv
SUPABASE_DATABASE_URL=<this project's Session pooler URI with sslmode=require>
```

The URI must name the PromptVault project and port 5432. The normal root `.env`
continues to point at the local database. Credentials and row contents are not
included in sync status or error logs. Fingerprints and crash recovery checkpoints
are retained privately in `secrets/supabase-sync/state.json`.

```bash
# Show the last successful run, any error, and row-change counts.
.venv/bin/python scripts/sync-supabase.py --status

# Reconcile once now, including content verification.
.venv/bin/python scripts/sync-supabase.py

# Stop automatic sync and prevent it from restarting at login.
.venv/bin/python scripts/sync-supabase.py --stop-agent

# Verify a real sync and reinstall the repeating job.
.venv/bin/python scripts/sync-supabase.py --install-agent
```

The job's summary and error logs are in `secrets/supabase-sync/`. Its process
normally exits successfully between runs; launchd schedules the next run. A local
file lock and destination advisory lock prevent overlapping workers. Durable
pending checkpoints allow recovery if a process stops after the destination
commit but before the final local checkpoint is written.

Validation: `tests/delivery/test_supabase_sync.py` uses disposable source and
destination databases to cover CRUD, exact JSON/numeric/binary values, cascade
relationships, audit preservation, uncommitted source transactions, destination
conflicts, failed-transaction rollback, schema/migration drift, interrupted
checkpoint recovery, and partition creation. Run alongside the existing local
startup checks:

```bash
.venv/bin/python -m pytest -q tests/delivery/test_supabase_sync.py tests/delivery/test_local_startup.py
```

## Verification artifacts

- Private native backups: `secrets/backups/`.
- Private import SQL and snapshot manifest: `secrets/supabase-import/`.
- Native backup/restore verification: `evidence/database/backup-restore.json`.
- Supabase content, permissions, and runtime-role verification:
  `evidence/database/supabase-migration.json`.

The import SQL was tested in a new temporary local database before remote use.
The remote verification checked content hashes for all 30 tables, all 45 migration
records, the audit identity sequence, all table RLS flags, API role isolation,
backend reads, and read-only protection of password hashes. No hosted backend
HTTP or SMTP flow has been tested as part of this database-only migration.
