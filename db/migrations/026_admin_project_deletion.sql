-- Delete a complete project graph only for a current active administrator.
CREATE FUNCTION delete_project(
    p_project_id UUID,
    p_actor_id UUID,
    p_request_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
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

    DELETE FROM run_reservations WHERE project_id = p_project_id;
    DELETE FROM runs WHERE project_id = p_project_id;

    UPDATE deployments
    SET rollback_of_id = NULL
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);
    DELETE FROM deployments
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);

    UPDATE prompt_versions
    SET parent_version_id = NULL
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);
    DELETE FROM prompt_versions
    WHERE prompt_id IN (SELECT id FROM prompts WHERE project_id = p_project_id);

    DELETE FROM prompts WHERE project_id = p_project_id;
    DELETE FROM projects WHERE id = p_project_id;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION delete_project(UUID, UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_project(UUID, UUID, TEXT) TO promptvault_app;
