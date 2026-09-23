CREATE OR REPLACE FUNCTION create_prompt_version(
    p_prompt_id UUID,
    p_parent_version_id UUID,
    p_template_body TEXT,
    p_variables JSONB,
    p_model_config JSONB,
    p_commit_message TEXT,
    p_created_by UUID
)
RETURNS prompt_versions
LANGUAGE plpgsql
AS $$
DECLARE
    next_version INTEGER;
    existing_versions INTEGER;
    created_version prompt_versions%ROWTYPE;
BEGIN
    PERFORM 1 FROM prompts WHERE id = p_prompt_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'prompt_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT count(*), COALESCE(max(version_number), 0) + 1
    INTO existing_versions, next_version
    FROM prompt_versions
    WHERE prompt_id = p_prompt_id;

    IF existing_versions = 0 AND p_parent_version_id IS NOT NULL THEN
        RAISE EXCEPTION 'initial_version_cannot_have_parent' USING ERRCODE = '23514';
    END IF;
    IF existing_versions > 0 AND NOT EXISTS (
        SELECT 1 FROM prompt_versions
        WHERE id = p_parent_version_id AND prompt_id = p_prompt_id
    ) THEN
        RAISE EXCEPTION 'invalid_parent_version' USING ERRCODE = '23514';
    END IF;

    INSERT INTO prompt_versions (
        prompt_id,
        version_number,
        parent_version_id,
        template_body,
        variables,
        model_config,
        commit_message,
        created_by
    )
    VALUES (
        p_prompt_id,
        next_version,
        p_parent_version_id,
        p_template_body,
        p_variables,
        p_model_config,
        p_commit_message,
        p_created_by
    )
    RETURNING * INTO created_version;
    RETURN created_version;
END;
$$;

CREATE OR REPLACE FUNCTION request_deployment(
    p_version_id UUID,
    p_environment deployment_environment,
    p_requested_by UUID,
    p_request_note TEXT DEFAULT NULL
)
RETURNS deployments
LANGUAGE plpgsql
AS $$
DECLARE
    target_version prompt_versions%ROWTYPE;
    created_deployment deployments%ROWTYPE;
    initial_status deployment_status;
BEGIN
    SELECT pv.* INTO target_version
    FROM prompt_versions AS pv
    WHERE pv.id = p_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    PERFORM 1 FROM prompts WHERE id = target_version.prompt_id FOR UPDATE;
    initial_status := CASE WHEN p_environment = 'prod' THEN 'pending' ELSE 'active' END;

    IF initial_status = 'active' THEN
        UPDATE deployments
        SET status = 'superseded'
        WHERE prompt_id = target_version.prompt_id
          AND environment = p_environment
          AND status = 'active';
    END IF;

    INSERT INTO deployments (
        prompt_id,
        version_id,
        environment,
        status,
        request_note,
        requested_by,
        activated_at
    )
    VALUES (
        target_version.prompt_id,
        target_version.id,
        p_environment,
        initial_status,
        p_request_note,
        p_requested_by,
        CASE WHEN initial_status = 'active' THEN CURRENT_TIMESTAMP END
    )
    RETURNING * INTO created_deployment;
    RETURN created_deployment;
END;
$$;

CREATE OR REPLACE FUNCTION review_production_deployment(
    p_deployment_id UUID,
    p_admin_id UUID,
    p_approve BOOLEAN,
    p_review_note TEXT DEFAULT NULL
)
RETURNS deployments
LANGUAGE plpgsql
AS $$
DECLARE
    deployment_record deployments%ROWTYPE;
BEGIN
    PERFORM 1
    FROM users
    WHERE id = p_admin_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO deployment_record
    FROM deployments
    WHERE id = p_deployment_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'deployment_not_found' USING ERRCODE = 'P0002';
    END IF;
    IF deployment_record.environment <> 'prod' OR deployment_record.status <> 'pending' THEN
        RAISE EXCEPTION 'already_reviewed' USING ERRCODE = '40001';
    END IF;
    IF NOT p_approve AND length(trim(COALESCE(p_review_note, ''))) = 0 THEN
        RAISE EXCEPTION 'rejection_note_required' USING ERRCODE = '23514';
    END IF;

    IF p_approve THEN
        PERFORM 1 FROM prompts WHERE id = deployment_record.prompt_id FOR UPDATE;
        UPDATE deployments
        SET status = 'superseded'
        WHERE prompt_id = deployment_record.prompt_id
          AND environment = 'prod'
          AND status = 'active';
        UPDATE deployments
        SET status = 'active',
            review_note = p_review_note,
            reviewed_by = p_admin_id,
            reviewed_at = CURRENT_TIMESTAMP,
            activated_at = CURRENT_TIMESTAMP
        WHERE id = p_deployment_id
        RETURNING * INTO deployment_record;
    ELSE
        UPDATE deployments
        SET status = 'rejected',
            review_note = p_review_note,
            reviewed_by = p_admin_id,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = p_deployment_id
        RETURNING * INTO deployment_record;
    END IF;
    RETURN deployment_record;
END;
$$;

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
    IF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM prompt_versions
        WHERE id = p_target_version_id AND prompt_id = p_prompt_id
    ) THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT id INTO previous_id
    FROM deployments
    WHERE prompt_id = p_prompt_id
      AND environment = p_environment
      AND status = 'active'
    FOR UPDATE;

    IF previous_id IS NOT NULL THEN
        UPDATE deployments SET status = 'rolled_back' WHERE id = previous_id;
    END IF;

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

CREATE OR REPLACE FUNCTION record_run(
    p_user_id UUID,
    p_project_id UUID,
    p_prompt_id UUID,
    p_version_id UUID,
    p_status run_status,
    p_provider TEXT,
    p_model TEXT,
    p_input_variables JSONB,
    p_output_text TEXT,
    p_prompt_tokens INTEGER,
    p_completion_tokens INTEGER,
    p_latency_ms INTEGER,
    p_cost NUMERIC,
    p_error_code TEXT,
    p_request_id TEXT,
    p_created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
RETURNS runs
LANGUAGE plpgsql
AS $$
DECLARE
    budget_record budgets%ROWTYPE;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    spent NUMERIC(18, 6);
    final_status run_status := p_status;
    final_cost NUMERIC(18, 6) := p_cost;
    final_error TEXT := p_error_code;
    created_run runs%ROWTYPE;
BEGIN
    IF p_status = 'completed' THEN
        FOR budget_record IN
            SELECT *
            FROM budgets
            WHERE user_id = p_user_id OR project_id = p_project_id
            ORDER BY id
            FOR UPDATE
        LOOP
            month_start := date_trunc(
                'month',
                p_created_at AT TIME ZONE budget_record.timezone
            ) AT TIME ZONE budget_record.timezone;
            month_end := month_start + INTERVAL '1 month';

            SELECT COALESCE(sum(cost), 0) INTO spent
            FROM runs
            WHERE status = 'completed'
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            IF spent + p_cost > budget_record.monthly_limit THEN
                final_status := 'blocked';
                final_cost := 0;
                final_error := 'budget_exceeded';
                EXIT;
            END IF;
        END LOOP;
    END IF;

    INSERT INTO runs (
        user_id,
        project_id,
        prompt_id,
        version_id,
        status,
        provider,
        model,
        input_variables,
        output_text,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        cost,
        error_code,
        request_id,
        created_at
    )
    VALUES (
        p_user_id,
        p_project_id,
        p_prompt_id,
        p_version_id,
        final_status,
        p_provider,
        p_model,
        p_input_variables,
        CASE WHEN final_status = 'completed' THEN p_output_text END,
        p_prompt_tokens,
        p_completion_tokens,
        p_latency_ms,
        final_cost,
        final_error,
        p_request_id,
        p_created_at
    )
    RETURNING * INTO created_run;
    RETURN created_run;
END;
$$;
