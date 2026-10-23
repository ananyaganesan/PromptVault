-- Design: docs/database-refactor-design.md (written before this migration).
-- Preserve historical rows; derive immutable context rather than storing it repeatedly.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM runs r JOIN prompt_versions v ON v.id=r.version_id
 JOIN prompts p ON p.id=v.prompt_id WHERE r.prompt_id<>v.prompt_id OR r.project_id<>p.project_id
 OR r.provider<>v.model_config->>'provider' OR r.model<>v.model_config->>'model')
 OR EXISTS (SELECT 1 FROM run_reservations r JOIN prompt_versions v ON v.id=r.version_id
 JOIN prompts p ON p.id=v.prompt_id WHERE r.prompt_id<>v.prompt_id OR r.project_id<>p.project_id)
 OR EXISTS (SELECT 1 FROM deployments d JOIN prompt_versions v ON v.id=d.version_id
 WHERE d.prompt_id<>v.prompt_id) THEN
  RAISE EXCEPTION 'Existing execution context is inconsistent; normalization aborted';
 END IF;
END $$;

DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM runs r CROSS JOIN LATERAL jsonb_each(r.input_variables) i
 WHERE jsonb_typeof(i.value)<>'string') THEN
 RAISE EXCEPTION 'Non-string historical run input; normalization aborted'; END IF;
 IF EXISTS (SELECT 1 FROM prompt_versions WHERE model_config - ARRAY['provider','model','temperature','max_output_tokens'] <> '{}'::jsonb) THEN
 RAISE EXCEPTION 'Unknown historical model attributes; normalization aborted'; END IF;
END $$;
CREATE TABLE run_inputs (
 run_id UUID NOT NULL,run_created_at TIMESTAMPTZ NOT NULL,
 name TEXT NOT NULL,value TEXT NOT NULL,
 PRIMARY KEY(run_id,run_created_at,name),
 FOREIGN KEY(run_id,run_created_at) REFERENCES runs(id,created_at) ON DELETE CASCADE
);
INSERT INTO run_inputs SELECT r.id,r.created_at,i.key,i.value
 FROM runs r CROSS JOIN LATERAL jsonb_each_text(r.input_variables) i;
REVOKE ALL ON run_inputs FROM PUBLIC;
GRANT SELECT ON run_inputs TO promptvault_app,promptvault_readonly;
CREATE TRIGGER run_inputs_immutable BEFORE UPDATE OR DELETE ON run_inputs
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();
ALTER TABLE prompt_versions ADD COLUMN provider VARCHAR(80),ADD COLUMN model VARCHAR(160),
 ADD COLUMN temperature NUMERIC,ADD COLUMN max_output_tokens INTEGER;
ALTER TABLE prompt_versions DISABLE TRIGGER prompt_versions_are_immutable;
UPDATE prompt_versions SET provider=model_config->>'provider',model=model_config->>'model',
 temperature=(model_config->>'temperature')::numeric,
 max_output_tokens=(model_config->>'max_output_tokens')::integer;
ALTER TABLE prompt_versions ENABLE TRIGGER prompt_versions_are_immutable;
ALTER TABLE prompt_versions ALTER COLUMN provider SET NOT NULL,ALTER COLUMN model SET NOT NULL,
 ADD CONSTRAINT version_provider_scope CHECK (provider IN ('gemini','openrouter','groq','mock')),
 ADD CONSTRAINT version_model_not_blank CHECK (length(trim(model))>0),
 ADD CONSTRAINT version_temperature CHECK (temperature IS NULL OR temperature BETWEEN 0 AND 2),
 ADD CONSTRAINT version_output_limit CHECK (max_output_tokens IS NULL OR max_output_tokens BETWEEN 1 AND 1000000);
ALTER TABLE prompt_versions DROP COLUMN model_config;
ALTER TABLE runs DROP COLUMN input_variables;

CREATE TABLE prompt_version_parents (
 version_id UUID PRIMARY KEY REFERENCES prompt_versions(id) ON DELETE CASCADE,
 parent_version_id UUID NOT NULL REFERENCES prompt_versions(id) ON DELETE RESTRICT,
 CHECK (version_id<>parent_version_id)
);
CREATE INDEX ix_version_parents_parent ON prompt_version_parents(parent_version_id);
INSERT INTO prompt_version_parents SELECT id,parent_version_id FROM prompt_versions
 WHERE parent_version_id IS NOT NULL;
CREATE TABLE prompt_version_variables (
 version_id UUID NOT NULL REFERENCES prompt_versions(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL CHECK (ordinal>0),
 name TEXT NOT NULL CHECK (name ~ '^[A-Za-z_][A-Za-z0-9_]*$'),
 PRIMARY KEY(version_id,ordinal), UNIQUE(version_id,name)
);
INSERT INTO prompt_version_variables SELECT v.id,a.ordinality,a.name
 FROM prompt_versions v CROSS JOIN LATERAL jsonb_array_elements_text(v.variables)
 WITH ORDINALITY a(name,ordinality);
CREATE TABLE reservation_results (
 reservation_id UUID PRIMARY KEY REFERENCES run_reservations(id) ON DELETE CASCADE,
 run_id UUID NOT NULL,run_created_at TIMESTAMPTZ NOT NULL,
 FOREIGN KEY(run_id,run_created_at) REFERENCES runs(id,created_at) ON DELETE RESTRICT
);
INSERT INTO reservation_results SELECT id,run_id,run_created_at FROM run_reservations
 WHERE run_id IS NOT NULL;
DROP VIEW prompt_version_lineage;
ALTER TABLE prompt_versions DROP COLUMN parent_version_id,DROP COLUMN variables;
ALTER TABLE run_reservations DROP COLUMN actual_cost,DROP COLUMN run_id,DROP COLUMN run_created_at;
CREATE VIEW version_context AS SELECT v.id,v.prompt_id,v.version_number,v.template_body,
 v.commit_message,v.created_by,v.created_at,parent.parent_version_id,
 jsonb_strip_nulls(jsonb_build_object('provider',v.provider,'model',v.model,
 'temperature',v.temperature,'max_output_tokens',v.max_output_tokens)) AS model_config,
 COALESCE((SELECT jsonb_agg(pv.name ORDER BY pv.ordinal) FROM prompt_version_variables pv
 WHERE pv.version_id=v.id),'[]'::jsonb) AS variables
 FROM prompt_versions v LEFT JOIN prompt_version_parents parent ON parent.version_id=v.id;
CREATE FUNCTION enforce_version_parent_scope() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM prompt_versions child JOIN prompt_versions parent
 ON child.prompt_id=parent.prompt_id WHERE child.id=NEW.version_id
 AND parent.id=NEW.parent_version_id AND parent.version_number<child.version_number)
 THEN RAISE EXCEPTION 'invalid_parent_version' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER normalized_parent_scope BEFORE INSERT OR UPDATE ON prompt_version_parents
 FOR EACH ROW EXECUTE FUNCTION enforce_version_parent_scope();
CREATE TRIGGER version_parents_immutable BEFORE UPDATE OR DELETE ON prompt_version_parents
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();
CREATE TRIGGER version_variables_immutable BEFORE UPDATE OR DELETE ON prompt_version_variables
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();
REVOKE ALL ON prompt_version_parents,prompt_version_variables,reservation_results FROM PUBLIC;
GRANT SELECT ON prompt_version_parents,prompt_version_variables,reservation_results,version_context
 TO promptvault_app;
GRANT SELECT ON prompt_version_parents,prompt_version_variables,version_context TO promptvault_readonly;
REVOKE ALL ON FUNCTION enforce_version_parent_scope() FROM PUBLIC;

CREATE TABLE deployment_rollbacks (
 deployment_id UUID PRIMARY KEY REFERENCES deployments(id) ON DELETE RESTRICT,
 rollback_of_id UUID NOT NULL REFERENCES deployments(id) ON DELETE RESTRICT,
 reason TEXT NOT NULL CHECK (length(trim(reason))>0)
);
INSERT INTO deployment_rollbacks(deployment_id,rollback_of_id,reason)
 SELECT id,rollback_of_id,rollback_reason FROM deployments WHERE rollback_of_id IS NOT NULL;

DROP VIEW deployment_history;
DROP VIEW monthly_costs;
ALTER TABLE runs DROP COLUMN project_id, DROP COLUMN prompt_id, DROP COLUMN provider, DROP COLUMN model;
ALTER TABLE run_reservations DROP COLUMN project_id, DROP COLUMN prompt_id;
ALTER TABLE deployments DROP COLUMN prompt_id, DROP COLUMN rollback_of_id, DROP COLUMN rollback_reason;
-- Removing the former composite version/prompt key also removes its FK.
ALTER TABLE deployments ADD CONSTRAINT deployments_version_fk
 FOREIGN KEY(version_id) REFERENCES prompt_versions(id) ON DELETE RESTRICT;

CREATE VIEW run_context AS SELECT r.*,v.prompt_id,p.project_id,
 v.provider,v.model,
 COALESCE((SELECT jsonb_object_agg(i.name,i.value) FROM run_inputs i
 WHERE i.run_id=r.id AND i.run_created_at=r.created_at),'{}'::jsonb) AS input_variables
 FROM runs r JOIN prompt_versions v ON v.id=r.version_id JOIN prompts p ON p.id=v.prompt_id;
CREATE VIEW reservation_context AS SELECT r.*,v.prompt_id,p.project_id,
 result.run_id,result.run_created_at,
 CASE WHEN r.status IN ('completed','failed') THEN ledger.cost END AS actual_cost
 FROM run_reservations r JOIN prompt_versions v ON v.id=r.version_id
 JOIN prompts p ON p.id=v.prompt_id
 LEFT JOIN reservation_results result ON result.reservation_id=r.id
 LEFT JOIN runs ledger ON ledger.id=result.run_id AND ledger.created_at=result.run_created_at;
CREATE VIEW deployment_context AS SELECT d.*,v.prompt_id,rb.rollback_of_id,rb.reason AS rollback_reason
 FROM deployments d JOIN prompt_versions v ON v.id=d.version_id
 LEFT JOIN deployment_rollbacks rb ON rb.deployment_id=d.id;

CREATE INDEX ix_runs_version_timeline ON runs(version_id,created_at DESC,id DESC) INCLUDE (status,cost);
CREATE INDEX ix_reservations_version_created ON run_reservations(version_id,created_at DESC);
CREATE INDEX ix_deployments_version_environment ON deployments(version_id,environment,status);

CREATE FUNCTION enforce_normalized_deployment() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE target_prompt UUID;
BEGIN
 SELECT prompt_id INTO target_prompt FROM prompt_versions WHERE id=NEW.version_id;
 PERFORM 1 FROM prompts WHERE id=target_prompt FOR UPDATE;
 IF NEW.status='active' AND EXISTS (
   SELECT 1 FROM deployments d JOIN prompt_versions v ON v.id=d.version_id
   WHERE v.prompt_id=target_prompt AND d.environment=NEW.environment AND d.status='active'
     AND d.id<>NEW.id
 ) THEN RAISE EXCEPTION 'one_active_deployment' USING ERRCODE='23505'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER normalized_deployment_activation BEFORE INSERT OR UPDATE ON deployments
 FOR EACH ROW EXECUTE FUNCTION enforce_normalized_deployment();

CREATE FUNCTION enforce_rollback_scope() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM deployments d JOIN prompt_versions v ON v.id=d.version_id
 JOIN deployments previous ON previous.id=NEW.rollback_of_id
 JOIN prompt_versions pv ON pv.id=previous.version_id
 WHERE d.id=NEW.deployment_id AND v.prompt_id=pv.prompt_id
 AND d.environment=previous.environment AND v.version_number<pv.version_number)
 THEN RAISE EXCEPTION 'invalid_rollback_scope' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER normalized_rollback_scope BEFORE INSERT OR UPDATE ON deployment_rollbacks
 FOR EACH ROW EXECUTE FUNCTION enforce_rollback_scope();
CREATE TRIGGER deployment_rollbacks_audit AFTER INSERT OR UPDATE OR DELETE ON deployment_rollbacks
 FOR EACH ROW EXECUTE FUNCTION record_audit_event();
REVOKE ALL ON deployment_rollbacks FROM PUBLIC;
GRANT SELECT ON deployment_rollbacks TO promptvault_app,promptvault_readonly;
GRANT SELECT ON run_context,reservation_context,deployment_context TO promptvault_app;
GRANT SELECT ON run_context,deployment_context TO promptvault_readonly;
REVOKE ALL ON FUNCTION enforce_normalized_deployment(),enforce_rollback_scope() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.record_run(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_status run_status, p_provider text, p_model text, p_input_variables jsonb, p_output_text text, p_prompt_tokens integer, p_completion_tokens integer, p_latency_ms integer, p_cost numeric, p_error_code text, p_request_id text, p_created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP)
 RETURNS runs
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    budget_record budgets%ROWTYPE;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    spent NUMERIC(18, 6);
    final_status run_status := p_status;
    final_cost NUMERIC(18, 6) := p_cost;
    final_error TEXT := p_error_code;
    created_run runs%ROWTYPE;
BEGIN
    IF p_input_variables IS NULL OR jsonb_typeof(p_input_variables)<>'object'
       OR EXISTS(SELECT 1 FROM jsonb_each(p_input_variables) i WHERE jsonb_typeof(i.value)<>'string')
    THEN RAISE EXCEPTION 'invalid_run_inputs' USING ERRCODE='23514'; END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM prompt_versions pv
        JOIN prompts p ON p.id = pv.prompt_id
        WHERE pv.id = p_version_id
          AND pv.prompt_id = p_prompt_id
          AND p.project_id = p_project_id
          AND pv.provider = p_provider
          AND pv.model = p_model
    ) THEN
        RAISE EXCEPTION 'invalid_run_target' USING ERRCODE = '23503';
    END IF;

    IF p_status = 'completed' THEN
        FOR budget_record IN
            SELECT *
            FROM budgets
            WHERE user_id = p_user_id OR project_id = p_project_id
            ORDER BY id
            FOR UPDATE
        LOOP
            month_start := date_trunc(
                'month',
                p_created_at AT TIME ZONE budget_record.timezone
            ) AT TIME ZONE budget_record.timezone;
            month_end := (
                date_trunc('month', p_created_at AT TIME ZONE budget_record.timezone)
                + INTERVAL '1 month'
            ) AT TIME ZONE budget_record.timezone;

            SELECT COALESCE(sum(cost), 0) INTO spent
            FROM run_context
            WHERE status = 'completed'
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            IF spent + p_cost > budget_record.monthly_limit THEN
                final_status := 'blocked';
                final_cost := 0;
                final_error := 'budget_exceeded';
                EXIT;
            END IF;
        END LOOP;
    END IF;

    INSERT INTO runs (
        user_id,
        version_id,
        status,
        output_text,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        cost,
        error_code,
        request_id,
        created_at
    )
    VALUES (
        p_user_id,
        p_version_id,
        final_status,
        CASE WHEN final_status = 'completed' THEN p_output_text END,
        p_prompt_tokens,
        p_completion_tokens,
        p_latency_ms,
        final_cost,
        final_error,
        p_request_id,
        p_created_at
    )
    RETURNING * INTO created_run;
    INSERT INTO run_inputs(run_id,run_created_at,name,value)
    SELECT created_run.id,created_run.created_at,key,value
    FROM jsonb_each_text(p_input_variables);
    RETURN created_run;
END;
$function$;

DROP FUNCTION reserve_run_execution(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_idempotency_key text, p_request_fingerprint text, p_claim_token uuid, p_estimated_cost numeric, p_maximum_concurrent integer, p_created_at timestamp with time zone);
CREATE OR REPLACE FUNCTION public.reserve_run_execution(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_idempotency_key text, p_request_fingerprint text, p_claim_token uuid, p_estimated_cost numeric, p_maximum_concurrent integer, p_created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP)
 RETURNS reservation_context
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    existing_reservation run_reservations%ROWTYPE;
    created_reservation run_reservations%ROWTYPE;
    budget_record budgets%ROWTYPE;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    spent NUMERIC(18, 6);
    reserved NUMERIC(18, 6);
    blocked_error TEXT;
BEGIN
    IF p_estimated_cost < 0 OR p_maximum_concurrent < 1 THEN
        RAISE EXCEPTION 'invalid_reservation_limits' USING ERRCODE = '22023';
    END IF;

    PERFORM 1 FROM users WHERE id = p_user_id AND is_active FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'inactive_user' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO existing_reservation
    FROM run_reservations
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
    FOR UPDATE;
    IF FOUND THEN
        IF existing_reservation.request_fingerprint <> p_request_fingerprint THEN
            RAISE EXCEPTION 'idempotency_conflict';
        END IF;
        RETURN (SELECT context FROM reservation_context context WHERE context.id=existing_reservation.id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM prompt_versions pv
        JOIN prompts p ON p.id = pv.prompt_id
        WHERE pv.id = p_version_id
          AND pv.prompt_id = p_prompt_id
          AND p.project_id = p_project_id
    ) THEN
        RAISE EXCEPTION 'invalid_run_target' USING ERRCODE = '23503';
    END IF;

    IF (
        SELECT count(*)
        FROM run_reservations
        WHERE user_id = p_user_id AND status = 'reserved'
    ) >= p_maximum_concurrent THEN
        blocked_error := 'concurrency_limit';
    END IF;

    IF blocked_error IS NULL THEN
        FOR budget_record IN
            SELECT *
            FROM budgets
            WHERE user_id = p_user_id OR project_id = p_project_id
            ORDER BY id
            FOR UPDATE
        LOOP
            month_start := date_trunc(
                'month', p_created_at AT TIME ZONE budget_record.timezone
            ) AT TIME ZONE budget_record.timezone;
            month_end := (
                date_trunc('month', p_created_at AT TIME ZONE budget_record.timezone)
                + INTERVAL '1 month'
            ) AT TIME ZONE budget_record.timezone;

            SELECT COALESCE(sum(cost), 0) INTO spent
            FROM run_context
            WHERE status = 'completed'
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            SELECT COALESCE(sum(estimated_cost), 0) INTO reserved
            FROM reservation_context
            WHERE status IN ('reserved', 'uncertain')
              AND created_at >= month_start
              AND created_at < month_end
              AND (
                  (budget_record.user_id IS NOT NULL AND user_id = budget_record.user_id)
                  OR
                  (budget_record.project_id IS NOT NULL AND project_id = budget_record.project_id)
              );

            IF spent + reserved + p_estimated_cost > budget_record.monthly_limit THEN
                blocked_error := 'budget_exceeded';
                EXIT;
            END IF;
        END LOOP;
    END IF;

    INSERT INTO run_reservations (
        user_id, version_id, idempotency_key,
        request_fingerprint, claim_token, estimated_cost, status, error_code, created_at
    ) VALUES (
        p_user_id, p_version_id, p_idempotency_key,
        p_request_fingerprint, p_claim_token, p_estimated_cost,
        CASE WHEN blocked_error IS NULL THEN 'reserved' ELSE 'blocked' END,
        blocked_error, p_created_at
    )
    RETURNING * INTO created_reservation;
    RETURN (SELECT context FROM reservation_context context WHERE context.id=created_reservation.id);
END;
$function$;
REVOKE ALL ON FUNCTION reserve_run_execution(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_idempotency_key text, p_request_fingerprint text, p_claim_token uuid, p_estimated_cost numeric, p_maximum_concurrent integer, p_created_at timestamp with time zone) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reserve_run_execution(p_user_id uuid, p_project_id uuid, p_prompt_id uuid, p_version_id uuid, p_idempotency_key text, p_request_fingerprint text, p_claim_token uuid, p_estimated_cost numeric, p_maximum_concurrent integer, p_created_at timestamp with time zone) TO promptvault_app;


DROP FUNCTION finalize_run_execution(p_reservation_id uuid, p_status text, p_actual_cost numeric, p_run_id uuid, p_run_created_at timestamp with time zone, p_error_code text);
CREATE OR REPLACE FUNCTION public.finalize_run_execution(p_reservation_id uuid, p_status text, p_actual_cost numeric, p_run_id uuid, p_run_created_at timestamp with time zone, p_error_code text)
 RETURNS reservation_context
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    reservation run_reservations%ROWTYPE;
BEGIN
    SELECT * INTO reservation
    FROM run_reservations
    WHERE id = p_reservation_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation_not_found' USING ERRCODE = 'P0002';
    END IF;
    IF reservation.status <> 'reserved' THEN
        IF reservation.status = p_status THEN
            RETURN (SELECT context FROM reservation_context context WHERE context.id=reservation.id);
        END IF;
        RAISE EXCEPTION 'reservation_already_finalized' USING ERRCODE = '55000';
    END IF;
    IF p_status NOT IN ('completed', 'failed', 'uncertain') THEN
        RAISE EXCEPTION 'invalid_reservation_status' USING ERRCODE = '22023';
    END IF;
    IF p_status IN ('completed', 'failed') THEN
        IF p_run_id IS NULL OR p_run_created_at IS NULL OR p_actual_cost IS NULL THEN
            RAISE EXCEPTION 'finalized_reservation_requires_run' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM runs
            WHERE id = p_run_id
              AND created_at = p_run_created_at
              AND user_id = reservation.user_id
              AND version_id = reservation.version_id
              AND cost = p_actual_cost
        ) THEN
            RAISE EXCEPTION 'reservation_run_mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF p_actual_cost IS NOT NULL OR (p_run_id IS NULL) <> (p_run_created_at IS NULL) THEN
        RAISE EXCEPTION 'invalid_uncertain_reservation_result' USING ERRCODE = '23514';
    ELSIF p_run_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM runs
        WHERE id = p_run_id
          AND created_at = p_run_created_at
          AND user_id = reservation.user_id
          AND version_id = reservation.version_id
    ) THEN
        RAISE EXCEPTION 'reservation_run_mismatch' USING ERRCODE = '23514';
    END IF;

    UPDATE run_reservations
    SET status = p_status,
        error_code = p_error_code,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_reservation_id
    RETURNING * INTO reservation;
    IF p_run_id IS NOT NULL THEN
        INSERT INTO reservation_results(reservation_id,run_id,run_created_at)
        VALUES(p_reservation_id,p_run_id,p_run_created_at);
    END IF;
    RETURN (SELECT context FROM reservation_context context WHERE context.id=reservation.id);
END;
$function$;
REVOKE ALL ON FUNCTION finalize_run_execution(p_reservation_id uuid, p_status text, p_actual_cost numeric, p_run_id uuid, p_run_created_at timestamp with time zone, p_error_code text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finalize_run_execution(p_reservation_id uuid, p_status text, p_actual_cost numeric, p_run_id uuid, p_run_created_at timestamp with time zone, p_error_code text) TO promptvault_app;


CREATE OR REPLACE FUNCTION public.request_deployment(p_version_id uuid, p_environment deployment_environment, p_requested_by uuid, p_request_note text DEFAULT NULL::text)
 RETURNS deployments
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    target_version prompt_versions%ROWTYPE;
    created_deployment deployments%ROWTYPE;
    initial_status deployment_status;
BEGIN
    SELECT pv.* INTO target_version
    FROM prompt_versions AS pv
    WHERE pv.id = p_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    PERFORM 1 FROM prompts WHERE id = target_version.prompt_id FOR UPDATE;
    initial_status := CASE WHEN p_environment = 'prod' THEN 'pending' ELSE 'active' END;

    IF initial_status = 'active' THEN
        UPDATE deployments
        SET status = 'superseded'
        WHERE version_id IN (SELECT id FROM prompt_versions WHERE prompt_id = target_version.prompt_id)
          AND environment = p_environment
          AND status = 'active';
    END IF;

    INSERT INTO deployments (
        version_id,
        environment,
        status,
        request_note,
        requested_by,
        activated_at
    )
    VALUES (
        target_version.id,
        p_environment,
        initial_status,
        p_request_note,
        p_requested_by,
        CASE WHEN initial_status = 'active' THEN CURRENT_TIMESTAMP END
    )
    RETURNING * INTO created_deployment;
    RETURN created_deployment;
END;
$function$;

CREATE OR REPLACE FUNCTION public.review_production_deployment(p_deployment_id uuid, p_admin_id uuid, p_approve boolean, p_review_note text DEFAULT NULL::text)
 RETURNS deployments
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    deployment_record deployments%ROWTYPE;
BEGIN
    PERFORM 1
    FROM users
    WHERE id = p_admin_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO deployment_record
    FROM deployments
    WHERE id = p_deployment_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'deployment_not_found' USING ERRCODE = 'P0002';
    END IF;
    IF deployment_record.environment <> 'prod' OR deployment_record.status <> 'pending' THEN
        RAISE EXCEPTION 'already_reviewed' USING ERRCODE = '40001';
    END IF;
    IF NOT p_approve AND length(trim(COALESCE(p_review_note, ''))) = 0 THEN
        RAISE EXCEPTION 'rejection_note_required' USING ERRCODE = '23514';
    END IF;

    IF p_approve THEN
        PERFORM 1 FROM prompts WHERE id = (SELECT prompt_id FROM prompt_versions WHERE id=deployment_record.version_id) FOR UPDATE;
        UPDATE deployments
        SET status = 'superseded'
        WHERE version_id IN (SELECT id FROM prompt_versions WHERE prompt_id = (SELECT prompt_id FROM prompt_versions WHERE id=deployment_record.version_id))
          AND environment = 'prod'
          AND status = 'active';
        UPDATE deployments
        SET status = 'active',
            review_note = p_review_note,
            reviewed_by = p_admin_id,
            reviewed_at = CURRENT_TIMESTAMP,
            activated_at = CURRENT_TIMESTAMP
        WHERE id = p_deployment_id
        RETURNING * INTO deployment_record;
    ELSE
        UPDATE deployments
        SET status = 'rejected',
            review_note = p_review_note,
            reviewed_by = p_admin_id,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = p_deployment_id
        RETURNING * INTO deployment_record;
    END IF;
    RETURN deployment_record;
END;
$function$;

CREATE OR REPLACE FUNCTION public.rollback_deployment(p_prompt_id uuid, p_target_version_id uuid, p_admin_id uuid, p_reason text, p_environment deployment_environment DEFAULT 'prod'::deployment_environment)
 RETURNS deployments
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    previous_id UUID;
    active_version_number INTEGER;
    target_version_number INTEGER;
    created_deployment deployments%ROWTYPE;
BEGIN
    PERFORM 1
    FROM users
    WHERE id = p_admin_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;
    IF length(trim(COALESCE(p_reason, ''))) = 0 THEN
        RAISE EXCEPTION 'rollback_reason_required' USING ERRCODE = '23514';
    END IF;

    PERFORM 1 FROM prompts WHERE id = p_prompt_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT version_number INTO target_version_number
    FROM prompt_versions
    WHERE id = p_target_version_id AND prompt_id = p_prompt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT d.id, pv.version_number
    INTO previous_id, active_version_number
    FROM deployments d
    JOIN prompt_versions pv ON pv.id = d.version_id
    WHERE pv.prompt_id = p_prompt_id
      AND d.environment = p_environment
      AND d.status = 'active'
    FOR UPDATE OF d;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no_active_deployment' USING ERRCODE = 'P0002';
    END IF;
    IF target_version_number >= active_version_number THEN
        RAISE EXCEPTION 'invalid_rollback_target' USING ERRCODE = '23514';
    END IF;

    UPDATE deployments SET status = 'rolled_back' WHERE id = previous_id;

    INSERT INTO deployments (
        version_id,
        environment,
        status,
        requested_by,
        reviewed_by,
        reviewed_at,
        activated_at
    )
    VALUES (
        p_target_version_id,
        p_environment,
        'active',
        p_admin_id,
        p_admin_id,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
    RETURNING * INTO created_deployment;
    INSERT INTO deployment_rollbacks(deployment_id,rollback_of_id,reason)
    VALUES(created_deployment.id,previous_id,p_reason);
    RETURN created_deployment;
END;
$function$;

CREATE OR REPLACE FUNCTION public.delete_project(p_project_id uuid, p_actor_id uuid, p_request_id text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    deleted_versions INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM users
        WHERE id = p_actor_id AND role = 'admin' AND is_active
    ) THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    PERFORM 1 FROM projects WHERE id = p_project_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    PERFORM set_config('app.user_id', p_actor_id::text, true);
    PERFORM set_config('app.request_id', p_request_id, true);
    PERFORM set_config('app.project_deletion', 'true', true);

    DELETE FROM run_reservations WHERE version_id IN (SELECT v.id FROM prompt_versions v JOIN prompts p ON p.id=v.prompt_id WHERE p.project_id=p_project_id);
    DELETE FROM runs WHERE version_id IN (SELECT v.id FROM prompt_versions v JOIN prompts p ON p.id=v.prompt_id WHERE p.project_id=p_project_id);

    DELETE FROM deployment_rollbacks WHERE deployment_id IN (SELECT d.id FROM deployment_context d JOIN prompts p ON p.id=d.prompt_id WHERE p.project_id=p_project_id);
    DELETE FROM deployments
    WHERE version_id IN (SELECT v.id FROM prompt_versions v JOIN prompts p ON p.id=v.prompt_id WHERE p.project_id=p_project_id);

    LOOP
        DELETE FROM prompt_versions candidate
        WHERE candidate.prompt_id IN (
            SELECT id FROM prompts WHERE project_id = p_project_id
        )
          AND NOT EXISTS (
              SELECT 1
              FROM prompt_version_parents child
              WHERE child.parent_version_id = candidate.id
          );
        GET DIAGNOSTICS deleted_versions = ROW_COUNT;
        EXIT WHEN deleted_versions = 0;
    END LOOP;

    DELETE FROM prompts WHERE project_id = p_project_id;
    DELETE FROM projects WHERE id = p_project_id;
    PERFORM set_config('app.project_deletion', 'false', true);
    RETURN TRUE;
END;
$function$;

CREATE VIEW deployment_history AS
SELECT
    deployment.id,
    deployment.prompt_id,
    prompt.project_id,
    deployment.version_id,
    version.version_number,
    deployment.environment,
    deployment.status,
    deployment.request_note,
    deployment.review_note,
    deployment.rollback_reason,
    deployment.rollback_of_id,
    deployment.requested_by,
    deployment.reviewed_by,
    deployment.requested_at,
    deployment.reviewed_at,
    deployment.activated_at
FROM deployment_context AS deployment
JOIN prompts AS prompt ON prompt.id = deployment.prompt_id
JOIN prompt_versions AS version ON version.id = deployment.version_id;

CREATE VIEW monthly_costs AS
SELECT
    date_trunc('month', created_at) AS month,
    user_id,
    project_id,
    provider,
    model,
    count(*) FILTER (WHERE status = 'completed') AS completed_runs,
    count(*) FILTER (WHERE status = 'failed') AS failed_runs,
    count(*) FILTER (WHERE status = 'blocked') AS blocked_runs,
    COALESCE(sum(cost) FILTER (WHERE status = 'completed'), 0)::NUMERIC(18, 6) AS cost
FROM run_context
GROUP BY date_trunc('month', created_at), user_id, project_id, provider, model;

GRANT SELECT ON deployment_history,monthly_costs TO promptvault_app,promptvault_readonly;

CREATE OR REPLACE FUNCTION public.create_prompt_version(p_prompt_id uuid, p_parent_version_id uuid, p_template_body text, p_variables jsonb, p_model_config jsonb, p_commit_message text, p_created_by uuid)
 RETURNS prompt_versions
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    next_version INTEGER;
    existing_versions INTEGER;
    created_version prompt_versions%ROWTYPE;
BEGIN
    PERFORM 1 FROM prompts WHERE id = p_prompt_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'prompt_not_found' USING ERRCODE = 'P0002';
    END IF;

    SELECT count(*), COALESCE(max(version_number), 0) + 1
    INTO existing_versions, next_version
    FROM prompt_versions
    WHERE prompt_id = p_prompt_id;

    IF existing_versions = 0 AND p_parent_version_id IS NOT NULL THEN
        RAISE EXCEPTION 'initial_version_cannot_have_parent' USING ERRCODE = '23514';
    END IF;
    IF existing_versions > 0 AND NOT EXISTS (
        SELECT 1 FROM prompt_versions
        WHERE id = p_parent_version_id AND prompt_id = p_prompt_id
    ) THEN
        RAISE EXCEPTION 'invalid_parent_version' USING ERRCODE = '23514';
    END IF;

    INSERT INTO prompt_versions (
        prompt_id,
        version_number,
        template_body,
        provider, model, temperature, max_output_tokens,
        commit_message,
        created_by
    )
    VALUES (
        p_prompt_id,
        next_version,
        p_template_body,
        p_model_config->>'provider',p_model_config->>'model',
        (p_model_config->>'temperature')::numeric,(p_model_config->>'max_output_tokens')::integer,
        p_commit_message,
        p_created_by
    )
    RETURNING * INTO created_version;
    IF p_parent_version_id IS NOT NULL THEN
        INSERT INTO prompt_version_parents(version_id,parent_version_id)
        VALUES(created_version.id,p_parent_version_id);
    END IF;
    INSERT INTO prompt_version_variables(version_id,ordinal,name)
    SELECT created_version.id,ordinality,name
    FROM jsonb_array_elements_text(p_variables) WITH ORDINALITY AS v(name,ordinality);
    RETURN created_version;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.reject_immutable_row_change()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('app.project_deletion', true) = 'true'
       AND (TG_TABLE_NAME IN ('prompt_versions', 'runs', 'prompt_version_parents', 'prompt_version_variables', 'run_inputs')
            OR EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid=TG_RELID AND inhparent='runs'::regclass)) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$function$
;

CREATE VIEW prompt_version_lineage AS
WITH RECURSIVE lineage AS (
    SELECT
        version.id AS descendant_version_id,
        version.id AS version_id,
        version.parent_version_id,
        0 AS depth,
        ARRAY[version.id] AS path,
        FALSE AS cycle_detected
    FROM version_context AS version

    UNION ALL

    SELECT
        lineage.descendant_version_id,
        parent.id,
        parent.parent_version_id,
        lineage.depth + 1,
        lineage.path || parent.id,
        parent.id = ANY(lineage.path)
    FROM lineage
    JOIN version_context AS parent ON parent.id = lineage.parent_version_id
    WHERE NOT lineage.cycle_detected
      AND lineage.depth < 1000
)
SELECT
    descendant_version_id,
    version_id,
    parent_version_id,
    depth,
    cycle_detected
FROM lineage;


GRANT SELECT ON prompt_version_lineage TO promptvault_app,promptvault_readonly;
