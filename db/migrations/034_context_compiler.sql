-- Local Context Compiler snapshots. Raw connector tokens and absolute roots are never persisted.
CREATE TABLE context_compilations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    goal TEXT NOT NULL,
    repository VARCHAR(120) NOT NULL,
    budget TEXT NOT NULL CHECK (budget IN ('fast', 'balanced', 'deep')),
    compiler_version TEXT NOT NULL,
    token_estimate INTEGER NOT NULL CHECK (token_estimate >= 0),
    token_limit INTEGER NOT NULL CHECK (token_limit > 0 AND token_estimate <= token_limit),
    dependencies JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX context_compilations_project_created ON context_compilations(project_id, created_at DESC, id);

CREATE TABLE context_sources (
    compilation_id UUID NOT NULL REFERENCES context_compilations(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    symbols JSONB NOT NULL,
    imports JSONB NOT NULL,
    reason TEXT NOT NULL,
    redacted BOOLEAN NOT NULL,
    included BOOLEAN NOT NULL,
    PRIMARY KEY (compilation_id, path)
);
CREATE TABLE context_warnings (
    compilation_id UUID NOT NULL REFERENCES context_compilations(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    rule TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning')),
    message TEXT NOT NULL,
    paths JSONB NOT NULL,
    PRIMARY KEY (compilation_id, ordinal)
);
CREATE TABLE compiled_prompts (
    compilation_id UUID NOT NULL REFERENCES context_compilations(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('implementation', 'verification', 'review')),
    content TEXT NOT NULL,
    PRIMARY KEY (compilation_id, kind)
);

CREATE FUNCTION protect_context_snapshot() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('app.project_deletion', true) = 'true' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Context Compiler snapshots are immutable' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER context_compilations_immutable BEFORE UPDATE OR DELETE ON context_compilations
    FOR EACH ROW EXECUTE FUNCTION protect_context_snapshot();
CREATE TRIGGER context_sources_immutable BEFORE UPDATE OR DELETE ON context_sources
    FOR EACH ROW EXECUTE FUNCTION protect_context_snapshot();
CREATE TRIGGER context_warnings_immutable BEFORE UPDATE OR DELETE ON context_warnings
    FOR EACH ROW EXECUTE FUNCTION protect_context_snapshot();
CREATE TRIGGER compiled_prompts_immutable BEFORE UPDATE OR DELETE ON compiled_prompts
    FOR EACH ROW EXECUTE FUNCTION protect_context_snapshot();

GRANT SELECT, INSERT ON context_compilations, context_sources, context_warnings, compiled_prompts TO promptvault_app;
