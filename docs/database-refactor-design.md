# Database refactor design — 2026-10-23

This design precedes new migration 030. Applied migrations 001–029 remain unchanged.
The persistent local database is preserved; changes are rehearsed on isolated test
and restore databases before migration. A verified native dump is retained privately.

## Normalized execution and deployment relations

- `runs`: retain execution identity, user, immutable version reference, outcome,
  response, measured usage/latency/cost and request timestamp.
  Derive prompt/project and provider/model through the immutable version rather
  than storing duplicate identifiers/configuration on each execution.
- `run_reservations`: retain user-scoped idempotency/admission state and version.
  Derive prompt/project through the immutable version.
- `deployments`: retain version, environment, decision and actor/timestamp facts.
  Derive prompt through the immutable version. Serialize activation using the
  existing prompt lock and a database constraint trigger to preserve one active
  release per prompt/environment after removal of the redundant prompt column.
- Read-only context views expose derived relationships for analytics, joins and
  backwards-compatible API representations. They are not additional stored tables.
- Rollback references must identify an earlier deployment of the same prompt and
  environment; the database continues to enforce the boundary after normalization.

ORM mappings and application queries must use the normalized base relations for
ordinary persistence. Database procedures retain responsibility for budget
admission, immutable version allocation, activation, review and rollback locks.
Raw SQL remains limited to those advanced database features, recursive lineage,
partition/maintenance administration and measured snapshot-consistent reports.

## Migration and validation

The migration checks existing derived identifiers before removing redundant
columns; inconsistencies abort rather than modifying historical facts. Existing
accounts, token hashes, versions, runs and deployment decisions are retained.
Updated procedures, context views and grants are installed atomically with the
column changes. Validate fresh and upgraded databases, restore counts, rejected
cross-project writes, concurrency, authorization, idempotency and API contracts.

The normalized design also separates optional relationships rather than copying
their implied facts into lifecycle rows:

- `prompt_version_parents(version_id PK, parent_version_id FK)` stores ancestry;
  it does not repeat the prompt inferred from either version. A constraint trigger
  validates same-prompt ancestry. Version snapshots remain immutable.
- `prompt_version_variables(version_id, ordinal PK, name)` stores atomic ordered
  variable declarations, with a unique `(version_id,name)` alternate key.
- `reservation_results(reservation_id PK, run_id, run_created_at)` links finalized
  admission to its ledger result. Actual cost is read from the result, not copied.
- `deployment_rollbacks(deployment_id PK, rollback_of_id, reason)` stores rollback
  links without repeating the prompt/environment inferred from either deployment.

These four relation tables and the `run_inputs` relation below extend the original
19 tables to 24 logical tables. `version_context`, `reservation_context`, `run_context`, and
`deployment_context` expose derived API fields. They are projections, not stored
copies. New diagrams and dictionary entries must explicitly list the new relations.

For atomic course-facing attributes, version model configuration is stored as
provider/model/temperature/output-limit columns, and `run_inputs` stores one
named string input per run. API JSON objects are assembled by context views.
This adds one relation (24 logical tables total). Audit before/after JSON remains
an opaque historical event document, not duplicated live entity attributes.

## Gemini-only scope (revision 031)

The user narrowed provider support to Gemini in every environment. Preserve immutable
historical configurations and execution records; reject new non-Gemini versions,
credentials, pricing, admissions, runs and activations. Historical read DTOs retain
the original provider string, while write DTOs accept only Gemini. Removed-provider
credentials are deactivated and hidden from current configuration listings. Existing
versions require an explicit new Gemini configuration before execution/activation;
no silent history rewrite or provider fallback is permitted.
