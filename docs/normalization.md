# Normalization and functional dependencies

Revision 030 removes stored transitive context and repeating variable/input collections. Model configuration uses atomic provider, model, temperature and output-limit columns. API JSON is reconstructed by views. No applied migration 001–029 was changed.

## Table-by-table 3NF review

For each relation, the listed candidate key determines all remaining stored attributes. Composite keys have no proper subset determining a non-key attribute. No non-key stored attribute determines another non-key stored attribute under the application business rules. Unique indexes supply alternate keys where applicable; conditional keys are explicitly qualified.

| Relation | Candidate keys / functional dependencies | 3NF rationale |
|---|---|---|
| `api_tokens` | `id`; `token_hash` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `audit_events` | `id` → remaining attributes | Before/after JSON is an opaque redacted historical document, not authoritative entity state. |
| `auth_sessions` | `id` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `spend_limits` | `id` → remaining attributes | XOR user/project target; partial unique indexes ensure one spend limit per target. |
| `deployment_rollbacks` | `deployment_id` → remaining attributes | One rollback link and reason per deployment; prompt/environment are derived. |
| `deployments` | `id` → remaining attributes | Version determines scope through joins; rollback link/reason live separately. |
| `email_verification_tokens` | `id`; `token_hash` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `model_pricing` | `id` → remaining attributes | Effective interval and prices belong to a pricing event; exclusion constraint prevents overlapping windows. |
| `password_history` | `id`; `(user_id,password_hash)` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `password_reset_tokens` | `id`; `token_hash` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `project_invitations` | `id`; `token_hash` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `project_members` | `(project_id, user_id)` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `projects` | `id`; `key` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `prompt_version_parents` | `version_id` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `prompt_version_variables` | `(version_id, ordinal)`; `(version_id,name)` → remaining attributes | One ordered atomic name; names are unique within the version. |
| `prompt_versions` | `id`; `(prompt_id,version_number)` → remaining attributes | Atomic configuration; ordered variables and ancestry live in separate relations. |
| `prompts` | `id`; `(project_id,key)` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `provider_keys` | `id` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `reservation_results` | `reservation_id` → remaining attributes | One result link per reservation; composite run FK identifies a partitioned ledger row. |
| `run_inputs` | `(run_id, run_created_at, name)` → remaining attributes | One atomic string per named execution input. |
| `run_reservations` | `id`; `(user_id,idempotency_key)` → remaining attributes | Only admission facts remain; result identity and actual cost come from reservation_results and runs. |
| `runs` | `(id, created_at)` → remaining attributes | Version identifies prompt/project/provider/model through joins; measured cost/usage are event facts, never current-price derivations. |
| `schema_migrations` | `version` → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |
| `users` | `id`; `email` (case-insensitive) → remaining attributes | Identity/lifecycle facts reference related entities through foreign keys; no copied parent descriptions or scope. |

## Dependencies removed by migration 030

- Former `runs.version_id → prompt_id → project_id` and `version_id → provider,model` no longer duplicate those facts in runs.
- Former `run_reservations.version_id → prompt_id → project_id` is derived, and completed result cost is read from the ledger.
- Former `deployments.version_id → prompt_id` is derived. Rollback relationships have their own relation.
- Version variable arrays and execution input objects are normalized into rows; model configuration is typed scalar attributes.

## Derived and historical values

The four context views rebuild the existing API shape; clients still receive variables/configuration/input JSON. Lineage, deployment history and monthly costs are views. Materialized metrics are caches, never authorization or budget authority. An immutable version fixes provider/model historically. Measured run cost remains stored because it is the amount recorded at execution, not a dependency on the current pricing row. Audit JSON remains an opaque event document.

A composite `runs(id,created_at)` primary key supports native range partitioning; child ledger references include both fields. Physical partitions are not additional independent logical entities. The [catalog dictionary](data-dictionary.md) supplies actual constraints and indexes, and the [upgrade test](../tests/database/test_normalization_upgrade.py) verifies preservation from revision 029.

Revision 031 adds Gemini-only checks on new versions, keys and prices, and guards execution/admission/activation references. `NOT VALID` preserves historical provider rows while enforcing checks on every new write; historical values are not silently rewritten. Non-Gemini execution and Serve requests are also rejected by the API. Revisions 032–033 rename the physical relation and its catalog objects to `spend_limits` while leaving budget behavior and the public API unchanged.
