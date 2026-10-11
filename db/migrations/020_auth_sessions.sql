CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT auth_sessions_valid_lifetime CHECK (expires_at > issued_at),
    CONSTRAINT auth_sessions_revocation_consistent CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)
    )
);

CREATE INDEX ix_auth_sessions_user_active
    ON auth_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE INDEX ix_auth_sessions_expired_cleanup
    ON auth_sessions (expires_at)
    WHERE revoked_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions TO promptvault_app;

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

    UPDATE auth_sessions
    SET revoked_at = CURRENT_TIMESTAMP,
        revocation_reason = 'password_reset'
    WHERE user_id = v_user_id
      AND revoked_at IS NULL;

    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION consume_password_reset_token(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consume_password_reset_token(TEXT, TEXT) TO promptvault_app;
