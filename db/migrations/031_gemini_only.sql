-- Design: docs/database-refactor-design.md. Keep immutable history intact.
UPDATE provider_keys SET deactivated_at=COALESCE(deactivated_at,CURRENT_TIMESTAMP)
 WHERE provider<>'gemini' AND deactivated_at IS NULL;
ALTER TABLE prompt_versions DROP CONSTRAINT version_provider_scope;
-- NOT VALID preserves historical rows while checking every future write.
ALTER TABLE prompt_versions ADD CONSTRAINT version_provider_scope
 CHECK(provider='gemini') NOT VALID;
ALTER TABLE provider_keys ADD CONSTRAINT provider_keys_gemini_only
 CHECK(provider='gemini') NOT VALID;
ALTER TABLE model_pricing ADD CONSTRAINT model_pricing_gemini_only
 CHECK(provider='gemini') NOT VALID;
CREATE FUNCTION enforce_gemini_version_reference() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM prompt_versions WHERE id=NEW.version_id AND provider<>'gemini')
 THEN RAISE EXCEPTION 'Only Gemini versions can be executed or activated' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION enforce_gemini_version_reference() FROM PUBLIC;
CREATE TRIGGER gemini_execution_only BEFORE INSERT ON runs
 FOR EACH ROW EXECUTE FUNCTION enforce_gemini_version_reference();
CREATE TRIGGER gemini_admission_only BEFORE INSERT ON run_reservations
 FOR EACH ROW EXECUTE FUNCTION enforce_gemini_version_reference();
CREATE TRIGGER gemini_deployment_only BEFORE INSERT OR UPDATE ON deployments
 FOR EACH ROW WHEN (NEW.status IN ('pending','active'))
 EXECUTE FUNCTION enforce_gemini_version_reference();
