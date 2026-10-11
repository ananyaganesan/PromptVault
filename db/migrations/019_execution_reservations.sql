CREATE TABLE run_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE RESTRICT,
    version_id UUID NOT NULL REFERENCES prompt_versions(id) ON DELETE RESTRICT,
    idempotency_key VARCHAR(128) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    claim_token UUID NOT NULL,
    estimated_cost NUMERIC(18, 6) NOT NULL,
    actual_cost NUMERIC(18, 6),
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(80),
    run_id UUID,
    run_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, idempotency_key),
    FOREIGN KEY (run_id, run_created_at) REFERENCES runs(id, created_at) ON DELETE RESTRICT,
    CHECK (length(idempotency_key) >= 16),
    CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    CHECK (estimated_cost >= 0),
    CHECK (actual_cost IS NULL OR actual_cost >= 0),
    CHECK (status IN ('reserved', 'completed', 'failed', 'uncertain', 'blocked')),
    CHECK ((run_id IS NULL) = (run_created_at IS NULL))
);

CREATE INDEX run_reservations_budget_user_idx
    ON run_reservations (user_id, created_at)
    WHERE status IN ('reserved', 'uncertain');
CREATE INDEX run_reservations_budget_project_idx
    ON run_reservations (project_id, created_at)
    WHERE status IN ('reserved', 'uncertain');

CREATE FUNCTION reserve_run_execution(
    p_user_id UUID,
    p_project_id UUID,
    p_prompt_id UUID,
    p_version_id UUID,
    p_idempotency_key TEXT,
    p_request_fingerprint TEXT,
    p_claim_token UUID,
    p_estimated_cost NUMERIC,
    p_maximum_concurrent INTEGER,
    p_created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
RETURNS run_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    existing_reservation run_reservations%ROWTYPE;
    created_reservation run_reservations%ROWTYPE;
    budget_record budgets%ROWTYPE;
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
        RETURN existing_reservation;
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
            FROM budgets
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
            FROM runs
            WHERE status = 'completed'
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            SELECT COALESCE(sum(estimated_cost), 0) INTO reserved
            FROM run_reservations
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
        user_id, project_id, prompt_id, version_id, idempotency_key,
        request_fingerprint, claim_token, estimated_cost, status, error_code, created_at
    ) VALUES (
        p_user_id, p_project_id, p_prompt_id, p_version_id, p_idempotency_key,
        p_request_fingerprint, p_claim_token, p_estimated_cost,
        CASE WHEN blocked_error IS NULL THEN 'reserved' ELSE 'blocked' END,
        blocked_error, p_created_at
    )
    RETURNING * INTO created_reservation;
    RETURN created_reservation;
END;
$$;

CREATE FUNCTION finalize_run_execution(
    p_reservation_id UUID,
    p_status TEXT,
    p_actual_cost NUMERIC,
    p_run_id UUID,
    p_run_created_at TIMESTAMPTZ,
    p_error_code TEXT
)
RETURNS run_reservations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    reservation run_reservations%ROWTYPE;
BEGIN
    SELECT * INTO reservation
    FROM run_reservations
    WHERE id = p_reservation_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation_not_found' USING ERRCODE = 'P0002';
    END IF;
    IF reservation.status <> 'reserved' THEN
        IF reservation.status = p_status THEN
            RETURN reservation;
        END IF;
        RAISE EXCEPTION 'reservation_already_finalized' USING ERRCODE = '55000';
    END IF;
    IF p_status NOT IN ('completed', 'failed', 'uncertain') THEN
        RAISE EXCEPTION 'invalid_reservation_status' USING ERRCODE = '22023';
    END IF;
    IF p_status IN ('completed', 'failed') THEN
        IF p_run_id IS NULL OR p_run_created_at IS NULL OR p_actual_cost IS NULL THEN
            RAISE EXCEPTION 'finalized_reservation_requires_run' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM runs
            WHERE id = p_run_id
              AND created_at = p_run_created_at
              AND user_id = reservation.user_id
              AND project_id = reservation.project_id
              AND prompt_id = reservation.prompt_id
              AND version_id = reservation.version_id
              AND cost = p_actual_cost
        ) THEN
            RAISE EXCEPTION 'reservation_run_mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF p_actual_cost IS NOT NULL OR (p_run_id IS NULL) <> (p_run_created_at IS NULL) THEN
        RAISE EXCEPTION 'invalid_uncertain_reservation_result' USING ERRCODE = '23514';
    ELSIF p_run_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM runs
        WHERE id = p_run_id
          AND created_at = p_run_created_at
          AND user_id = reservation.user_id
          AND project_id = reservation.project_id
          AND prompt_id = reservation.prompt_id
          AND version_id = reservation.version_id
    ) THEN
        RAISE EXCEPTION 'reservation_run_mismatch' USING ERRCODE = '23514';
    END IF;

    UPDATE run_reservations
    SET status = p_status,
        actual_cost = p_actual_cost,
        run_id = p_run_id,
        run_created_at = p_run_created_at,
        error_code = p_error_code,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_reservation_id
    RETURNING * INTO reservation;
    RETURN reservation;
END;
$$;

REVOKE ALL ON TABLE run_reservations FROM PUBLIC;
GRANT SELECT ON TABLE run_reservations TO promptvault_app;
REVOKE ALL ON FUNCTION reserve_run_execution(
    UUID, UUID, UUID, UUID, TEXT, TEXT, UUID, NUMERIC, INTEGER, TIMESTAMPTZ
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_run_execution(
    UUID, UUID, UUID, UUID, TEXT, TEXT, UUID, NUMERIC, INTEGER, TIMESTAMPTZ
) TO promptvault_app;
REVOKE ALL ON FUNCTION finalize_run_execution(
    UUID, TEXT, NUMERIC, UUID, TIMESTAMPTZ, TEXT
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finalize_run_execution(
    UUID, TEXT, NUMERIC, UUID, TIMESTAMPTZ, TEXT
) TO promptvault_app;
