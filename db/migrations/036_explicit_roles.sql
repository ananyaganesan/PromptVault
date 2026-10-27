-- Preserve existing highest-privilege accounts by renaming their enum value.
-- Enum additions are committed before the next migration uses the new value.
ALTER TYPE user_role RENAME VALUE 'admin' TO 'super_admin';

-- Stored authorization routines must use the renamed value too. Replace only
-- the exact role literal in existing public routines; preserve grants/owners.
DO $$
DECLARE routine RECORD; definition TEXT;
BEGIN
    FOR routine IN
        SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
          AND p.prosrc LIKE '%''admin''%'
    LOOP
        definition := replace(pg_get_functiondef(routine.oid), '''admin''', '''super_admin''');
        EXECUTE definition;
    END LOOP;
END $$;
ALTER TYPE user_role ADD VALUE 'admin';
