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
SECURITY DEFINER
SET search_path = public, pg_temp
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
    IF NOT EXISTS (
        SELECT 1
        FROM prompt_versions pv
        JOIN prompts p ON p.id = pv.prompt_id
        WHERE pv.id = p_version_id
          AND pv.prompt_id = p_prompt_id
          AND p.project_id = p_project_id
    ) THEN
        RAISE EXCEPTION 'invalid_run_target' USING ERRCODE = '23503';
    END IF;

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
            month_end := (
                date_trunc('month', p_created_at AT TIME ZONE budget_record.timezone)
                + INTERVAL '1 month'
            ) AT TIME ZONE budget_record.timezone;

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

REVOKE INSERT ON runs FROM promptvault_app;
DO $$
DECLARE
    partition_name REGCLASS;
BEGIN
    FOR partition_name IN
        SELECT inhrelid::regclass
        FROM pg_inherits
        WHERE inhparent = 'runs'::regclass
    LOOP
        EXECUTE format('REVOKE INSERT ON TABLE %s FROM promptvault_app', partition_name);
    END LOOP;
END;
$$;
REVOKE ALL ON FUNCTION record_run(
    UUID, UUID, UUID, UUID, run_status, TEXT, TEXT, JSONB, TEXT,
    INTEGER, INTEGER, INTEGER, NUMERIC, TEXT, TEXT, TIMESTAMPTZ
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_run(
    UUID, UUID, UUID, UUID, run_status, TEXT, TEXT, JSONB, TEXT,
    INTEGER, INTEGER, INTEGER, NUMERIC, TEXT, TEXT, TIMESTAMPTZ
) TO promptvault_app;
