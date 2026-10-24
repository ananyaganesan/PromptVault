# PromptVault column dictionary

Generated from the live PostgreSQL catalog; see academic evidence for its migration revision.
Logical tables exclude physical partitions and views. No stored row values are exported.

## `api_tokens`

Hashed, expiring and revocable project-scoped Serve credentials.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| project_id | uuid | False | — | Referenced project/workspace. |
| name | character varying(120) | False | — | Human-readable resource name (migration name for schema_migrations). |
| token_prefix | character varying(20) | False | — | Non-secret token label shown after one-time disclosure. |
| token_hash | character(64) | False | — | SHA-256 digest of the one-time disclosed token. |
| created_by | uuid | False | — | User who created the resource. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| expires_at | timestamp with time zone | True | — | Time after which the credential/session is invalid. |
| revoked_at | timestamp with time zone | True | — | Optional time of explicit credential/session revocation. |
| revoked_by | uuid | True | — | User who revoked the credential, if retained. |

Constraints and keys:

- `NOT NULL created_at`
- `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL created_by`
- `CHECK (((expires_at IS NULL) OR (expires_at > created_at)))`
- `CHECK ((token_hash ~ '^[0-9a-f]{64}$'::text))`
- `NOT NULL id`
- `CHECK ((length(TRIM(BOTH FROM name)) > 0))`
- `NOT NULL name`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE`
- `NOT NULL project_id`
- `CHECK (((revoked_at IS NULL) OR (revoked_at >= created_at)))`
- `CHECK (((revoked_at IS NULL) = (revoked_by IS NULL)))`
- `FOREIGN KEY (revoked_by) REFERENCES users(id) ON DELETE SET NULL`
- `NOT NULL token_hash`
- `NOT NULL token_prefix`

Indexes:

- `CREATE UNIQUE INDEX api_tokens_pkey ON public.api_tokens USING btree (id)`
- `CREATE INDEX ix_api_tokens_project_active ON public.api_tokens USING btree (project_id, created_at DESC) WHERE (revoked_at IS NULL)`
- `CREATE UNIQUE INDEX uq_api_tokens_hash ON public.api_tokens USING btree (token_hash)`

## `audit_events`

Append-only redacted change history and actor attribution.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | bigint | False | GENERATED IDENTITY | Surrogate row identity (runs also includes creation time in its primary key). |
| actor_user_id | uuid | True | — | Optional user responsible for the audited change. |
| action | character varying(120) | False | — | Audited operation name. |
| entity_type | character varying(80) | False | — | Relation/resource kind affected by the audited operation. |
| entity_id | uuid | True | — | Affected UUID resource identity, if applicable. |
| before_data | jsonb | True | — | Redacted resource snapshot before the change. |
| after_data | jsonb | True | — | Redacted resource snapshot after the change. |
| request_id | character varying(128) | True | — | Correlation identifier connecting the request and audit/execution. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `CHECK ((length(TRIM(BOTH FROM action)) > 0))`
- `NOT NULL action`
- `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `NOT NULL created_at`
- `CHECK ((length(TRIM(BOTH FROM entity_type)) > 0))`
- `NOT NULL entity_type`
- `NOT NULL id`
- `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX audit_events_pkey ON public.audit_events USING btree (id)`
- `CREATE INDEX ix_audit_events_action_created ON public.audit_events USING btree (action, created_at DESC, id)`
- `CREATE INDEX ix_audit_events_actor_created ON public.audit_events USING btree (actor_user_id, created_at DESC, id)`
- `CREATE INDEX ix_audit_events_entity_created ON public.audit_events USING btree (entity_type, entity_id, created_at DESC, id)`

## `auth_sessions`

Server-side session lifetime and revocation state.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | — | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| issued_at | timestamp with time zone | False | — | Time the server-side session was issued. |
| expires_at | timestamp with time zone | False | — | Time after which the credential/session is invalid. |
| revoked_at | timestamp with time zone | True | — | Optional time of explicit credential/session revocation. |
| revocation_reason | text | True | — | Reason a session was revoked; consistent with revoked_at. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL expires_at`
- `NOT NULL id`
- `NOT NULL issued_at`
- `PRIMARY KEY (id)`
- `CHECK ((((revoked_at IS NULL) AND (revocation_reason IS NULL)) OR ((revoked_at IS NOT NULL) AND (revocation_reason IS NOT NULL))))`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`
- `CHECK ((expires_at > issued_at))`

Indexes:

- `CREATE UNIQUE INDEX auth_sessions_pkey ON public.auth_sessions USING btree (id)`
- `CREATE INDEX ix_auth_sessions_expired_cleanup ON public.auth_sessions USING btree (expires_at) WHERE (revoked_at IS NULL)`
- `CREATE INDEX ix_auth_sessions_user_active ON public.auth_sessions USING btree (user_id, expires_at DESC) WHERE (revoked_at IS NULL)`

## `spend_limits`

Monthly execution limit targeting exactly one user or project.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | True | — | Referenced account/actor or user spend-limit target. |
| project_id | uuid | True | — | Referenced project/workspace. |
| monthly_limit | numeric(18,6) | False | — | Exact decimal monthly execution allowance. |
| timezone | character varying(64) | False | 'UTC'::character varying | Timezone defining the target's monthly spend-limit boundaries. |
| created_by | uuid | True | — | User who created the resource. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| updated_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Timestamp of the latest mutable state change. |

Constraints and keys:

- `NOT NULL created_at`
- `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `CHECK ((num_nonnulls(user_id, project_id) = 1))`
- `NOT NULL id`
- `CHECK ((monthly_limit >= (0)::numeric))`
- `NOT NULL monthly_limit`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE`
- `CHECK ((length(TRIM(BOTH FROM timezone)) > 0))`
- `NOT NULL timezone`
- `NOT NULL updated_at`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`

Indexes:

- `CREATE UNIQUE INDEX spend_limits_pkey ON public.spend_limits USING btree (id)`
- `CREATE INDEX ix_spend_limits_updated ON public.spend_limits USING btree (updated_at DESC, id DESC)`
- `CREATE UNIQUE INDEX uq_spend_limits_project ON public.spend_limits USING btree (project_id) WHERE (project_id IS NOT NULL)`
- `CREATE UNIQUE INDEX uq_spend_limits_user ON public.spend_limits USING btree (user_id) WHERE (user_id IS NOT NULL)`

## `deployment_rollbacks`

Normalized rollback link and explanation without copied scope.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| deployment_id | uuid | False | — | Referenced rollback deployment event. |
| rollback_of_id | uuid | False | — | Deployment event being rolled back. |
| reason | text | False | — | Reason recorded for a rollback decision. |

Constraints and keys:

- `FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE RESTRICT`
- `NOT NULL deployment_id`
- `PRIMARY KEY (deployment_id)`
- `CHECK ((length(TRIM(BOTH FROM reason)) > 0))`
- `NOT NULL reason`
- `FOREIGN KEY (rollback_of_id) REFERENCES deployments(id) ON DELETE RESTRICT`
- `NOT NULL rollback_of_id`

Indexes:

- `CREATE UNIQUE INDEX deployment_rollbacks_pkey ON public.deployment_rollbacks USING btree (deployment_id)`

## `deployments`

Prompt/version promotion, review and rollback lifecycle records.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| version_id | uuid | False | — | Referenced immutable prompt version. |
| environment | deployment_environment | False | — | Application promotion slot (dev/staging/prod), usable locally. |
| status | deployment_status | False | — | Lifecycle state constrained by the relation's enum/checks. |
| request_note | text | True | — | Requester's explanation for promotion. |
| review_note | text | True | — | Reviewer's decision explanation. |
| requested_by | uuid | False | — | User who requested the deployment. |
| reviewed_by | uuid | True | — | Optional user who reviewed the deployment. |
| requested_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Time the promotion was requested. |
| reviewed_at | timestamp with time zone | True | — | Optional time of the review decision. |
| activated_at | timestamp with time zone | True | — | Optional time the version became active. |

Constraints and keys:

- `NOT NULL environment`
- `NOT NULL id`
- `CHECK (((environment = 'prod'::deployment_environment) OR (status <> 'pending'::deployment_status)))`
- `PRIMARY KEY (id)`
- `CHECK (((environment <> 'prod'::deployment_environment) OR (status <> ALL (ARRAY['active'::deployment_status, 'superseded'::deployment_status, 'rolled_back'::deployment_status])) OR (reviewed_at IS NOT NULL)))`
- `CHECK (((status <> 'rejected'::deployment_status) OR (length(TRIM(BOTH FROM review_note)) > 0)))`
- `NOT NULL requested_at`
- `FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL requested_by`
- `CHECK (((reviewed_by IS NULL) = (reviewed_at IS NULL)))`
- `FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE RESTRICT`
- `CHECK ((((status = ANY (ARRAY['pending'::deployment_status, 'cancelled'::deployment_status])) AND (reviewed_at IS NULL) AND (activated_at IS NULL)) OR ((status = 'rejected'::deployment_status) AND (reviewed_at IS NOT NULL) AND (activated_at IS NULL)) OR ((status = ANY (ARRAY['active'::deployment_status, 'superseded'::deployment_status, 'rolled_back'::deployment_status])) AND (activated_at IS NOT NULL))))`
- `NOT NULL status`
- `FOREIGN KEY (version_id) REFERENCES prompt_versions(id) ON DELETE RESTRICT`
- `NOT NULL version_id`

Indexes:

- `CREATE UNIQUE INDEX deployments_pkey ON public.deployments USING btree (id)`
- `CREATE INDEX ix_deployments_pending_prod ON public.deployments USING btree (requested_at, id) WHERE ((environment = 'prod'::deployment_environment) AND (status = 'pending'::deployment_status))`
- `CREATE INDEX ix_deployments_version_environment ON public.deployments USING btree (version_id, environment, status)`

## `email_verification_tokens`

Hashed, expiring single-use email ownership credentials.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| token_hash | character(64) | False | — | SHA-256 digest of the one-time disclosed token. |
| expires_at | timestamp with time zone | False | — | Time after which the credential/session is invalid. |
| used_at | timestamp with time zone | True | — | Optional time when a reset token was consumed. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL expires_at`
- `NOT NULL id`
- `PRIMARY KEY (id)`
- `UNIQUE (token_hash)`
- `NOT NULL token_hash`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`

Indexes:

- `CREATE UNIQUE INDEX email_verification_tokens_pkey ON public.email_verification_tokens USING btree (id)`
- `CREATE UNIQUE INDEX email_verification_tokens_token_hash_key ON public.email_verification_tokens USING btree (token_hash)`
- `CREATE INDEX ix_email_verification_tokens_user_active ON public.email_verification_tokens USING btree (user_id, created_at DESC) WHERE (used_at IS NULL)`

## `model_pricing`

Historical provider/model effective price windows.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| provider | character varying(80) | False | — | Provider identity; external execution is restricted by application policy. |
| model | character varying(160) | False | — | Provider-specific model identifier. |
| input_price_per_million | numeric(18,6) | False | — | Historical price per million input tokens. |
| output_price_per_million | numeric(18,6) | False | — | Historical price per million output tokens. |
| effective_from | timestamp with time zone | False | — | Inclusive start of the pricing validity window. |
| effective_to | timestamp with time zone | True | — | Optional end of the pricing validity window. |
| created_by | uuid | True | — | User who created the resource. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `NOT NULL created_at`
- `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL`
- `NOT NULL effective_from`
- `CHECK (((provider)::text = 'gemini'::text)) NOT VALID`
- `NOT NULL id`
- `NOT NULL input_price_per_million`
- `CHECK ((length(TRIM(BOTH FROM model)) > 0))`
- `NOT NULL model`
- `EXCLUDE USING gist (provider WITH =, model WITH =, tstzrange(effective_from, effective_to, '[)'::text) WITH &&)`
- `CHECK (((input_price_per_million >= (0)::numeric) AND (output_price_per_million >= (0)::numeric)))`
- `NOT NULL output_price_per_million`
- `PRIMARY KEY (id)`
- `CHECK ((length(TRIM(BOTH FROM provider)) > 0))`
- `NOT NULL provider`
- `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`

Indexes:

- `CREATE INDEX ix_model_pricing_lookup ON public.model_pricing USING btree (provider, model, effective_from DESC)`
- `CREATE INDEX model_pricing_no_overlap ON public.model_pricing USING gist (provider, model, tstzrange(effective_from, effective_to, '[)'::text))`
- `CREATE UNIQUE INDEX model_pricing_pkey ON public.model_pricing USING btree (id)`

## `password_history`

Previously used password hashes for reuse prevention.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| password_hash | text | False | — | Argon2id password digest; plaintext is never stored. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL id`
- `NOT NULL password_hash`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`
- `UNIQUE (user_id, password_hash)`

Indexes:

- `CREATE UNIQUE INDEX password_history_pkey ON public.password_history USING btree (id)`
- `CREATE UNIQUE INDEX password_history_user_id_password_hash_key ON public.password_history USING btree (user_id, password_hash)`

## `password_reset_tokens`

Hashed, expiring single-use password-reset credentials.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| token_hash | character(64) | False | — | SHA-256 digest of the one-time disclosed token. |
| expires_at | timestamp with time zone | False | — | Time after which the credential/session is invalid. |
| used_at | timestamp with time zone | True | — | Optional time when a reset token was consumed. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL expires_at`
- `NOT NULL id`
- `PRIMARY KEY (id)`
- `UNIQUE (token_hash)`
- `NOT NULL token_hash`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`

Indexes:

- `CREATE INDEX ix_password_reset_tokens_user_active ON public.password_reset_tokens USING btree (user_id, expires_at DESC) WHERE (used_at IS NULL)`
- `CREATE UNIQUE INDEX password_reset_tokens_pkey ON public.password_reset_tokens USING btree (id)`
- `CREATE UNIQUE INDEX password_reset_tokens_token_hash_key ON public.password_reset_tokens USING btree (token_hash)`

## `project_invitations`

Pending, expiring recipient-accepted project access invitations.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| project_id | uuid | False | — | Referenced project/workspace. |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| invited_by | uuid | False | — | Account issuing a project invitation. |
| token_hash | text | False | — | SHA-256 digest of the one-time disclosed token. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| expires_at | timestamp with time zone | False | — | Time after which the credential/session is invalid. |
| accepted_at | timestamp with time zone | True | — | Timestamp of recipient acceptance and membership creation. |
| revoked_at | timestamp with time zone | True | — | Optional time of explicit credential/session revocation. |

Constraints and keys:

- `CHECK ((expires_at > created_at))`
- `CHECK (((accepted_at IS NULL) OR (revoked_at IS NULL)))`
- `NOT NULL created_at`
- `NOT NULL expires_at`
- `NOT NULL id`
- `FOREIGN KEY (invited_by) REFERENCES users(id)`
- `NOT NULL invited_by`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE`
- `NOT NULL project_id`
- `CHECK ((token_hash ~ '^[0-9a-f]{64}$'::text))`
- `UNIQUE (token_hash)`
- `NOT NULL token_hash`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`

Indexes:

- `CREATE UNIQUE INDEX ix_project_invitations_pending ON public.project_invitations USING btree (project_id, user_id) WHERE ((accepted_at IS NULL) AND (revoked_at IS NULL))`
- `CREATE INDEX ix_project_invitations_user ON public.project_invitations USING btree (user_id)`
- `CREATE UNIQUE INDEX project_invitations_pkey ON public.project_invitations USING btree (id)`
- `CREATE UNIQUE INDEX project_invitations_token_hash_key ON public.project_invitations USING btree (token_hash)`

## `project_members`

Many-to-many access relationship between users and projects.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| project_id | uuid | False | — | Referenced project/workspace. |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| added_by | uuid | True | — | User who granted membership, if retained. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL`
- `NOT NULL created_at`
- `PRIMARY KEY (project_id, user_id)`
- `FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE`
- `NOT NULL project_id`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `NOT NULL user_id`

Indexes:

- `CREATE INDEX ix_project_members_user ON public.project_members USING btree (user_id, project_id)`
- `CREATE UNIQUE INDEX project_members_pkey ON public.project_members USING btree (project_id, user_id)`

## `projects`

Owned workspace containing prompts and scoped memberships.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| name | character varying(160) | False | — | Human-readable resource name (migration name for schema_migrations). |
| key | character varying(63) | False | — | Stable resource lookup key; uniqueness scope is defined by constraints. |
| description | text | True | — | Optional resource description. |
| owner_id | uuid | False | — | User owning the project. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| updated_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Timestamp of the latest mutable state change. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL id`
- `CHECK (((key)::text ~ '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$'::text))`
- `NOT NULL key`
- `CHECK (((length(TRIM(BOTH FROM name)) >= 1) AND (length(TRIM(BOTH FROM name)) <= 160)))`
- `NOT NULL name`
- `FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL owner_id`
- `PRIMARY KEY (id)`
- `NOT NULL updated_at`

Indexes:

- `CREATE INDEX ix_projects_owner ON public.projects USING btree (owner_id)`
- `CREATE UNIQUE INDEX projects_pkey ON public.projects USING btree (id)`
- `CREATE UNIQUE INDEX uq_projects_key ON public.projects USING btree (key)`

## `prompt_version_parents`

Normalized same-prompt version ancestry.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| version_id | uuid | False | — | Referenced immutable prompt version. |
| parent_version_id | uuid | False | — | Optional predecessor version in the same prompt. |

Constraints and keys:

- `CHECK ((version_id <> parent_version_id))`
- `FOREIGN KEY (parent_version_id) REFERENCES prompt_versions(id) ON DELETE RESTRICT`
- `NOT NULL parent_version_id`
- `PRIMARY KEY (version_id)`
- `FOREIGN KEY (version_id) REFERENCES prompt_versions(id) ON DELETE CASCADE`
- `NOT NULL version_id`

Indexes:

- `CREATE INDEX ix_version_parents_parent ON public.prompt_version_parents USING btree (parent_version_id)`
- `CREATE UNIQUE INDEX prompt_version_parents_pkey ON public.prompt_version_parents USING btree (version_id)`

## `prompt_version_variables`

Ordered atomic variable declarations for immutable versions.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| version_id | uuid | False | — | Referenced immutable prompt version. |
| ordinal | integer | False | — | One-based declaration order within a version. |
| name | text | False | — | Human-readable resource name (migration name for schema_migrations). |

Constraints and keys:

- `CHECK ((name ~ '^[A-Za-z_][A-Za-z0-9_]*$'::text))`
- `NOT NULL name`
- `CHECK ((ordinal > 0))`
- `NOT NULL ordinal`
- `PRIMARY KEY (version_id, ordinal)`
- `FOREIGN KEY (version_id) REFERENCES prompt_versions(id) ON DELETE CASCADE`
- `UNIQUE (version_id, name)`
- `NOT NULL version_id`

Indexes:

- `CREATE UNIQUE INDEX prompt_version_variables_pkey ON public.prompt_version_variables USING btree (version_id, ordinal)`
- `CREATE UNIQUE INDEX prompt_version_variables_version_id_name_key ON public.prompt_version_variables USING btree (version_id, name)`

## `prompt_versions`

Immutable template and configuration snapshots with lineage.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| prompt_id | uuid | False | — | Referenced prompt identity. |
| version_number | integer | False | — | Monotonically assigned version number within a prompt. |
| template_body | text | False | — | Immutable prompt template text. |
| commit_message | character varying(500) | False | — | Author's explanation of the version change. |
| created_by | uuid | False | — | User who created the resource. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| provider | character varying(80) | False | — | Provider identity; external execution is restricted by application policy. |
| model | character varying(160) | False | — | Provider-specific model identifier. |
| temperature | numeric | True | — | Saved sampling temperature for an immutable version. |
| max_output_tokens | integer | True | — | Saved output-token limit for an immutable version. |

Constraints and keys:

- `NOT NULL commit_message`
- `CHECK ((length(TRIM(BOTH FROM commit_message)) > 0))`
- `NOT NULL created_at`
- `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL created_by`
- `NOT NULL id`
- `NOT NULL model`
- `CHECK ((version_number > 0))`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE RESTRICT`
- `NOT NULL prompt_id`
- `NOT NULL provider`
- `NOT NULL template_body`
- `CHECK ((length(template_body) > 0))`
- `NOT NULL version_number`
- `UNIQUE (id, prompt_id)`
- `UNIQUE (prompt_id, version_number)`
- `CHECK ((length(TRIM(BOTH FROM model)) > 0))`
- `CHECK (((max_output_tokens IS NULL) OR ((max_output_tokens >= 1) AND (max_output_tokens <= 1000000))))`
- `CHECK (((provider)::text = 'gemini'::text)) NOT VALID`
- `CHECK (((temperature IS NULL) OR ((temperature >= (0)::numeric) AND (temperature <= (2)::numeric))))`

Indexes:

- `CREATE INDEX ix_prompt_versions_history ON public.prompt_versions USING btree (prompt_id, version_number DESC, id)`
- `CREATE UNIQUE INDEX prompt_versions_pkey ON public.prompt_versions USING btree (id)`
- `CREATE UNIQUE INDEX uq_prompt_versions_id_prompt ON public.prompt_versions USING btree (id, prompt_id)`
- `CREATE UNIQUE INDEX uq_prompt_versions_number ON public.prompt_versions USING btree (prompt_id, version_number)`

## `prompts`

Named prompt identity within a project.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| project_id | uuid | False | — | Referenced project/workspace. |
| key | character varying(63) | False | — | Stable resource lookup key; uniqueness scope is defined by constraints. |
| name | character varying(160) | False | — | Human-readable resource name (migration name for schema_migrations). |
| description | text | True | — | Optional resource description. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| updated_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Timestamp of the latest mutable state change. |

Constraints and keys:

- `NOT NULL created_at`
- `NOT NULL id`
- `CHECK (((key)::text ~ '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$'::text))`
- `NOT NULL key`
- `CHECK (((length(TRIM(BOTH FROM name)) >= 1) AND (length(TRIM(BOTH FROM name)) <= 160)))`
- `NOT NULL name`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE`
- `NOT NULL project_id`
- `NOT NULL updated_at`
- `UNIQUE (id, project_id)`
- `UNIQUE (project_id, key)`

Indexes:

- `CREATE INDEX ix_prompts_project_updated ON public.prompts USING btree (project_id, updated_at DESC, id)`
- `CREATE UNIQUE INDEX prompts_pkey ON public.prompts USING btree (id)`
- `CREATE UNIQUE INDEX uq_prompts_id_project ON public.prompts USING btree (id, project_id)`
- `CREATE UNIQUE INDEX uq_prompts_project_key ON public.prompts USING btree (project_id, key)`

## `provider_keys`

Encrypted administrator-managed shared provider credentials.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| provider | character varying(80) | False | — | Provider identity; external execution is restricted by application policy. |
| alias | character varying(120) | False | — | Administrator's label for a provider credential. |
| encrypted_secret | bytea | False | — | Authenticated encrypted API key; never a plaintext response. |
| created_by | uuid | False | — | User who created the resource. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| deactivated_at | timestamp with time zone | True | — | Optional time when this provider credential was disabled. |

Constraints and keys:

- `CHECK ((length(TRIM(BOTH FROM alias)) > 0))`
- `NOT NULL alias`
- `NOT NULL created_at`
- `FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL created_by`
- `CHECK (((deactivated_at IS NULL) OR (deactivated_at >= created_at)))`
- `NOT NULL encrypted_secret`
- `CHECK (((provider)::text = 'gemini'::text)) NOT VALID`
- `NOT NULL id`
- `PRIMARY KEY (id)`
- `CHECK ((length(TRIM(BOTH FROM provider)) > 0))`
- `NOT NULL provider`

Indexes:

- `CREATE INDEX ix_provider_keys_provider_created ON public.provider_keys USING btree (provider, created_at DESC, id DESC)`
- `CREATE UNIQUE INDEX provider_keys_pkey ON public.provider_keys USING btree (id)`
- `CREATE UNIQUE INDEX uq_provider_keys_active_alias ON public.provider_keys USING btree (provider, alias) WHERE (deactivated_at IS NULL)`

## `reservation_results`

Normalized link from an admission to its immutable ledger result.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| reservation_id | uuid | False | — | Referenced execution admission record. |
| run_id | uuid | False | — | Optional execution ledger identity after reconciliation. |
| run_created_at | timestamp with time zone | False | — | Creation time completing the composite run foreign key. |

Constraints and keys:

- `PRIMARY KEY (reservation_id)`
- `FOREIGN KEY (reservation_id) REFERENCES run_reservations(id) ON DELETE CASCADE`
- `NOT NULL reservation_id`
- `NOT NULL run_created_at`
- `NOT NULL run_id`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs(id, created_at) ON DELETE RESTRICT`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs_2026_10(id, created_at) ON DELETE RESTRICT`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs_2026_11(id, created_at) ON DELETE RESTRICT`

Indexes:

- `CREATE UNIQUE INDEX reservation_results_pkey ON public.reservation_results USING btree (reservation_id)`

## `run_inputs`

Atomic named input values for an immutable run.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| run_id | uuid | False | — | Optional execution ledger identity after reconciliation. |
| run_created_at | timestamp with time zone | False | — | Creation time completing the composite run foreign key. |
| name | text | False | — | Human-readable resource name (migration name for schema_migrations). |
| value | text | False | — | Supplied string value for this named run input. |

Constraints and keys:

- `NOT NULL name`
- `PRIMARY KEY (run_id, run_created_at, name)`
- `NOT NULL run_created_at`
- `NOT NULL run_id`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs(id, created_at) ON DELETE CASCADE`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs_2026_10(id, created_at) ON DELETE CASCADE`
- `FOREIGN KEY (run_id, run_created_at) REFERENCES runs_2026_11(id, created_at) ON DELETE CASCADE`
- `NOT NULL value`

Indexes:

- `CREATE UNIQUE INDEX run_inputs_pkey ON public.run_inputs USING btree (run_id, run_created_at, name)`

## `run_reservations`

Idempotent execution admission and cost reconciliation state.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| version_id | uuid | False | — | Referenced immutable prompt version. |
| idempotency_key | character varying(128) | False | — | User-scoped execution request deduplication key. |
| request_fingerprint | character(64) | False | — | Digest binding an idempotency key to its request content. |
| claim_token | uuid | False | — | Internal execution-admission ownership credential. |
| estimated_cost | numeric(18,6) | False | — | Reserved cost before provider execution. |
| status | character varying(20) | False | — | Lifecycle state constrained by the relation's enum/checks. |
| error_code | character varying(80) | True | — | Normalized safe execution failure code, if any. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| updated_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Timestamp of the latest mutable state change. |

Constraints and keys:

- `NOT NULL claim_token`
- `NOT NULL created_at`
- `CHECK ((estimated_cost >= (0)::numeric))`
- `NOT NULL estimated_cost`
- `NOT NULL id`
- `CHECK ((length((idempotency_key)::text) >= 16))`
- `NOT NULL idempotency_key`
- `PRIMARY KEY (id)`
- `CHECK ((request_fingerprint ~ '^[0-9a-f]{64}$'::text))`
- `NOT NULL request_fingerprint`
- `CHECK (((status)::text = ANY ((ARRAY['reserved'::character varying, 'completed'::character varying, 'failed'::character varying, 'uncertain'::character varying, 'blocked'::character varying])::text[])))`
- `NOT NULL status`
- `NOT NULL updated_at`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT`
- `UNIQUE (user_id, idempotency_key)`
- `NOT NULL user_id`
- `FOREIGN KEY (version_id) REFERENCES prompt_versions(id) ON DELETE RESTRICT`
- `NOT NULL version_id`

Indexes:

- `CREATE INDEX ix_reservations_version_created ON public.run_reservations USING btree (version_id, created_at DESC)`
- `CREATE INDEX run_reservations_budget_user_idx ON public.run_reservations USING btree (user_id, created_at) WHERE ((status)::text = ANY ((ARRAY['reserved'::character varying, 'uncertain'::character varying])::text[]))`
- `CREATE UNIQUE INDEX run_reservations_pkey ON public.run_reservations USING btree (id)`
- `CREATE UNIQUE INDEX run_reservations_user_id_idempotency_key_key ON public.run_reservations USING btree (user_id, idempotency_key)`

## `runs`

Append-only execution ledger, physically partitioned by creation month.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| user_id | uuid | False | — | Referenced account/actor or user budget target. |
| version_id | uuid | False | — | Referenced immutable prompt version. |
| status | run_status | False | — | Lifecycle state constrained by the relation's enum/checks. |
| output_text | text | True | — | Provider output, if execution produced a result. |
| prompt_tokens | integer | False | 0 | Recorded input-token usage. |
| completion_tokens | integer | False | 0 | Recorded output-token usage. |
| latency_ms | integer | False | 0 | Recorded execution duration in milliseconds. |
| cost | numeric(18,6) | False | 0 | Exact decimal cost snapshot; allowed external free executions use zero. |
| error_code | character varying(80) | True | — | Normalized safe execution failure code, if any. |
| request_id | character varying(128) | True | — | Correlation identifier connecting the request and audit/execution. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |

Constraints and keys:

- `CHECK (((status <> 'completed'::run_status) OR ((output_text IS NOT NULL) AND (error_code IS NULL))))`
- `NOT NULL completion_tokens`
- `CHECK ((cost >= (0)::numeric))`
- `NOT NULL cost`
- `NOT NULL created_at`
- `CHECK (((status = 'completed'::run_status) OR (error_code IS NOT NULL)))`
- `NOT NULL id`
- `NOT NULL latency_ms`
- `CHECK ((latency_ms >= 0))`
- `PRIMARY KEY (id, created_at)`
- `NOT NULL prompt_tokens`
- `NOT NULL status`
- `CHECK (((prompt_tokens >= 0) AND (completion_tokens >= 0)))`
- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT`
- `NOT NULL user_id`
- `FOREIGN KEY (version_id) REFERENCES prompt_versions(id) ON DELETE RESTRICT`
- `NOT NULL version_id`

Indexes:

- `CREATE INDEX ix_runs_status_created ON ONLY public.runs USING btree (status, created_at DESC, id)`
- `CREATE INDEX ix_runs_user_created ON ONLY public.runs USING btree (user_id, created_at DESC, id)`
- `CREATE INDEX ix_runs_version_created ON ONLY public.runs USING btree (version_id, created_at DESC, id)`
- `CREATE INDEX ix_runs_version_timeline ON ONLY public.runs USING btree (version_id, created_at DESC, id DESC) INCLUDE (status, cost)`
- `CREATE UNIQUE INDEX runs_pkey ON ONLY public.runs USING btree (id, created_at)`

## `schema_migrations`

Infrastructure record of applied migration versions/checksums.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| version | bigint | False | — | Applied migration number. |
| name | text | False | — | Human-readable resource name (migration name for schema_migrations). |
| checksum | character(64) | False | — | SHA-256 checksum protecting an applied migration from changes. |
| applied_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Time the migration was applied. |

Constraints and keys:

- `NOT NULL applied_at`
- `NOT NULL checksum`
- `NOT NULL name`
- `PRIMARY KEY (version)`
- `NOT NULL version`

Indexes:

- `CREATE UNIQUE INDEX schema_migrations_pkey ON public.schema_migrations USING btree (version)`

## `users`

Account identity, display name, credentials and authorization role.

| Column | Type | Nullable | Default / identity | Purpose |
|---|---|---|---|---|
| id | uuid | False | gen_random_uuid() | Surrogate row identity (runs also includes creation time in its primary key). |
| email | citext | False | — | Case-insensitive unique account login email. |
| display_name | character varying(120) | False | — | User-editable name shown across the application. |
| password_hash | text | False | — | Argon2id password digest; plaintext is never stored. |
| role | user_role | False | 'user'::user_role | Account authorization role: user or admin. |
| is_active | boolean | False | true | Whether the account may authenticate and access resources. |
| created_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Database timestamp when the record was created. |
| updated_at | timestamp with time zone | False | CURRENT_TIMESTAMP | Timestamp of the latest mutable state change. |
| email_verified_at | timestamp with time zone | True | — | Time when the account proved control of its email address. |

Constraints and keys:

- `NOT NULL created_at`
- `CHECK (((length(TRIM(BOTH FROM display_name)) >= 1) AND (length(TRIM(BOTH FROM display_name)) <= 120)))`
- `NOT NULL display_name`
- `CHECK (((length(TRIM(BOTH FROM (email)::text)) >= 3) AND (length(TRIM(BOTH FROM (email)::text)) <= 320)))`
- `NOT NULL email`
- `NOT NULL id`
- `NOT NULL is_active`
- `NOT NULL password_hash`
- `PRIMARY KEY (id)`
- `NOT NULL role`
- `NOT NULL updated_at`

Indexes:

- `CREATE INDEX ix_users_admin_list ON public.users USING btree (role, is_active, created_at DESC, id DESC)`
- `CREATE INDEX ix_users_role_active ON public.users USING btree (role, is_active)`
- `CREATE UNIQUE INDEX uq_users_email ON public.users USING btree (email)`
- `CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)`
