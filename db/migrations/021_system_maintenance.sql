CREATE OR REPLACE PROCEDURE perform_system_maintenance(
    p_stale_reservation_age INTERVAL DEFAULT INTERVAL '10 minutes',
    p_security_retention INTERVAL DEFAULT INTERVAL '30 days',
    p_idempotency_retention INTERVAL DEFAULT INTERVAL '30 days'
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_stale_reservation_age <= INTERVAL '0 seconds'
       OR p_security_retention <= INTERVAL '0 seconds'
       OR p_idempotency_retention <= INTERVAL '0 seconds' THEN
        RAISE EXCEPTION 'maintenance intervals must be positive' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('promptvault_system_maintenance'));

    -- A process can disappear after sending a paid request but before recording
    -- the response. Preserve the reserved amount and require operator review.
    UPDATE run_reservations
    SET status = 'uncertain',
        error_code = 'execution_interrupted',
        updated_at = CURRENT_TIMESTAMP
    WHERE status = 'reserved'
      AND created_at < CURRENT_TIMESTAMP - p_stale_reservation_age;

    DELETE FROM auth_sessions
    WHERE expires_at < CURRENT_TIMESTAMP - p_security_retention
       OR revoked_at < CURRENT_TIMESTAMP - p_security_retention;

    DELETE FROM password_reset_tokens
    WHERE (used_at IS NOT NULL AND used_at < CURRENT_TIMESTAMP - p_security_retention)
       OR expires_at < CURRENT_TIMESTAMP - p_security_retention;

    DELETE FROM run_reservations
    WHERE status IN ('completed', 'failed', 'blocked')
      AND updated_at < CURRENT_TIMESTAMP - p_idempotency_retention;

    PERFORM create_run_partition(
        (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date
    );

    REFRESH MATERIALIZED VIEW organization_monthly_metrics;
    REFRESH MATERIALIZED VIEW user_monthly_metrics;
END;
$$;

REVOKE ALL ON PROCEDURE perform_system_maintenance(INTERVAL, INTERVAL, INTERVAL)
    FROM PUBLIC;
