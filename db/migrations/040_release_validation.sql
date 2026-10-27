-- Release evidence is immutable; evaluation progress remains in prompt_evaluations.
CREATE TABLE release_validations (
    id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES prompt_versions(id) ON DELETE CASCADE,
    environment deployment_environment NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    base_deployment_id UUID,
    setup_source JSONB,
    request_payload JSONB NOT NULL,
    configuration JSONB NOT NULL,
    checks JSONB NOT NULL CHECK (jsonb_typeof(checks) = 'array'),
    evaluation_id UUID REFERENCES prompt_evaluations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ix_release_validations_version ON release_validations(version_id, created_at DESC);
ALTER TABLE deployments ADD COLUMN validation_id UUID REFERENCES release_validations(id);
REVOKE ALL ON release_validations FROM PUBLIC;
GRANT SELECT, INSERT ON release_validations TO promptvault_app;

CREATE FUNCTION release_validation_problem(p_id uuid, p_version uuid,
    p_environment deployment_environment) RETURNS text LANGUAGE plpgsql VOLATILE
SET search_path TO public, pg_temp AS $$
DECLARE r release_validations%ROWTYPE; e prompt_evaluations%ROWTYPE;
    current_base uuid; source jsonb; target_prompt uuid;
BEGIN
    SELECT * INTO r FROM release_validations WHERE id=p_id;
    IF NOT FOUND OR r.version_id<>p_version OR r.environment<>p_environment THEN
        RETURN 'blocked: Run release validation for this version and environment.';
    END IF;
    SELECT prompt_id INTO target_prompt FROM prompt_versions WHERE id=p_version;
    SELECT id INTO current_base FROM deployment_context WHERE prompt_id=target_prompt
        AND environment=p_environment AND status='active';
    SELECT configuration INTO source FROM prompt_evaluation_setups WHERE prompt_id=target_prompt;
    IF r.base_deployment_id IS DISTINCT FROM current_base OR r.setup_source IS DISTINCT FROM source
        OR r.created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN
        RETURN 'stale: The active release, saved test suite, or evidence age changed. Validate again.';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(r.checks) c WHERE NOT (c->>'passed')::boolean) THEN
        RETURN 'blocked: Resolve the failed compatibility checks and validate a new version.';
    END IF;
    SELECT * INTO e FROM prompt_evaluations WHERE id=r.evaluation_id;
    IF NOT FOUND THEN RETURN 'blocked: No executable test suite was validated.'; END IF;
    IF e.status IN ('queued','running') THEN RETURN 'running: Release tests are in progress.'; END IF;
    IF e.status<>'completed' THEN RETURN 'blocked: Release tests did not finish. Validate again.'; END IF;
    IF e.configuration IS DISTINCT FROM r.configuration
        OR e.configuration->'version_ids' <> jsonb_build_array(p_version::text)
        OR jsonb_array_length(e.results)<>jsonb_array_length(e.configuration->'cases')
        OR (SELECT count(DISTINCT x->>'case_index') FROM jsonb_array_elements(e.results) x)
            <>jsonb_array_length(e.configuration->'cases')
        OR EXISTS (SELECT 1 FROM jsonb_array_elements(e.results) x
            WHERE x->>'version_id'<>p_version::text OR x->>'error' IS NOT NULL
                OR x->>'weighted_score' IS NULL OR (x->>'weighted_score')::numeric<70
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(x->'checks') c
                    WHERE NOT (c->>'passed')::boolean)) THEN
        RETURN 'blocked: Every test must pass its required checks and score at least 70/100.';
    END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION assert_release_validation(p_id uuid, p_version uuid,
    p_environment deployment_environment) RETURNS void LANGUAGE plpgsql
SET search_path TO public, pg_temp AS $$
DECLARE problem text;
BEGIN
    -- Serialize the evidence check with activation, rollback, and other releases.
    PERFORM 1 FROM prompts WHERE id=(SELECT prompt_id FROM prompt_versions WHERE id=p_version)
        FOR UPDATE;
    -- Lock the saved suite against edits between checking and activation.
    PERFORM 1 FROM prompt_evaluation_setups WHERE prompt_id=(
        SELECT prompt_id FROM prompt_versions WHERE id=p_version) FOR SHARE;
    problem := release_validation_problem(p_id,p_version,p_environment);
    IF problem IS NOT NULL THEN RAISE EXCEPTION 'release_validation: %', problem; END IF;
END $$;

ALTER FUNCTION request_deployment(uuid,deployment_environment,uuid,text)
    RENAME TO request_deployment_without_validation;
REVOKE ALL ON FUNCTION request_deployment_without_validation(uuid,deployment_environment,uuid,text)
    FROM PUBLIC, promptvault_app;
CREATE FUNCTION request_deployment(p_version_id uuid, p_environment deployment_environment,
    p_requested_by uuid, p_request_note text DEFAULT NULL, p_validation_id uuid DEFAULT NULL)
RETURNS deployments LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public, pg_temp AS $$
DECLARE result deployments%ROWTYPE;
BEGIN
    IF NOT EXISTS(SELECT 1 FROM release_validations WHERE id=p_validation_id
        AND created_by=p_requested_by) THEN
        RAISE EXCEPTION 'release_validation: blocked: Validate this release before requesting it.';
    END IF;
    PERFORM assert_release_validation(p_validation_id,p_version_id,p_environment);
    result := request_deployment_without_validation(p_version_id,p_environment,p_requested_by,p_request_note);
    UPDATE deployments SET validation_id=p_validation_id WHERE id=result.id RETURNING * INTO result;
    RETURN result;
END $$;

ALTER FUNCTION review_production_deployment(uuid,uuid,boolean,text)
    RENAME TO review_production_deployment_without_validation;
REVOKE ALL ON FUNCTION review_production_deployment_without_validation(uuid,uuid,boolean,text)
    FROM PUBLIC, promptvault_app;
CREATE FUNCTION review_production_deployment(p_deployment_id uuid, p_admin_id uuid,
    p_approve boolean, p_review_note text DEFAULT NULL) RETURNS deployments
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public, pg_temp AS $$
DECLARE d deployments%ROWTYPE;
BEGIN
    SELECT * INTO d FROM deployments WHERE id=p_deployment_id;
    IF p_approve AND d.status='pending' THEN
        PERFORM assert_release_validation(d.validation_id,d.version_id,d.environment);
    END IF;
    RETURN review_production_deployment_without_validation(p_deployment_id,p_admin_id,p_approve,p_review_note);
END $$;

CREATE FUNCTION replace_release_validation(p_deployment_id uuid,p_validation_id uuid,p_actor uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public, pg_temp AS $$
DECLARE d deployments%ROWTYPE;
BEGIN
    SELECT * INTO d FROM deployments WHERE id=p_deployment_id;
    IF NOT FOUND OR d.requested_by<>p_actor OR d.status<>'pending' THEN
        RAISE EXCEPTION 'release_validation: blocked: Only the requester can revalidate a pending request.';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM release_validations WHERE id=p_validation_id AND created_by=p_actor) THEN
        RAISE EXCEPTION 'release_validation: blocked: Validate this release first.';
    END IF;
    PERFORM assert_release_validation(p_validation_id,d.version_id,d.environment);
    UPDATE deployments SET validation_id=p_validation_id WHERE id=d.id AND status='pending';
    IF NOT FOUND THEN RAISE EXCEPTION 'release_validation: stale: The request changed.'; END IF;
END $$;
REVOKE ALL ON FUNCTION release_validation_problem(uuid,uuid,deployment_environment),
    assert_release_validation(uuid,uuid,deployment_environment),
    request_deployment(uuid,deployment_environment,uuid,text,uuid),
    review_production_deployment(uuid,uuid,boolean,text),replace_release_validation(uuid,uuid,uuid)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION release_validation_problem(uuid,uuid,deployment_environment),
    request_deployment(uuid,deployment_environment,uuid,text,uuid),
    review_production_deployment(uuid,uuid,boolean,text),replace_release_validation(uuid,uuid,uuid)
    TO promptvault_app;
