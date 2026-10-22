-- Super Admins may demote themselves, but cannot demote another Super Admin.
CREATE OR REPLACE FUNCTION admin_update_user(
    p_target_user_id UUID,
    p_actor_user_id UUID,
    p_role user_role,
    p_role_set BOOLEAN,
    p_is_active BOOLEAN,
    p_active_set BOOLEAN
)
RETURNS users
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    target users%ROWTYPE;
    resulting_role user_role;
    resulting_active BOOLEAN;
    updated users%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('promptvault_admin_user_transition'));

    PERFORM 1 FROM users
    WHERE id = p_actor_user_id AND role = 'admin' AND is_active
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO target FROM users WHERE id = p_target_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'user_not_found' USING ERRCODE = 'P0002';
    END IF;

    resulting_role := CASE WHEN p_role_set THEN p_role ELSE target.role END;
    resulting_active := CASE WHEN p_active_set THEN p_is_active ELSE target.is_active END;

    IF target.role = 'admin' AND resulting_role <> 'admin'
       AND target.id <> p_actor_user_id THEN
        RAISE EXCEPTION 'admin_peer_demotion' USING ERRCODE = '23514';
    END IF;

    IF target.role = 'admin' AND target.is_active
       AND (resulting_role <> 'admin' OR NOT resulting_active)
       AND NOT EXISTS (
           SELECT 1 FROM users
           WHERE id <> target.id AND role = 'admin' AND is_active
       ) THEN
        RAISE EXCEPTION 'last_admin' USING ERRCODE = '23514';
    END IF;

    UPDATE users
    SET role = resulting_role, is_active = resulting_active
    WHERE id = target.id
    RETURNING * INTO updated;
    RETURN updated;
END;
$$;

REVOKE ALL ON FUNCTION admin_update_user(
    UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_update_user(
    UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN
) TO promptvault_app;
