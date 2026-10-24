-- PostgreSQL versions that expose NOT NULL constraints in pg_constraint keep
-- their generated names when a relation is renamed. Normalize those catalog
-- names where present; older supported versions simply have nothing to rename.
DO $migration$
DECLARE
    constraint_record RECORD;
BEGIN
    FOR constraint_record IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.spend_limits'::regclass
          AND conname IN (
              'budgets_id_not_null',
              'budgets_monthly_limit_not_null',
              'budgets_timezone_not_null',
              'budgets_created_at_not_null',
              'budgets_updated_at_not_null'
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE public.spend_limits RENAME CONSTRAINT %I TO %I',
            constraint_record.conname,
            replace(constraint_record.conname, 'budgets_', 'spend_limits_')
        );
    END LOOP;
END
$migration$;
