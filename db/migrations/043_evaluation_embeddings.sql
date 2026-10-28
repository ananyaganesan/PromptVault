-- Preserve existing evaluation history; allow audited Gemini embedding calls.
ALTER TABLE evaluation_calls DROP CONSTRAINT evaluation_calls_purpose_check;
ALTER TABLE evaluation_calls ADD CONSTRAINT evaluation_calls_purpose_check
    CHECK (purpose IN ('judge', 'suggest', 'improve', 'embed'));
