-- Existing accounts retain access; only new registrations need approval.
ALTER TABLE users ADD COLUMN is_approved BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ALTER COLUMN is_approved SET DEFAULT FALSE;

DROP FUNCTION admin_update_user(UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN);
CREATE FUNCTION admin_update_user(
    p_target_user_id UUID, p_actor_user_id UUID,
    p_role user_role, p_role_set BOOLEAN,
    p_is_active BOOLEAN, p_active_set BOOLEAN,
    p_is_approved BOOLEAN, p_approved_set BOOLEAN
) RETURNS users
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE actor users%ROWTYPE; target users%ROWTYPE; updated users%ROWTYPE;
    resulting_role user_role; resulting_active BOOLEAN; resulting_approved BOOLEAN;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('promptvault_admin_user_transition'));
    SELECT * INTO actor FROM users WHERE id = p_actor_user_id FOR UPDATE;
    IF NOT FOUND OR actor.role NOT IN ('admin', 'super_admin')
       OR NOT actor.is_active OR NOT actor.is_approved
       OR actor.email_verified_at IS NULL THEN
        RAISE EXCEPTION 'admin_required' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO target FROM users WHERE id = p_target_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'user_not_found' USING ERRCODE = 'P0002';
    END IF;
    -- Admins manage regular users only; role assignment belongs to superadmins.
    IF actor.role = 'admin' AND (target.role <> 'user' OR p_role_set) THEN
        RAISE EXCEPTION 'super_admin_required' USING ERRCODE = '42501';
    END IF;
    resulting_role := CASE WHEN p_role_set THEN p_role ELSE target.role END;
    resulting_active := CASE WHEN p_active_set THEN p_is_active ELSE target.is_active END;
    resulting_approved := CASE WHEN p_approved_set THEN p_is_approved ELSE target.is_approved END;
    IF p_approved_set AND resulting_approved AND target.email_verified_at IS NULL THEN
        RAISE EXCEPTION 'email_unverified' USING ERRCODE = '23514';
    END IF;
    IF target.role = 'super_admin' AND resulting_role <> 'super_admin'
       AND target.id <> actor.id THEN
        RAISE EXCEPTION 'admin_peer_demotion' USING ERRCODE = '23514';
    END IF;
    IF target.role = 'super_admin' AND target.is_active AND target.is_approved
       AND (resulting_role <> 'super_admin' OR NOT resulting_active OR NOT resulting_approved)
       AND NOT EXISTS (SELECT 1 FROM users WHERE id <> target.id
            AND role = 'super_admin' AND is_active AND is_approved) THEN
        RAISE EXCEPTION 'last_admin' USING ERRCODE = '23514';
    END IF;
    UPDATE users SET role = resulting_role, is_active = resulting_active,
        is_approved = resulting_approved WHERE id = target.id RETURNING * INTO updated;
    RETURN updated;
END $$;
REVOKE ALL ON FUNCTION admin_update_user(UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN, BOOLEAN, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_update_user(UUID, UUID, user_role, BOOLEAN, BOOLEAN, BOOLEAN, BOOLEAN, BOOLEAN) TO promptvault_app;

-- Deployment approvals are the only existing system routines delegated to admins.
DO $$
DECLARE routine RECORD; definition TEXT;
BEGIN
    FOR routine IN SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname IN ('review_production_deployment')
    LOOP
        definition := replace(pg_get_functiondef(routine.oid),
            'role = ''super_admin'' AND is_active',
            'role IN (''admin'', ''super_admin'') AND is_active AND is_approved');
        EXECUTE definition;
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION preserve_last_active_admin() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.role = 'super_admin' AND OLD.is_active AND OLD.is_approved
       AND (TG_OP = 'DELETE' OR NEW.role <> 'super_admin'
            OR NOT NEW.is_active OR NOT NEW.is_approved) THEN
        PERFORM pg_advisory_xact_lock(hashtext('promptvault_admin_user_transition'));
        IF NOT EXISTS (SELECT 1 FROM users WHERE id <> OLD.id
            AND role = 'super_admin' AND is_active AND is_approved) THEN
            RAISE EXCEPTION 'last_admin' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
