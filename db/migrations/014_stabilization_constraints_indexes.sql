ALTER TABLE runs
    ADD CONSTRAINT fk_runs_prompt_project
        FOREIGN KEY (prompt_id, project_id)
        REFERENCES prompts(id, project_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT fk_runs_version_prompt
        FOREIGN KEY (version_id, prompt_id)
        REFERENCES prompt_versions(id, prompt_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT runs_provider_not_blank CHECK (length(trim(provider)) > 0),
    ADD CONSTRAINT runs_model_not_blank CHECK (length(trim(model)) > 0);

ALTER TABLE api_tokens
    ADD CONSTRAINT api_tokens_revocation_complete CHECK (
        (revoked_at IS NULL) = (revoked_by IS NULL)
    ),
    ADD CONSTRAINT api_tokens_revocation_after_creation CHECK (
        revoked_at IS NULL OR revoked_at >= created_at
    );

ALTER TABLE provider_keys
    ADD CONSTRAINT provider_keys_deactivation_after_creation CHECK (
        deactivated_at IS NULL OR deactivated_at >= created_at
    );

ALTER TABLE deployments
    ADD CONSTRAINT uq_deployments_id_prompt_environment
        UNIQUE (id, prompt_id, environment),
    ADD CONSTRAINT fk_deployments_rollback_scope
        FOREIGN KEY (rollback_of_id, prompt_id, environment)
        REFERENCES deployments(id, prompt_id, environment)
        ON DELETE RESTRICT,
    ADD CONSTRAINT deployments_review_metadata_complete CHECK (
        (reviewed_by IS NULL) = (reviewed_at IS NULL)
    ),
    ADD CONSTRAINT deployments_state_timestamps CHECK (
        (
            status IN ('pending', 'cancelled')
            AND reviewed_at IS NULL
            AND activated_at IS NULL
        ) OR (
            status = 'rejected'
            AND reviewed_at IS NOT NULL
            AND activated_at IS NULL
        ) OR (
            status IN ('active', 'superseded', 'rolled_back')
            AND activated_at IS NOT NULL
        )
    ),
    ADD CONSTRAINT deployments_production_activation_reviewed CHECK (
        environment <> 'prod'
        OR status NOT IN ('active', 'superseded', 'rolled_back')
        OR reviewed_at IS NOT NULL
    );

ALTER TABLE audit_events
    ADD CONSTRAINT audit_events_action_not_blank CHECK (length(trim(action)) > 0),
    ADD CONSTRAINT audit_events_entity_type_not_blank CHECK (length(trim(entity_type)) > 0);

CREATE INDEX ix_users_admin_list
    ON users (role, is_active, created_at DESC, id DESC);
CREATE INDEX ix_provider_keys_provider_created
    ON provider_keys (provider, created_at DESC, id DESC);
CREATE INDEX ix_budgets_updated
    ON budgets (updated_at DESC, id DESC);

-- Race-sensitive history and deployment writes are reachable only through
-- their transaction-owning functions. The API role remains a trusted service
-- role for ordinary repository CRUD, but cannot bypass these boundaries.
ALTER FUNCTION create_prompt_version(UUID, UUID, TEXT, JSONB, JSONB, TEXT, UUID)
    SECURITY DEFINER;
ALTER FUNCTION create_prompt_version(UUID, UUID, TEXT, JSONB, JSONB, TEXT, UUID)
    SET search_path = public, pg_temp;
ALTER FUNCTION request_deployment(UUID, deployment_environment, UUID, TEXT)
    SECURITY DEFINER;
ALTER FUNCTION request_deployment(UUID, deployment_environment, UUID, TEXT)
    SET search_path = public, pg_temp;
ALTER FUNCTION review_production_deployment(UUID, UUID, BOOLEAN, TEXT)
    SECURITY DEFINER;
ALTER FUNCTION review_production_deployment(UUID, UUID, BOOLEAN, TEXT)
    SET search_path = public, pg_temp;
ALTER FUNCTION rollback_deployment(UUID, UUID, UUID, TEXT, deployment_environment)
    SECURITY DEFINER;
ALTER FUNCTION rollback_deployment(UUID, UUID, UUID, TEXT, deployment_environment)
    SET search_path = public, pg_temp;

REVOKE INSERT ON prompt_versions FROM promptvault_app;
REVOKE INSERT, UPDATE ON deployments FROM promptvault_app;
