-- Keep only Argon2 hashes, including the password in use when history is enabled.
CREATE TABLE password_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, password_hash)
);

INSERT INTO password_history (user_id, password_hash)
SELECT id, password_hash FROM users;

CREATE FUNCTION record_password_history()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO password_history (user_id, password_hash)
        VALUES (OLD.id, OLD.password_hash)
        ON CONFLICT (user_id, password_hash) DO NOTHING;
    END IF;
    INSERT INTO password_history (user_id, password_hash)
    VALUES (NEW.id, NEW.password_hash)
    ON CONFLICT (user_id, password_hash) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_password_history
AFTER INSERT OR UPDATE OF password_hash ON users
FOR EACH ROW EXECUTE FUNCTION record_password_history();

REVOKE ALL ON FUNCTION record_password_history() FROM PUBLIC;
GRANT SELECT ON password_history TO promptvault_app;
