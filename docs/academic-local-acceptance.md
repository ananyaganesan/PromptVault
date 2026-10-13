# Academic database evidence and local demonstration

Accepted technically on 2026-10-13 against PostgreSQL 18. Migration 024 adds the
email-verification timestamp, hashed token relation, atomic confirmation function,
and inactive-account cleanup trigger while backfilling existing accounts as verified.

## Deliverables

- [Column dictionary](data-dictionary.md): all 147 columns of 17 logical tables,
  with purpose, catalog types, nullability, defaults, identity behavior, primary/
  alternate/foreign keys, checks and index definitions.
- [Machine-readable evidence](../evidence/academic/database-evidence.json): current
  migration checksums; 17 table mappings; five view/materialized-view definitions;
  21 non-internal logical-table triggers; 60 logical-table indexes; the actual
  stored-procedure definition; nonempty join/aggregate/view results and a normal
  `EXPLAIN (ANALYZE, BUFFERS)` plan. Small-data plans need not choose an index;
  representative-data plan tests separately verify index use and partition pruning.
- [Collector](../scripts/collect-academic-evidence.py): reproducible live-catalog
  extraction and SQL demonstrations, limited to a disposable `_test` database.
  Source SHA-256 fingerprints bind the report to the script, ER/normalization
  documents and migration files; the dictionary has its own checksum.

The collector demonstrates project INSERT/SELECT/UPDATE/DELETE, automatic owner
membership, audit insert/update/delete events, a savepoint rollback, invalid-FK
rejection, cascade deletion and `CALL perform_system_maintenance(...)`. All of its
SQL writes, including maintenance effects, roll back before it exports evidence.
PostgreSQL identity sequences can still advance during rolled-back inserts; gaps
are expected and no demonstration rows are retained.
It creates one clearly labeled synthetic internal-mock run inside that transaction
to guarantee nonempty aggregate results. This is not a real provider request.
No account credentials, token values/hashes or provider secrets are exported.

Immutable and append-only relations are intentionally not subject to unrestricted
CRUD: prompt edits create a new version, runs/audits retain event history, and
revocation/consumption replace deletion in credential lifecycle flows. Existing
database tests prove immutable writes are rejected and audit secrets are redacted.

## Validation and full local journey

- 109 database, concurrency, performance and collector tests passed, including
  migration integrity, constraints, roles, immutable rows, auditing, budget and
  execution admission, maintenance, approval/version/member races, index use and
  partition pruning.
- A separate 56-test delivery/schema pass included both collector checks and
  existing executable showcase/version-race/approval-race examples.
- All 152 frontend tests passed; types, lint, build, collector/test Ruff and
  whitespace checks passed.
- Twelve desktop/mobile Chrome cases passed in 36.3 seconds: registration/reset/
  session/logout; project creation/update/member grant/removal; immutable versions
  and lineage; run output/history/reload; profile persistence; deployment approval,
  Serve, rollback and token revocation; admin credentials, budgets, zero-valued
  pricing, runs, audit and maintenance.

The browser checks found navigation links to `/admin/budgets` and
`/admin/model-pricing` without registered routes. Both existing management pages
are now reachable under the existing admin authorization boundary. The stale
run-detail test now checks the displayed latency. The admin budget test explicitly
creates an internal-mock fixture, and its pricing example uses zero rates for an
allowed provider. External execution still rejects non-free configurations.

Initial checks on the previously accumulated A2 browser database found the missing
routes and outdated assertion. Overlapping reruns on that large shared fixture
also timed out during workspace loading. Final acceptance ran sequentially on the
separate academic database; it is a functional local-demo result, not a large-workspace
latency claim. Existing representative performance tests passed separately.

## Reproduce

This session freshly created `promptvault_academic_test` on the disposable cluster
at 127.0.0.1:55435, applied migrations 001–023 and ran all three seed files.
Subsequent tests/browser checks added isolated demonstration fixtures there.
For a new run, create a new disposable database; do not reset the application DB.

```bash
createdb -h 127.0.0.1 -p 55435 -U promptvault promptvault_academic_test
.venv/bin/python scripts/run-migrations.py --database-url postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test
ENVIRONMENT=test .venv/bin/python scripts/seed-database.py --database-url postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test
.venv/bin/python scripts/collect-academic-evidence.py --database-url postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test
```

For the browser journey, start the [A5 loopback SMTP/API and web setup](a5-local-acceptance.md)
with `E2E_DATABASE_URL` pointing to this database and a separate mailbox directory.
Then run from `web/`:

```bash
E2E_LIVE=1 E2E_BASE_URL=http://127.0.0.1:5178 E2E_API_BASE_URL=http://127.0.0.1:8005/api/v1 E2E_DATABASE_URL=postgresql://promptvault@127.0.0.1:55435/promptvault_academic_test E2E_MAILBOX_DIR=/private/tmp/promptvault-academic-mailbox npx playwright test e2e/live-auth-reset.spec.ts e2e/live-workspace.spec.ts e2e/live-profile.spec.ts e2e/live-runs.spec.ts e2e/live-deployments.spec.ts e2e/live-admin.spec.ts --project=desktop-chrome --project=mobile-chrome --output=/private/tmp/promptvault-academic-demo-results
```

Do not concurrently reset or mutate the selected database from another suite.
The maintenance showcase is a write-capable demonstration; use this disposable
database for it. The new collector rolls back its own writes.

## Submission boundary

The ER mapping's password-history primary key was corrected to match migration
018: UUID `id` is primary, `(user_id,password_hash)` is a unique alternate key.
Its normalization analysis and dictionary now agree with the catalog.

Design-before-implementation chronology remains unproven: `git log --reverse`
records both `docs/erd.md` and `db/migrations/002_tables.sql` in the initial commit
`13622f5` on 2026-09-03, followed by schema work in `39e201e` on 2026-09-23.
This proves the artifacts existed together, not which was prepared first. No dated
design evidence was invented. That academic item and final submission review remain
open; they do not require additional application code.

Email verification is validated locally with isolated database and loopback SMTP
acceptance. Deployment infrastructure and staging URLs remain excluded.
The fixed external providers remain Gemini, OpenRouter and Groq. Real free-tier
account calls remain pending as documented in [A1 acceptance](a1-local-acceptance.md).
