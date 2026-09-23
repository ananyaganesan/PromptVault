DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'promptvault_app') THEN
        CREATE ROLE promptvault_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'promptvault_readonly') THEN
        CREATE ROLE promptvault_readonly NOLOGIN;
    END IF;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO promptvault_app, promptvault_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO promptvault_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO promptvault_app;

GRANT SELECT ON
    projects,
    project_members,
    prompts,
    prompt_versions,
    model_pricing,
    budgets,
    deployments,
    runs,
    audit_events,
    prompt_version_lineage,
    deployment_history,
    monthly_costs,
    organization_monthly_metrics,
    user_monthly_metrics
TO promptvault_readonly;
GRANT SELECT (id, email, display_name, role, is_active, created_at, updated_at)
    ON users TO promptvault_readonly;
GRANT SELECT (id, provider, alias, created_by, created_at, deactivated_at)
    ON provider_keys TO promptvault_readonly;
GRANT SELECT (
    id, project_id, name, token_prefix, created_by, created_at, expires_at, revoked_at, revoked_by
) ON api_tokens TO promptvault_readonly;

GRANT INSERT, UPDATE ON users TO promptvault_app;
GRANT INSERT, UPDATE, DELETE ON projects, project_members, prompts TO promptvault_app;
GRANT INSERT ON prompt_versions, runs, audit_events, model_pricing TO promptvault_app;
GRANT INSERT, UPDATE ON deployments, budgets, provider_keys, api_tokens TO promptvault_app;

GRANT EXECUTE ON FUNCTION create_prompt_version(
    UUID, UUID, TEXT, JSONB, JSONB, TEXT, UUID
) TO promptvault_app;
GRANT EXECUTE ON FUNCTION request_deployment(
    UUID, deployment_environment, UUID, TEXT
) TO promptvault_app;
GRANT EXECUTE ON FUNCTION review_production_deployment(
    UUID, UUID, BOOLEAN, TEXT
) TO promptvault_app;
GRANT EXECUTE ON FUNCTION rollback_deployment(
    UUID, UUID, UUID, TEXT, deployment_environment
) TO promptvault_app;
GRANT EXECUTE ON FUNCTION record_run(
    UUID, UUID, UUID, UUID, run_status, TEXT, TEXT, JSONB, TEXT,
    INTEGER, INTEGER, INTEGER, NUMERIC, TEXT, TEXT, TIMESTAMPTZ
) TO promptvault_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO promptvault_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO promptvault_app;
