-- Invitations grant no access until accepted by the recipient.
CREATE TABLE project_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invited_by UUID NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at),
    accepted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CHECK (accepted_at IS NULL OR revoked_at IS NULL)
);
CREATE UNIQUE INDEX ix_project_invitations_pending
ON project_invitations(project_id, user_id)
WHERE accepted_at IS NULL AND revoked_at IS NULL;
CREATE INDEX ix_project_invitations_user ON project_invitations(user_id);
CREATE TRIGGER project_invitations_audit
AFTER INSERT OR UPDATE OR DELETE ON project_invitations
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
GRANT SELECT, INSERT, UPDATE ON project_invitations TO promptvault_app;
