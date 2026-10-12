-- Narrow self-profile writes without granting direct UPDATE on users.
CREATE FUNCTION update_self_display_name(
    p_user_id UUID, p_session_id UUID, p_display_name TEXT, p_request_id TEXT
)
RETURNS users
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    updated users%ROWTYPE;
BEGIN
    IF length(trim(p_display_name)) NOT BETWEEN 1 AND 120 THEN
        RAISE EXCEPTION 'invalid_display_name' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM users WHERE id = p_user_id AND is_active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invalid_session' USING ERRCODE = '42501';
    END IF;
    PERFORM 1 FROM auth_sessions
    WHERE id = p_session_id AND user_id = p_user_id
      AND revoked_at IS NULL AND expires_at > clock_timestamp()
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'invalid_session' USING ERRCODE = '42501';
    END IF;
    PERFORM set_config('app.user_id', p_user_id::text, true);
    PERFORM set_config('app.request_id', p_request_id, true);
    UPDATE users SET display_name = trim(p_display_name)
    WHERE id = p_user_id RETURNING * INTO updated;
    RETURN updated;
END;
$$;
REVOKE ALL ON FUNCTION update_self_display_name(UUID, UUID, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION update_self_display_name(UUID, UUID, TEXT, TEXT) TO promptvault_app;
