-- Retire the Context Compiler at the user's request. Keep migration 034 intact
-- because it has already been applied to persistent local databases.
-- Drop only this feature's tables; do not cascade into other application data.
DROP TABLE compiled_prompts;
DROP TABLE context_warnings;
DROP TABLE context_sources;
DROP TABLE context_compilations;
DROP FUNCTION protect_context_snapshot();
