-- Match existing governance and cancellation: reviewer, deployment, then prompt.
-- This also lets competing reviews observe the first committed decision before
-- deciding whether fresh release evidence is still needed.
CREATE OR REPLACE FUNCTION review_production_deployment(p_deployment_id uuid, p_admin_id uuid,
    p_approve boolean, p_review_note text DEFAULT NULL) RETURNS deployments
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public, pg_temp AS $$
DECLARE d deployments%ROWTYPE;
BEGIN
    PERFORM 1 FROM users WHERE id=p_admin_id AND role IN ('admin','super_admin')
        AND is_active AND is_approved AND email_verified_at IS NOT NULL FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'admin_required' USING ERRCODE='42501'; END IF;
    SELECT * INTO d FROM deployments WHERE id=p_deployment_id FOR UPDATE;
    IF p_approve AND d.status='pending' THEN
        PERFORM assert_release_validation(d.validation_id,d.version_id,d.environment);
    END IF;
    RETURN review_production_deployment_without_validation(p_deployment_id,p_admin_id,p_approve,p_review_note);
END $$;
