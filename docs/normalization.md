# Database normalization

The v1 schema is normalized to third normal form for transactional entities, with deliberate JSONB snapshots where the whole value is immutable and read together.

## Normalized relationships

- Users, projects, and memberships are separate tables. Membership uses `(project_id, user_id)` as its natural composite key; project ownership remains an explicit foreign key with a trigger that guarantees owner membership.
- Prompts store stable metadata. Every editable template save creates a `prompt_versions` row, so version content is never overwritten.
- Runs reference the exact user, project, prompt, and immutable version used. Historical provider/model/cost values live on the ledger row and do not change when pricing changes.
- Deployments are lifecycle events referencing immutable versions. Rollback creates another event and links to the previous active event rather than rewriting history.
- Budgets use nullable user/project foreign keys plus an XOR constraint because the two target types share identical enforcement behavior. Partial unique indexes preserve one budget per target.
- Pricing rows are effective-dated and append-only in application behavior. A GiST exclusion constraint rejects overlapping provider/model windows.

## Intentional JSONB fields

`prompt_versions.variables`, `prompt_versions.model_config`, and `runs.input_variables` are JSONB because each is an immutable request/snapshot value consumed as a unit. Shape checks require arrays or objects. Values needed for authorization, filtering, joins, money calculations, and concurrency are regular typed columns and indexed accordingly.

Audit before/after documents are JSONB snapshots. The database trigger removes `password_hash`, `encrypted_secret`, and `token_hash` before insertion.

## Derived data

Lineage, deployment history, and monthly costs are views. Organization/user monthly metrics are materialized views with unique indexes so controlled concurrent refresh is possible. Derived rows are never authoritative for authorization, budget enforcement, or deployment state.
