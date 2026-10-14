-- Permit immutable history deletion only inside the guarded admin project routine.
CREATE OR REPLACE FUNCTION reject_immutable_row_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('app.project_deletion', true) = 'true'
       AND TG_TABLE_NAME IN ('prompt_versions', 'runs') THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION delete_project(
    p_project_id UUID,
    p_actor_id UUID,
    p_request_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
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

    DELETE FROM run_reservations WHERE project_id = p_project_id;
    DELETE FROM runs WHERE project_id = p_project_id;

    UPDATE deployments
    SET rollback_of_id = NULL
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);
    DELETE FROM deployments
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);

    LOOP
        DELETE FROM prompt_versions candidate
        WHERE candidate.prompt_id IN (
            SELECT id FROM prompts WHERE project_id = p_project_id
        )
          AND NOT EXISTS (
              SELECT 1
              FROM prompt_versions child
              WHERE child.parent_version_id = candidate.id
                AND child.prompt_id = candidate.prompt_id
          );
        GET DIAGNOSTICS deleted_versions = ROW_COUNT;
        EXIT WHEN deleted_versions = 0;
    END LOOP;

    DELETE FROM prompts WHERE project_id = p_project_id;
    DELETE FROM projects WHERE id = p_project_id;
    PERFORM set_config('app.project_deletion', 'false', true);
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION delete_project(UUID, UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_project(UUID, UUID, TEXT) TO promptvault_app;
