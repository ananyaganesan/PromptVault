CREATE OR REPLACE FUNCTION admin_update_user(
    p_target_user_id UUID,
    p_actor_user_id UUID,
    p_role user_role,
    p_role_set BOOLEAN,
    p_is_active BOOLEAN,
    p_active_set BOOLEAN
)
RETURNS users
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    target users%ROWTYPE;
    resulting_role user_role;
    resulting_active BOOLEAN;
    updated users%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('promptvault_admin_user_transition'));

    PERFORM 1 FROM users
    WHERE id = p_actor_user_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO target FROM users WHERE id = p_target_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'user_not_found' USING ERRCODE = 'P0002';
    END IF;

    resulting_role := CASE WHEN p_role_set THEN p_role ELSE target.role END;
    resulting_active := CASE WHEN p_active_set THEN p_is_active ELSE target.is_active END;

    IF target.role = 'admin' AND target.is_active
       AND (resulting_role <> 'admin' OR NOT resulting_active)
       AND NOT EXISTS (
           SELECT 1 FROM users
           WHERE id <> target.id AND role = 'admin' AND is_active
       ) THEN
        RAISE EXCEPTION 'last_admin' USING ERRCODE = '23514';
    END IF;

    IF target.id = p_actor_user_id
       AND target.role = 'admin' AND target.is_active
       AND (resulting_role <> 'admin' OR NOT resulting_active) THEN
        RAISE EXCEPTION 'self_lockout' USING ERRCODE = '23514';
    END IF;

    UPDATE users
    SET role = resulting_role, is_active = resulting_active
    WHERE id = target.id
    RETURNING * INTO updated;
    RETURN updated;
END;
$$;

REVOKE ALL ON FUNCTION admin_update_user(
    UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_update_user(
    UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN
) TO promptvault_app;

REVOKE UPDATE ON users FROM promptvault_app;
GRANT DELETE ON budgets TO promptvault_app;

CREATE OR REPLACE FUNCTION admin_refresh_reporting_views(
    p_actor_user_id UUID,
    p_request_id TEXT
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    completed_at TIMESTAMPTZ;
BEGIN
    PERFORM 1 FROM users
    WHERE id = p_actor_user_id AND role = 'admin' AND is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('promptvault_refresh_reporting_views'));
    REFRESH MATERIALIZED VIEW organization_monthly_metrics;
    REFRESH MATERIALIZED VIEW user_monthly_metrics;
    completed_at := CURRENT_TIMESTAMP;

    INSERT INTO audit_events (
        actor_user_id, action, entity_type, before_data, after_data, request_id
    ) VALUES (
        p_actor_user_id,
        'refresh',
        'materialized_views',
        NULL,
        jsonb_build_object(
            'views', jsonb_build_array(
                'organization_monthly_metrics', 'user_monthly_metrics'
            ),
            'completed_at', completed_at
        ),
        nullif(p_request_id, '')
    );
    RETURN completed_at;
END;
$$;

CREATE OR REPLACE FUNCTION admin_create_next_run_partition(
    p_actor_user_id UUID,
    p_request_id TEXT
)
RETURNS TABLE(partition_name TEXT, already_existed BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    target_month DATE;
BEGIN
    PERFORM 1 FROM users
    WHERE id = p_actor_user_id AND role = 'admin' AND is_active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext('promptvault_run_partition_creation'));
    target_month := (date_trunc('month', current_date) + INTERVAL '1 month')::date;
    partition_name := format('runs_%s', to_char(target_month, 'YYYY_MM'));
    already_existed := to_regclass(partition_name) IS NOT NULL;
    PERFORM create_run_partition(target_month);

    INSERT INTO audit_events (
        actor_user_id, action, entity_type, before_data, after_data, request_id
    ) VALUES (
        p_actor_user_id,
        'create',
        'run_partitions',
        NULL,
        jsonb_build_object(
            'partition_name', partition_name,
            'already_existed', already_existed
        ),
        nullif(p_request_id, '')
    );
    RETURN NEXT;
END;
$$;

REVOKE ALL ON FUNCTION admin_refresh_reporting_views(UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION admin_create_next_run_partition(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_refresh_reporting_views(UUID, TEXT) TO promptvault_app;
GRANT EXECUTE ON FUNCTION admin_create_next_run_partition(UUID, TEXT) TO promptvault_app;
