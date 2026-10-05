CREATE OR REPLACE FUNCTION consume_password_reset_token(
    p_token_hash TEXT,
    p_password_hash TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    UPDATE password_reset_tokens
    SET used_at = CURRENT_TIMESTAMP
    WHERE token_hash = p_token_hash
      AND used_at IS NULL
      AND expires_at > CURRENT_TIMESTAMP
    RETURNING user_id INTO v_user_id;

    IF v_user_id IS NULL THEN
        RETURN FALSE;
    END IF;

    UPDATE users
    SET password_hash = p_password_hash,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = v_user_id;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION consume_password_reset_token(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consume_password_reset_token(TEXT, TEXT) TO promptvault_app;
