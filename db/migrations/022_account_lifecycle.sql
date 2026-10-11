CREATE OR REPLACE FUNCTION close_user_account(
    p_user_id UUID,
    p_password_hash TEXT,
    p_request_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    target users%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('promptvault_admin_user_transition'));
    SELECT * INTO target FROM users WHERE id = p_user_id FOR UPDATE;
    IF NOT FOUND OR NOT target.is_active THEN
        RETURN FALSE;
    END IF;
    IF target.role = 'admin' AND NOT EXISTS (
        SELECT 1 FROM users
        WHERE id <> target.id AND role = 'admin' AND is_active
    ) THEN
        RAISE EXCEPTION 'last_admin' USING ERRCODE = '23514';
    END IF;

    PERFORM set_config('app.user_id', target.id::text, true);
    PERFORM set_config('app.request_id', COALESCE(p_request_id, ''), true);

    UPDATE auth_sessions
    SET revoked_at = CURRENT_TIMESTAMP, revocation_reason = 'account_closed'
    WHERE user_id = target.id AND revoked_at IS NULL;
    DELETE FROM password_reset_tokens WHERE user_id = target.id;
    UPDATE api_tokens
    SET revoked_at = CURRENT_TIMESTAMP, revoked_by = target.id
    WHERE created_by = target.id AND revoked_at IS NULL;
    UPDATE provider_keys
    SET deactivated_at = CURRENT_TIMESTAMP
    WHERE created_by = target.id AND deactivated_at IS NULL;
    UPDATE users
    SET email = ('deleted+' || replace(target.id::text, '-', '') || '@invalid.promptvault')::citext,
        display_name = 'Deleted User',
        password_hash = p_password_hash,
        role = 'user',
        is_active = FALSE,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = target.id;

    INSERT INTO audit_events (
        actor_user_id, action, entity_type, entity_id, after_data, request_id
    ) VALUES (
        target.id, 'close', 'accounts', target.id,
        jsonb_build_object('pseudonymized', true, 'closed_at', CURRENT_TIMESTAMP),
        nullif(p_request_id, '')
    );
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION close_user_account(UUID, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION close_user_account(UUID, TEXT, TEXT) TO promptvault_app;
