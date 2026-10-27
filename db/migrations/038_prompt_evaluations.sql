-- Evaluation artifacts are separate from immutable prompt versions and deployments.
CREATE TABLE prompt_evaluation_setups (
    prompt_id UUID PRIMARY KEY REFERENCES prompts(id) ON DELETE CASCADE,
    configuration JSONB NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    updated_by UUID NOT NULL REFERENCES users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE prompt_evaluations (
    id UUID PRIMARY KEY,
    prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    configuration JSONB NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    version_snapshots JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
        ('queued','running','completed','failed','interrupted')),
    results JSONB NOT NULL DEFAULT '[]'::jsonb,
    ranking JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendation TEXT NOT NULL DEFAULT '',
    winner_version_id UUID REFERENCES prompt_versions(id) ON DELETE SET NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_prompt_evaluations_prompt ON prompt_evaluations(prompt_id, created_at DESC);
CREATE INDEX ix_prompt_evaluations_actor ON prompt_evaluations(created_by, status);
CREATE TABLE evaluation_calls (
    id UUID PRIMARY KEY,
    evaluation_id UUID REFERENCES prompt_evaluations(id) ON DELETE CASCADE,
    prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('judge','suggest','improve')),
    provider TEXT NOT NULL DEFAULT 'gemini' CHECK (provider = 'gemini'),
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed','interrupted')),
    request_text TEXT NOT NULL,
    output_text TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ
);
CREATE INDEX ix_evaluation_calls_actor ON evaluation_calls(user_id, created_at DESC);
CREATE INDEX ix_evaluation_calls_evaluation ON evaluation_calls(evaluation_id);
REVOKE ALL ON prompt_evaluation_setups, prompt_evaluations, evaluation_calls FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON prompt_evaluation_setups, prompt_evaluations, evaluation_calls
    TO promptvault_app;
