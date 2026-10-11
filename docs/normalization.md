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

## Functional-dependency review

| Relation(s) | Candidate key → non-key attributes | Normal-form conclusion |
|---|---|---|
| `users` | `id → email, display_name, password_hash, role, status, timestamps`; `email → same` | BCNF; both determinants are candidate keys |
| `projects`, `prompts` | ID determines metadata; project key and `(project_id,prompt key)` are alternate keys | BCNF |
| `project_members` | `(project_id,user_id) → added_by,created_at` | BCNF; no partial dependency |
| `prompt_versions` | `id → snapshot`; `(prompt_id,version_number) → snapshot` | BCNF; parent is a same-prompt FK, not duplicated parent data |
| `model_pricing` | `id → price window`; the exclusion constraint makes provider/model/time windows non-overlapping | 3NF; history is effective-dated rather than overwritten |
| `budgets` | `id → target,limit,timezone`; each partial unique target also determines its budget row | BCNF under the XOR target constraint |
| `provider_keys`, `api_tokens` | ID determines secret metadata; active alias/token hash are constrained alternate identifiers | BCNF for persisted attributes |
| `deployments` | `id → lifecycle snapshot`; active uniqueness is a conditional business invariant | 3NF; review/rollback facts belong to the deployment event |
| `runs` | `(id,created_at) → immutable execution snapshot` | 3NF; provider/model/cost are intentional historical facts, not current pricing derivations |
| `audit_events` | `id → actor,action,entity,snapshots,time` | 3NF append-only event relation |
| `password_reset_tokens`, `auth_sessions` | token/session ID determines one user's lifecycle metadata | BCNF |
| `password_history` | `(user_id,password_hash) → created_at` | BCNF |
| `run_reservations` | `id → request/target/cost/state`; `(user_id,idempotency_key) → same` | BCNF; actual cost/run reference appear only after reconciliation |
| `schema_migrations` | `version → name,checksum,applied_at` | BCNF tracking relation |

No relation contains a non-key attribute that determines another non-key attribute. Apparent cross-table facts—owner name, prompt name, current price, member state—are obtained by joins or views rather than copied into transactional tables. The deliberate run/deployment/audit snapshots preserve facts as they were at an event time; replacing them with current master data would destroy history rather than improve normalization.

## Derived data

Lineage, deployment history, and monthly costs are views. Organization/user monthly metrics are materialized views with unique indexes so controlled concurrent refresh is possible. Derived rows are never authoritative for authorization, budget enforcement, or deployment state.
