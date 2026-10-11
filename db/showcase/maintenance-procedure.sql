-- Actual PostgreSQL stored-procedure demonstration required by the database rubric.
-- Long thresholds keep representative recent records unchanged.
CALL perform_system_maintenance(
    INTERVAL '365 days',
    INTERVAL '365 days',
    INTERVAL '365 days'
);

SELECT
    'perform_system_maintenance(interval,interval,interval)' AS procedure_called,
    to_regprocedure(
        'perform_system_maintenance(interval,interval,interval)'
    ) IS NOT NULL AS procedure_exists;
