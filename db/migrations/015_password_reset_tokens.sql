CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_password_reset_tokens_user_active
    ON password_reset_tokens (user_id, expires_at DESC)
    WHERE used_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO promptvault_app;
