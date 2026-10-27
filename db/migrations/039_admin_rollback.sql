-- Admins inherit operational rollback; database/system controls remain Super Admin only.
DO $$
DECLARE definition TEXT;
BEGIN
    definition := pg_get_functiondef(
        'rollback_deployment(uuid,uuid,uuid,text,deployment_environment)'::regprocedure
    );
    IF position('role = ''super_admin'' AND is_active' IN definition) = 0 THEN
        RAISE EXCEPTION 'Unexpected rollback authorization definition';
    END IF;
    definition := replace(definition,
        'role = ''super_admin'' AND is_active',
        'role IN (''admin'', ''super_admin'') AND is_active AND is_approved AND email_verified_at IS NOT NULL');
    EXECUTE definition;
END $$;
