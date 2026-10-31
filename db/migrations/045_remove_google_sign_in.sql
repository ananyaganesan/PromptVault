-- Reverse the unused Google sign-in schema while preserving migration history.
DROP INDEX IF EXISTS users_google_sub_unique;
ALTER TABLE users DROP COLUMN IF EXISTS google_sub;
