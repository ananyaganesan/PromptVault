-- Add one-use email verification for newly registered accounts.
ALTER TABLE users
    ADD COLUMN email_verified_at TIMESTAMPTZ;

UPDATE users
SET email_verified_at = CURRENT_TIMESTAMP
WHERE email_verified_at IS NULL;

CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_email_verification_tokens_user_active
    ON email_verification_tokens (user_id, created_at DESC)
    WHERE used_at IS NULL;

CREATE FUNCTION confirm_email_verification(p_token_hash CHAR(64))
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT user_id INTO v_user_id
    FROM email_verification_tokens
    WHERE token_hash = p_token_hash
      AND used_at IS NULL
      AND expires_at > clock_timestamp()
    FOR UPDATE;

    IF v_user_id IS NULL THEN
        RETURN FALSE;
    END IF;

    PERFORM 1
    FROM users
    WHERE id = v_user_id
      AND is_active
      AND email_verified_at IS NULL
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    UPDATE users
    SET email_verified_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = v_user_id;

    UPDATE email_verification_tokens
    SET used_at = CURRENT_TIMESTAMP
    WHERE user_id = v_user_id
      AND used_at IS NULL;

    RETURN TRUE;
END;
$$;

CREATE FUNCTION purge_inactive_user_email_verification_tokens()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.is_active AND NOT NEW.is_active THEN
        DELETE FROM email_verification_tokens WHERE user_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_purge_email_verification_tokens
AFTER UPDATE OF is_active ON users
FOR EACH ROW EXECUTE FUNCTION purge_inactive_user_email_verification_tokens();

REVOKE ALL ON email_verification_tokens FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON email_verification_tokens TO promptvault_app;

REVOKE ALL ON FUNCTION confirm_email_verification(CHAR(64)) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION confirm_email_verification(CHAR(64)) TO promptvault_app;

REVOKE ALL ON FUNCTION purge_inactive_user_email_verification_tokens() FROM PUBLIC;
