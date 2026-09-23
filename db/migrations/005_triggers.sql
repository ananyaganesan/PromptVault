CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER projects_set_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER prompts_set_updated_at
BEFORE UPDATE ON prompts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER budgets_set_updated_at
BEFORE UPDATE ON budgets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION reject_immutable_row_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER prompt_versions_are_immutable
BEFORE UPDATE OR DELETE ON prompt_versions
FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();

CREATE TRIGGER runs_are_append_only
BEFORE UPDATE OR DELETE ON runs
FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();

CREATE TRIGGER audit_events_are_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_row_change();

CREATE OR REPLACE FUNCTION add_project_owner_membership()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO project_members (project_id, user_id, added_by)
    VALUES (NEW.id, NEW.owner_id, NEW.owner_id)
    ON CONFLICT (project_id, user_id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER projects_add_owner_membership
AFTER INSERT ON projects
FOR EACH ROW EXECUTE FUNCTION add_project_owner_membership();

CREATE OR REPLACE FUNCTION prevent_project_owner_removal()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM projects
        WHERE id = OLD.project_id AND owner_id = OLD.user_id
    ) THEN
        RAISE EXCEPTION 'project owner membership cannot be removed'
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER project_members_preserve_owner
BEFORE DELETE ON project_members
FOR EACH ROW EXECUTE FUNCTION prevent_project_owner_removal();

CREATE OR REPLACE FUNCTION preserve_last_active_admin()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    removes_admin BOOLEAN;
BEGIN
    removes_admin := OLD.role = 'admin'
        AND OLD.is_active
        AND (
            TG_OP = 'DELETE'
            OR NEW.role <> 'admin'
            OR NOT NEW.is_active
        );
    IF removes_admin AND NOT EXISTS (
        SELECT 1
        FROM users
        WHERE id <> OLD.id AND role = 'admin' AND is_active
    ) THEN
        RAISE EXCEPTION 'the last active admin cannot be removed'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_preserve_last_active_admin
BEFORE UPDATE OF role, is_active OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION preserve_last_active_admin();

CREATE OR REPLACE FUNCTION record_audit_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    actor_text TEXT := nullif(current_setting('app.user_id', true), '');
    current_request_id TEXT := nullif(current_setting('app.request_id', true), '');
    old_document JSONB;
    new_document JSONB;
    resource_id UUID;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        old_document := to_jsonb(OLD) - ARRAY['password_hash', 'encrypted_secret', 'token_hash'];
    END IF;
    IF TG_OP <> 'DELETE' THEN
        new_document := to_jsonb(NEW) - ARRAY['password_hash', 'encrypted_secret', 'token_hash'];
    END IF;

    resource_id := COALESCE(
        nullif(new_document ->> 'id', '')::uuid,
        nullif(old_document ->> 'id', '')::uuid
    );
    INSERT INTO audit_events (
        actor_user_id,
        action,
        entity_type,
        entity_id,
        before_data,
        after_data,
        request_id
    )
    VALUES (
        actor_text::uuid,
        lower(TG_OP),
        TG_TABLE_NAME,
        resource_id,
        old_document,
        new_document,
        current_request_id
    );
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER users_audit
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER projects_audit
AFTER INSERT OR UPDATE OR DELETE ON projects
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER project_members_audit
AFTER INSERT OR DELETE ON project_members
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER prompts_audit
AFTER INSERT OR UPDATE OR DELETE ON prompts
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER prompt_versions_audit
AFTER INSERT ON prompt_versions
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER deployments_audit
AFTER INSERT OR UPDATE ON deployments
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER budgets_audit
AFTER INSERT OR UPDATE OR DELETE ON budgets
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER provider_keys_audit
AFTER INSERT OR UPDATE ON provider_keys
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER api_tokens_audit
AFTER INSERT OR UPDATE ON api_tokens
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
CREATE TRIGGER model_pricing_audit
AFTER INSERT ON model_pricing
FOR EACH ROW EXECUTE FUNCTION record_audit_event();
