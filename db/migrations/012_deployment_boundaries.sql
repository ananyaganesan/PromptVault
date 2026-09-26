CREATE OR REPLACE FUNCTION rollback_deployment(
    p_prompt_id UUID,
    p_target_version_id UUID,
    p_admin_id UUID,
    p_reason TEXT,
    p_environment deployment_environment DEFAULT 'prod'
)
RETURNS deployments
LANGUAGE plpgsql
AS $$
DECLARE
    previous_id UUID;
    active_version_number INTEGER;
    target_version_number INTEGER;
    created_deployment deployments%ROWTYPE;
BEGIN
    PERFORM 1
    FROM users
    WHERE id = p_admin_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;
    IF length(trim(COALESCE(p_reason, ''))) = 0 THEN
        RAISE EXCEPTION 'rollback_reason_required' USING ERRCODE = '23514';
    END IF;

    PERFORM 1 FROM prompts WHERE id = p_prompt_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT version_number INTO target_version_number
    FROM prompt_versions
    WHERE id = p_target_version_id AND prompt_id = p_prompt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT d.id, pv.version_number
    INTO previous_id, active_version_number
    FROM deployments d
    JOIN prompt_versions pv ON pv.id = d.version_id
    WHERE d.prompt_id = p_prompt_id
      AND d.environment = p_environment
      AND d.status = 'active'
    FOR UPDATE OF d;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no_active_deployment' USING ERRCODE = 'P0002';
    END IF;
    IF target_version_number >= active_version_number THEN
        RAISE EXCEPTION 'invalid_rollback_target' USING ERRCODE = '23514';
    END IF;

    UPDATE deployments SET status = 'rolled_back' WHERE id = previous_id;

    INSERT INTO deployments (
        prompt_id,
        version_id,
        environment,
        status,
        rollback_reason,
        rollback_of_id,
        requested_by,
        reviewed_by,
        reviewed_at,
        activated_at
    )
    VALUES (
        p_prompt_id,
        p_target_version_id,
        p_environment,
        'active',
        p_reason,
        previous_id,
        p_admin_id,
        p_admin_id,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
    RETURNING * INTO created_deployment;
    RETURN created_deployment;
END;
$$;

REVOKE ALL ON FUNCTION rollback_deployment(
    UUID, UUID, UUID, TEXT, deployment_environment
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rollback_deployment(
    UUID, UUID, UUID, TEXT, deployment_environment
) TO promptvault_app;
