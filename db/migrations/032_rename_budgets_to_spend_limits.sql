-- The rows represent enforced monthly spend ceilings, not allocated funds.
-- Keep the public budget API stable while giving the physical relation a precise name.
ALTER TABLE budgets RENAME TO spend_limits;

ALTER TABLE spend_limits RENAME CONSTRAINT budgets_pkey TO spend_limits_pkey;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_exactly_one_target TO spend_limits_exactly_one_target;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_limit_nonnegative TO spend_limits_limit_nonnegative;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_timezone_not_blank TO spend_limits_timezone_not_blank;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_user_id_fkey TO spend_limits_user_id_fkey;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_project_id_fkey TO spend_limits_project_id_fkey;
ALTER TABLE spend_limits RENAME CONSTRAINT budgets_created_by_fkey TO spend_limits_created_by_fkey;

ALTER INDEX uq_budgets_user RENAME TO uq_spend_limits_user;
ALTER INDEX uq_budgets_project RENAME TO uq_spend_limits_project;
ALTER INDEX ix_budgets_updated RENAME TO ix_spend_limits_updated;

ALTER TRIGGER budgets_set_updated_at ON spend_limits RENAME TO spend_limits_set_updated_at;
ALTER TRIGGER budgets_audit ON spend_limits RENAME TO spend_limits_audit;

CREATE OR REPLACE FUNCTION public.record_run(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_status run_status, p_provider text, p_model text, p_input_variables jsonb, p_output_text text, p_prompt_tokens integer, p_completion_tokens integer, p_latency_ms integer, p_cost numeric, p_error_code text, p_request_id text, p_created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP)
 RETURNS runs
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    budget_record spend_limits%ROWTYPE;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    spent NUMERIC(18, 6);
    final_status run_status := p_status;
    final_cost NUMERIC(18, 6) := p_cost;
    final_error TEXT := p_error_code;
    created_run runs%ROWTYPE;
BEGIN
    IF p_input_variables IS NULL OR jsonb_typeof(p_input_variables)<>'object'
       OR EXISTS(SELECT 1 FROM jsonb_each(p_input_variables) i WHERE jsonb_typeof(i.value)<>'string')
    THEN RAISE EXCEPTION 'invalid_run_inputs' USING ERRCODE='23514'; END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM prompt_versions pv
        JOIN prompts p ON p.id = pv.prompt_id
        WHERE pv.id = p_version_id
          AND pv.prompt_id = p_prompt_id
          AND p.project_id = p_project_id
          AND pv.provider = p_provider
          AND pv.model = p_model
    ) THEN
        RAISE EXCEPTION 'invalid_run_target' USING ERRCODE = '23503';
    END IF;

    IF p_status = 'completed' THEN
        FOR budget_record IN
            SELECT *
            FROM spend_limits
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
            FROM run_context
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
        version_id,
        status,
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
        p_version_id,
        final_status,
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
    INSERT INTO run_inputs(run_id,run_created_at,name,value)
    SELECT created_run.id,created_run.created_at,key,value
    FROM jsonb_each_text(p_input_variables);
    RETURN created_run;
END;
$function$;

CREATE OR REPLACE FUNCTION public.reserve_run_execution(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_idempotency_key text, p_request_fingerprint text, p_claim_token uuid, p_estimated_cost numeric, p_maximum_concurrent integer, p_created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP)
 RETURNS reservation_context
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    existing_reservation run_reservations%ROWTYPE;
    created_reservation run_reservations%ROWTYPE;
    budget_record spend_limits%ROWTYPE;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    spent NUMERIC(18, 6);
    reserved NUMERIC(18, 6);
    blocked_error TEXT;
BEGIN
    IF p_estimated_cost < 0 OR p_maximum_concurrent < 1 THEN
        RAISE EXCEPTION 'invalid_reservation_limits' USING ERRCODE = '22023';
    END IF;

    PERFORM 1 FROM users WHERE id = p_user_id AND is_active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'inactive_user' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO existing_reservation
    FROM run_reservations
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;
    IF FOUND THEN
        IF existing_reservation.request_fingerprint <> p_request_fingerprint THEN
            RAISE EXCEPTION 'idempotency_conflict';
        END IF;
        RETURN (SELECT context FROM reservation_context context WHERE context.id=existing_reservation.id);
    END IF;

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

    IF (
        SELECT count(*)
        FROM run_reservations
        WHERE user_id = p_user_id AND status = 'reserved'
    ) >= p_maximum_concurrent THEN
        blocked_error := 'concurrency_limit';
    END IF;

    IF blocked_error IS NULL THEN
        FOR budget_record IN
            SELECT *
            FROM spend_limits
            WHERE user_id = p_user_id OR project_id = p_project_id
            ORDER BY id
            FOR UPDATE
        LOOP
            month_start := date_trunc(
                'month', p_created_at AT TIME ZONE budget_record.timezone
            ) AT TIME ZONE budget_record.timezone;
            month_end := (
                date_trunc('month', p_created_at AT TIME ZONE budget_record.timezone)
                + INTERVAL '1 month'
            ) AT TIME ZONE budget_record.timezone;

            SELECT COALESCE(sum(cost), 0) INTO spent
            FROM run_context
            WHERE status = 'completed'
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            SELECT COALESCE(sum(estimated_cost), 0) INTO reserved
            FROM reservation_context
            WHERE status IN ('reserved', 'uncertain')
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            IF spent + reserved + p_estimated_cost > budget_record.monthly_limit THEN
                blocked_error := 'budget_exceeded';
                EXIT;
            END IF;
        END LOOP;
    END IF;

    INSERT INTO run_reservations (
        user_id, version_id, idempotency_key,
        request_fingerprint, claim_token, estimated_cost, status, error_code, created_at
    ) VALUES (
        p_user_id, p_version_id, p_idempotency_key,
        p_request_fingerprint, p_claim_token, p_estimated_cost,
        CASE WHEN blocked_error IS NULL THEN 'reserved' ELSE 'blocked' END,
        blocked_error, p_created_at
    )
    RETURNING * INTO created_reservation;
    RETURN (SELECT context FROM reservation_context context WHERE context.id=created_reservation.id);
END;
$function$;
