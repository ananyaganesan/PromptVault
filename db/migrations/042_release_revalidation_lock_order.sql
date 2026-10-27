-- Reattaching evidence races with cancellation in the same way as approval.
CREATE OR REPLACE FUNCTION replace_release_validation(p_deployment_id uuid,p_validation_id uuid,p_actor uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public, pg_temp AS $$
DECLARE d deployments%ROWTYPE;
BEGIN
    SELECT * INTO d FROM deployments WHERE id=p_deployment_id FOR UPDATE;
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
