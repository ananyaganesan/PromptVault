ALTER TABLE users
    ADD CONSTRAINT users_email_not_blank CHECK (length(trim(email::text)) BETWEEN 3 AND 320),
    ADD CONSTRAINT users_display_name_not_blank CHECK (length(trim(display_name)) BETWEEN 1 AND 120);
CREATE UNIQUE INDEX uq_users_email ON users (email);
CREATE INDEX ix_users_role_active ON users (role, is_active);

ALTER TABLE projects
    ADD CONSTRAINT projects_name_not_blank CHECK (length(trim(name)) BETWEEN 1 AND 160),
    ADD CONSTRAINT projects_key_format CHECK (
        key ~ '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$'
    );
CREATE UNIQUE INDEX uq_projects_key ON projects (key);
CREATE INDEX ix_projects_owner ON projects (owner_id);

CREATE INDEX ix_project_members_user ON project_members (user_id, project_id);

ALTER TABLE prompts
    ADD CONSTRAINT prompts_name_not_blank CHECK (length(trim(name)) BETWEEN 1 AND 160),
    ADD CONSTRAINT prompts_key_format CHECK (
        key ~ '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$'
    ),
    ADD CONSTRAINT uq_prompts_id_project UNIQUE (id, project_id),
    ADD CONSTRAINT uq_prompts_project_key UNIQUE (project_id, key);
CREATE INDEX ix_prompts_project_updated ON prompts (project_id, updated_at DESC, id);

ALTER TABLE prompt_versions
    ADD CONSTRAINT prompt_versions_number_positive CHECK (version_number > 0),
    ADD CONSTRAINT prompt_versions_template_not_blank CHECK (length(template_body) > 0),
    ADD CONSTRAINT prompt_versions_commit_not_blank CHECK (length(trim(commit_message)) > 0),
    ADD CONSTRAINT prompt_versions_variables_array CHECK (jsonb_typeof(variables) = 'array'),
    ADD CONSTRAINT prompt_versions_model_config_object CHECK (jsonb_typeof(model_config) = 'object'),
    ADD CONSTRAINT uq_prompt_versions_id_prompt UNIQUE (id, prompt_id),
    ADD CONSTRAINT uq_prompt_versions_number UNIQUE (prompt_id, version_number),
    ADD CONSTRAINT fk_prompt_versions_parent
        FOREIGN KEY (parent_version_id, prompt_id)
        REFERENCES prompt_versions(id, prompt_id)
        ON DELETE RESTRICT;
CREATE INDEX ix_prompt_versions_history
    ON prompt_versions (prompt_id, version_number DESC, id);
CREATE INDEX ix_prompt_versions_parent ON prompt_versions (parent_version_id);

ALTER TABLE model_pricing
    ADD CONSTRAINT model_pricing_provider_not_blank CHECK (length(trim(provider)) > 0),
    ADD CONSTRAINT model_pricing_model_not_blank CHECK (length(trim(model)) > 0),
    ADD CONSTRAINT model_pricing_nonnegative CHECK (
        input_price_per_million >= 0 AND output_price_per_million >= 0
    ),
    ADD CONSTRAINT model_pricing_valid_window CHECK (
        effective_to IS NULL OR effective_to > effective_from
    ),
    ADD CONSTRAINT model_pricing_no_overlap EXCLUDE USING gist (
        provider WITH =,
        model WITH =,
        tstzrange(effective_from, effective_to, '[)') WITH &&
    );
CREATE INDEX ix_model_pricing_lookup
    ON model_pricing (provider, model, effective_from DESC);

ALTER TABLE budgets
    ADD CONSTRAINT budgets_exactly_one_target CHECK (num_nonnulls(user_id, project_id) = 1),
    ADD CONSTRAINT budgets_limit_nonnegative CHECK (monthly_limit >= 0),
    ADD CONSTRAINT budgets_timezone_not_blank CHECK (length(trim(timezone)) > 0);
CREATE UNIQUE INDEX uq_budgets_user ON budgets (user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_budgets_project ON budgets (project_id) WHERE project_id IS NOT NULL;

ALTER TABLE provider_keys
    ADD CONSTRAINT provider_keys_provider_not_blank CHECK (length(trim(provider)) > 0),
    ADD CONSTRAINT provider_keys_alias_not_blank CHECK (length(trim(alias)) > 0);
CREATE UNIQUE INDEX uq_provider_keys_active_alias
    ON provider_keys (provider, alias) WHERE deactivated_at IS NULL;

ALTER TABLE api_tokens
    ADD CONSTRAINT api_tokens_name_not_blank CHECK (length(trim(name)) > 0),
    ADD CONSTRAINT api_tokens_hash_hex CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT api_tokens_expiry_after_creation CHECK (
        expires_at IS NULL OR expires_at > created_at
    );
CREATE UNIQUE INDEX uq_api_tokens_hash ON api_tokens (token_hash);
CREATE INDEX ix_api_tokens_project_active
    ON api_tokens (project_id, created_at DESC)
    WHERE revoked_at IS NULL;

ALTER TABLE deployments
    ADD CONSTRAINT fk_deployments_prompt_version
        FOREIGN KEY (version_id, prompt_id)
        REFERENCES prompt_versions(id, prompt_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT deployments_pending_only_in_production CHECK (
        environment = 'prod' OR status <> 'pending'
    ),
    ADD CONSTRAINT deployments_rejection_note_required CHECK (
        status <> 'rejected' OR length(trim(review_note)) > 0
    ),
    ADD CONSTRAINT deployments_rollback_reason_required CHECK (
        rollback_of_id IS NULL OR length(trim(rollback_reason)) > 0
    );
CREATE UNIQUE INDEX uq_deployments_one_active
    ON deployments (prompt_id, environment)
    WHERE status = 'active';
CREATE INDEX ix_deployments_pending_prod
    ON deployments (requested_at, id)
    WHERE environment = 'prod' AND status = 'pending';
CREATE INDEX ix_deployments_history
    ON deployments (prompt_id, environment, requested_at DESC, id);

ALTER TABLE runs
    ADD CONSTRAINT runs_tokens_nonnegative CHECK (
        prompt_tokens >= 0 AND completion_tokens >= 0
    ),
    ADD CONSTRAINT runs_latency_nonnegative CHECK (latency_ms >= 0),
    ADD CONSTRAINT runs_cost_nonnegative CHECK (cost >= 0),
    ADD CONSTRAINT runs_input_object CHECK (jsonb_typeof(input_variables) = 'object'),
    ADD CONSTRAINT runs_completed_shape CHECK (
        status <> 'completed' OR (output_text IS NOT NULL AND error_code IS NULL)
    ),
    ADD CONSTRAINT runs_error_shape CHECK (
        status = 'completed' OR error_code IS NOT NULL
    );
CREATE INDEX ix_runs_user_created ON runs (user_id, created_at DESC, id);
CREATE INDEX ix_runs_project_created ON runs (project_id, created_at DESC, id);
CREATE INDEX ix_runs_prompt_created ON runs (prompt_id, created_at DESC, id);
CREATE INDEX ix_runs_version_created ON runs (version_id, created_at DESC, id);
CREATE INDEX ix_runs_status_created ON runs (status, created_at DESC, id);
CREATE INDEX ix_runs_model_created ON runs (provider, model, created_at DESC, id);

CREATE INDEX ix_audit_events_actor_created
    ON audit_events (actor_user_id, created_at DESC, id);
CREATE INDEX ix_audit_events_entity_created
    ON audit_events (entity_type, entity_id, created_at DESC, id);
CREATE INDEX ix_audit_events_action_created
    ON audit_events (action, created_at DESC, id);
