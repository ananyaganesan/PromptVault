"""Generate a catalog dictionary and rollback-only SQL demonstrations on a test DB."""

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

ENTITIES = {
    "users": "Account identity, display name, credentials and authorization role.",
    "projects": "Owned workspace containing prompts and scoped memberships.",
    "project_invitations": "Pending, expiring recipient-accepted project access invitations.",
    "project_members": "Many-to-many access relationship between users and projects.",
    "prompts": "Named prompt identity within a project.",
    "prompt_versions": "Immutable template and configuration snapshots with lineage.",
    "runs": "Append-only execution ledger, physically partitioned by creation month.",
    "run_reservations": "Idempotent execution admission and cost reconciliation state.",
    "budgets": "Monthly execution limit targeting exactly one user or project.",
    "model_pricing": "Historical provider/model effective price windows.",
    "provider_keys": "Encrypted administrator-managed shared provider credentials.",
    "api_tokens": "Hashed, expiring and revocable project-scoped Serve credentials.",
    "deployments": "Prompt/version promotion, review and rollback lifecycle records.",
    "audit_events": "Append-only redacted change history and actor attribution.",
    "password_reset_tokens": "Hashed, expiring single-use password-reset credentials.",
    "password_history": "Previously used password hashes for reuse prevention.",
    "auth_sessions": "Server-side session lifetime and revocation state.",
    "schema_migrations": "Infrastructure record of applied migration versions/checksums.",
}

PURPOSES = {
    "id": "Surrogate row identity (runs also includes creation time in its primary key).",
    "email": "Case-insensitive unique account login email.",
    "display_name": "User-editable name shown across the application.",
    "password_hash": "Argon2id password digest; plaintext is never stored.",
    "role": "Account authorization role: user or admin.",
    "is_active": "Whether the account may authenticate and access resources.",
    "created_at": "Database timestamp when the record was created.",
    "updated_at": "Timestamp of the latest mutable state change.",
    "name": "Human-readable resource name (migration name for schema_migrations).",
    "key": "Stable resource lookup key; uniqueness scope is defined by constraints.",
    "description": "Optional resource description.",
    "owner_id": "User owning the project.",
    "project_id": "Referenced project/workspace.",
    "user_id": "Referenced account/actor or user budget target.",
    "invited_by": "Account issuing a project invitation.",
    "accepted_at": "Timestamp of recipient acceptance and membership creation.",
    "added_by": "User who granted membership, if retained.",
    "prompt_id": "Referenced prompt identity.",
    "version_id": "Referenced immutable prompt version.",
    "version_number": "Monotonically assigned version number within a prompt.",
    "parent_version_id": "Optional predecessor version in the same prompt.",
    "template_body": "Immutable prompt template text.",
    "variables": "Template variable-name snapshot as a JSON array.",
    "model_config": "Provider/model/generation settings captured for this version.",
    "commit_message": "Author's explanation of the version change.",
    "created_by": "User who created the resource.",
    "provider": "Provider identity; external execution is restricted by application policy.",
    "model": "Provider-specific model identifier.",
    "input_price_per_million": "Historical price per million input tokens.",
    "output_price_per_million": "Historical price per million output tokens.",
    "effective_from": "Inclusive start of the pricing validity window.",
    "effective_to": "Optional end of the pricing validity window.",
    "monthly_limit": "Exact decimal monthly execution allowance.",
    "timezone": "Timezone defining the target's monthly budget boundaries.",
    "alias": "Administrator's label for a provider credential.",
    "encrypted_secret": "Authenticated encrypted API key; never a plaintext response.",
    "deactivated_at": "Optional time when this provider credential was disabled.",
    "token_prefix": "Non-secret token label shown after one-time disclosure.",
    "token_hash": "SHA-256 digest of the one-time disclosed token.",
    "expires_at": "Time after which the credential/session is invalid.",
    "revoked_at": "Optional time of explicit credential/session revocation.",
    "revoked_by": "User who revoked the credential, if retained.",
    "environment": "Application promotion slot (dev/staging/prod), usable locally.",
    "status": "Lifecycle state constrained by the relation's enum/checks.",
    "request_note": "Requester's explanation for promotion.",
    "review_note": "Reviewer's decision explanation.",
    "rollback_reason": "Explanation of a rollback.",
    "rollback_of_id": "Deployment event being rolled back.",
    "requested_by": "User who requested the deployment.",
    "reviewed_by": "Optional user who reviewed the deployment.",
    "requested_at": "Time the promotion was requested.",
    "reviewed_at": "Optional time of the review decision.",
    "activated_at": "Optional time the version became active.",
    "input_variables": "Execution input snapshot as JSON.",
    "output_text": "Provider output, if execution produced a result.",
    "prompt_tokens": "Recorded input-token usage.",
    "completion_tokens": "Recorded output-token usage.",
    "latency_ms": "Recorded execution duration in milliseconds.",
    "cost": "Exact decimal cost snapshot; allowed external free executions use zero.",
    "error_code": "Normalized safe execution failure code, if any.",
    "request_id": "Correlation identifier connecting the request and audit/execution.",
    "actor_user_id": "Optional user responsible for the audited change.",
    "action": "Audited operation name.",
    "entity_type": "Relation/resource kind affected by the audited operation.",
    "entity_id": "Affected UUID resource identity, if applicable.",
    "before_data": "Redacted resource snapshot before the change.",
    "after_data": "Redacted resource snapshot after the change.",
    "used_at": "Optional time when a reset token was consumed.",
    "issued_at": "Time the server-side session was issued.",
    "revocation_reason": "Reason a session was revoked; consistent with revoked_at.",
    "idempotency_key": "User-scoped execution request deduplication key.",
    "request_fingerprint": "Digest binding an idempotency key to its request content.",
    "claim_token": "Internal execution-admission ownership credential.",
    "estimated_cost": "Reserved cost before provider execution.",
    "actual_cost": "Reconciled cost after execution, if known.",
    "run_id": "Optional execution ledger identity after reconciliation.",
    "run_created_at": "Creation time completing the composite run foreign key.",
    "version": "Applied migration number.",
    "checksum": "SHA-256 checksum protecting an applied migration from changes.",
    "applied_at": "Time the migration was applied.",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def catalog(connection):
    tables = connection.execute("""
        SELECT c.relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relispartition
        ORDER BY c.relname
    """).fetchall()
    require({row['name'] for row in tables} == set(ENTITIES), "ER inventory mismatch")
    for table in tables:
        name = table['name']
        table['purpose'] = ENTITIES[name]
        table['columns'] = connection.execute("""
            SELECT a.attname AS name, format_type(a.atttypid,a.atttypmod) AS type,
                   NOT a.attnotnull AS nullable, a.attidentity AS identity,
                   pg_get_expr(d.adbin,d.adrelid) AS default
            FROM pg_attribute a LEFT JOIN pg_attrdef d
              ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """, (name,)).fetchall()
        for column in table['columns']:
            column['purpose'] = PURPOSES[column['name']]
        table['constraints'] = connection.execute("""
            SELECT conname AS name, contype AS kind, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY conname
        """, (name,)).fetchall()
        require(any(row['kind'] == 'p' for row in table['constraints']), f"Missing PK: {name}")
        table['indexes'] = connection.execute("""
            SELECT indexname AS name,indexdef AS definition FROM pg_indexes
            WHERE schemaname='public' AND tablename=%s ORDER BY indexname
        """, (name,)).fetchall()
    return tables


def demonstrations(connection):
    owner = connection.execute("SELECT id FROM users WHERE is_active ORDER BY id LIMIT 1").fetchone()
    require(owner is not None, "Seed at least one active user")
    key = f"academic-{uuid4().hex}"
    row = connection.execute("""
        INSERT INTO projects(name,key,owner_id) VALUES ('Academic CRUD',%s,%s) RETURNING id
    """, (key, owner['id'])).fetchone()
    project = row['id']
    membership = connection.execute(
        "SELECT count(*) AS count FROM project_members WHERE project_id=%s AND user_id=%s",
        (project, owner['id']),
    ).fetchone()['count']
    require(membership == 1, "Owner-membership trigger failed")
    connection.execute("UPDATE projects SET name='Academic updated' WHERE id=%s", (project,))
    require(connection.execute("SELECT name FROM projects WHERE id=%s", (project,)).fetchone()
            ['name'] == 'Academic updated', "CRUD update failed")
    # A savepoint rollback proves atomic recovery without altering real records.
    connection.execute("SAVEPOINT academic_rollback")
    connection.execute("UPDATE projects SET name='Should roll back' WHERE id=%s", (project,))
    connection.execute("ROLLBACK TO SAVEPOINT academic_rollback")
    require(connection.execute("SELECT name FROM projects WHERE id=%s", (project,)).fetchone()
            ['name'] == 'Academic updated', "Transaction rollback failed")
    connection.execute("SAVEPOINT invalid_fk")
    try:
        connection.execute("INSERT INTO prompts(project_id,key,name) VALUES (%s,'bad','bad')",
                           (uuid4(),))
    except psycopg.errors.ForeignKeyViolation:
        connection.execute("ROLLBACK TO SAVEPOINT invalid_fk")
    else:
        raise RuntimeError("Invalid FK was accepted")
    connection.execute("DELETE FROM projects WHERE id=%s", (project,))
    require(connection.execute("SELECT count(*) AS count FROM projects WHERE id=%s", (project,))
            .fetchone()['count'] == 0, "CRUD delete failed")
    require(connection.execute("SELECT count(*) AS count FROM project_members WHERE project_id=%s",
                               (project,)).fetchone()['count'] == 0, "Membership cascade failed")
    audits = connection.execute("""
        SELECT action,count(*) AS events FROM audit_events
        WHERE entity_id=%s AND entity_type='projects' GROUP BY action ORDER BY action
    """, (project,)).fetchall()
    require(len(audits) == 3, "CRUD audit trigger evidence missing")
    connection.execute("CALL perform_system_maintenance('365 days','365 days','365 days')")
    return {"crud": "insert/read/update/delete passed", "owner_membership_trigger": membership,
            "rollback": "savepoint restored prior value", "invalid_foreign_key": "23503 rejected",
            "cascade_delete": "membership removed", "audit_trigger": audits,
            "procedure_call": "perform_system_maintenance succeeded",
            "cleanup": "all demonstration writes rolled back"}


def markdown(tables):
    lines = ["# PromptVault column dictionary", "",
             "Generated from the live PostgreSQL catalog; see academic evidence for its migration revision.",
             "Logical tables exclude physical partitions and views. No stored row values are exported.", ""]
    for table in tables:
        lines.extend([f"## `{table['name']}`", "", table['purpose'], "",
                      "| Column | Type | Nullable | Default / identity | Purpose |",
                      "|---|---|---|---|---|"])
        for column in table['columns']:
            default = column['default'] or ("GENERATED IDENTITY" if column['identity'] else "—")
            values = [column['name'], column['type'], str(column['nullable']), default, column['purpose']]
            lines.append("| " + " | ".join(str(value).replace('|', '\\|') for value in values) + " |")
        lines.extend(["", "Constraints and keys:", ""])
        lines.extend(f"- `{row['definition']}`" for row in table['constraints'])
        lines.extend(["", "Indexes:", ""])
        lines.extend(f"- `{row['definition']}`" for row in table['indexes'])
        lines.append("")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('evidence/academic'))
    parser.add_argument('--dictionary', type=Path, default=Path('docs/data-dictionary.md'))
    args = parser.parse_args()
    require(urlsplit(args.database_url).path.endswith('_test'), "Requires disposable _test database")
    with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
        require(connection.execute("SELECT current_database() AS name").fetchone()['name']
                .endswith('_test'), "Connected database must end in _test")
        tables = catalog(connection)
        migrations = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        views = connection.execute("""
            SELECT c.relname AS name,c.relkind AS kind,pg_get_viewdef(c.oid,true) AS definition
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('v','m') ORDER BY c.relname
        """).fetchall()
        triggers = connection.execute("""
            SELECT tgname AS name,pg_get_triggerdef(oid) AS definition FROM pg_trigger
            WHERE NOT tgisinternal AND tgrelid IN
              (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace
               AND NOT relispartition) ORDER BY tgname
        """).fetchall()
        procedure = connection.execute("""
            SELECT pg_get_functiondef(oid) AS definition FROM pg_proc
            WHERE pronamespace='public'::regnamespace AND prokind='p'
              AND proname='perform_system_maintenance'
        """).fetchall()
        # Rollback-only fixture for nonempty aggregates; this is not an LLM call.
        fixture = connection.execute("""
            SELECT p.owner_id,p.id AS project_id,pr.id AS prompt_id,v.id AS version_id
            FROM projects p JOIN prompts pr ON pr.project_id=p.id
            JOIN prompt_versions v ON v.prompt_id=pr.id ORDER BY p.id,v.id LIMIT 1
        """).fetchone()
        require(fixture is not None, "Seed a prompt version before collecting evidence")
        connection.execute("""
            INSERT INTO runs(user_id,project_id,prompt_id,version_id,status,provider,model,
                             output_text,prompt_tokens,completion_tokens,cost)
            VALUES (%s,%s,%s,%s,'completed','mock','deterministic-v1',
                    'Synthetic academic SQL fixture; no provider request',7,3,0)
        """, (fixture['owner_id'],fixture['project_id'],fixture['prompt_id'],fixture['version_id']))
        joins = connection.execute("""
            SELECT p.key AS project,pr.key AS prompt,v.version_number
            FROM projects p JOIN prompts pr ON pr.project_id=p.id
            JOIN prompt_versions v ON v.prompt_id=pr.id ORDER BY p.key,pr.key,v.version_number
        """).fetchall()
        aggregates = connection.execute("""
            SELECT status,count(*) AS runs,sum(cost) AS cost FROM runs GROUP BY status ORDER BY status
        """).fetchall()
        view_samples = connection.execute(
            "SELECT provider,model,completed_runs,cost FROM monthly_costs ORDER BY provider,model"
        ).fetchall()
        plans = connection.execute("""
            EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)
            SELECT id,version_number FROM prompt_versions
            WHERE prompt_id=(SELECT id FROM prompts ORDER BY id LIMIT 1)
            ORDER BY version_number DESC LIMIT 25
        """).fetchone()
        require(bool(joins) and bool(aggregates) and bool(view_samples), "Seeded query evidence is empty")
        result = demonstrations(connection)
        connection.rollback()
        require(connection.execute("SELECT count(*) AS count FROM projects WHERE key LIKE 'academic-%'")
                .fetchone()['count'] == 0, "Demonstration data remains")
        report = {"generated_at": datetime.now(UTC).isoformat(), "logical_tables": len(tables),
                  "migrations": migrations, "tables": tables, "views": views, "triggers": triggers,
                  "procedure": procedure, "joins": joins, "aggregates": aggregates,
                  "view_samples": view_samples, "query_plan": plans, "demonstrations": result,
                  "execution_fixture": "rollback-only synthetic mock row; no provider call"}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dictionary.parent.mkdir(parents=True, exist_ok=True)
    args.dictionary.write_text(markdown(tables), encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    sources = [Path(__file__), root / 'docs' / 'erd.md', root / 'docs' / 'normalization.md']
    sources.extend(sorted((root / 'db' / 'migrations').glob('*.sql')))
    report['source_sha256'] = {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sources
    }
    report['dictionary_sha256'] = sha256(args.dictionary.read_bytes()).hexdigest()
    (args.output_dir / 'database-evidence.json').write_text(
        json.dumps(report, default=str, indent=2) + '\n', encoding='utf-8')
    print(f"Verified {len(tables)} logical tables; dictionary and SQL evidence saved.")


if __name__ == '__main__':
    main()
