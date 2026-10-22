"""Add a non-destructive local showcase using application services, without external calls."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app.config import Settings
from api.app.db.pool import create_pool
from api.app.errors import AppError
from api.app.providers.catalog import MODELS
from api.app.repositories.admin import AdminRepository
from api.app.repositories.deployments import DeploymentRepository
from api.app.repositories.projects import ProjectRepository
from api.app.repositories.prompts import PromptRepository
from api.app.repositories.runs import RunRepository
from api.app.repositories.tokens import TokenRepository
from api.app.repositories.users import UserRepository
from api.app.repositories.versions import VersionRepository
from api.app.schemas.admin import ModelPricingCreate
from api.app.schemas.budgets import BudgetCreate
from api.app.schemas.deployments import DeploymentCreate
from api.app.schemas.projects import ProjectCreate
from api.app.schemas.prompts import PromptCreate
from api.app.schemas.runs import RunCreate
from api.app.schemas.tokens import ApiTokenCreate
from api.app.schemas.versions import PromptVersionCreate
from api.app.services.admin import AdminGovernanceService
from api.app.services.deployments import DeploymentService
from api.app.services.playground import RunExecutionService
from api.app.services.projects import ProjectService
from api.app.services.prompt_versioning import PromptVersioningService
from api.app.services.serve import TokenService

MOCK = {
    "provider": "mock",
    "model": "deterministic-v1",
    "temperature": 0,
    "max_output_tokens": 500,
}
PROJECTS = [
    {
        "key": "demo-support-desk",
        "name": "Demo · Support Desk",
        "description": "Showcase: customer support templates, safe replies and controlled releases.",
        "prompts": [
            {
                "key": "order-reply",
                "name": "Order support reply",
                "templates": [
                    "Reply to {{customer_message}} about order {{order_id}}.",
                    "You are a support agent. Reply empathetically to {{customer_message}} about order {{order_id}}. Use only this policy: {{policy}}. Never invent a refund or delivery date.",
                    "You are a support agent. Customer: {{customer_message}}\nOrder: {{order_id}}\nApproved policy: {{policy}}\nWrite under 120 words with: Acknowledgement, Policy-based next step, Escalation if needed. Do not invent facts, promises or private account data.",
                ],
                "values": {
                    "customer_message": "My parcel arrived with a cracked mug. Can I get a replacement?",
                    "order_id": "PV-1042",
                    "policy": "Damaged items reported within 7 days qualify for a replacement after photo review.",
                },
            },
            {
                "key": "ticket-triage",
                "name": "Support ticket triage",
                "templates": [
                    "Classify this ticket: {{ticket}}.",
                    "Classify {{ticket}} into billing, delivery, product or account. Explain the urgency using {{priority_rules}}.",
                    "Ticket: {{ticket}}\nRules: {{priority_rules}}\nReturn category, priority, reason and suggested_team. Quote evidence from the ticket. Do not include personal data or invent details.",
                ],
                "values": {
                    "ticket": "I was charged twice for order PV-1042 and need help before the billing cutoff.",
                    "priority_rules": "Duplicate payments are high priority; account takeover is urgent; ordinary delivery questions are normal.",
                },
            },
        ],
    },
    {
        "key": "demo-study-coach",
        "name": "Demo · Study Coach",
        "description": "Showcase: improve educational explanations and quiz structure across versions.",
        "prompts": [
            {
                "key": "concept-explainer",
                "name": "Database concept explainer",
                "templates": [
                    "Explain {{topic}} to a student.",
                    "Explain {{topic}} to {{audience}}. Use a simple analogy and one concrete database example.",
                    "Topic: {{topic}}\nAudience: {{audience}}\nGive a short definition, an analogy, a PostgreSQL example and one common mistake. End with a question to check understanding. Clearly label assumptions.",
                ],
                "values": {
                    "topic": "third normal form and transitive dependencies",
                    "audience": "a second-year computer science student",
                },
            },
            {
                "key": "practice-quiz",
                "name": "Revision quiz generator",
                "templates": [
                    "Write a quiz about {{topic}}.",
                    "Write {{question_count}} questions about {{topic}} for {{level}}. Include answers.",
                    "Create {{question_count}} questions about {{topic}} for {{level}}. Mix recall and application. Number each question; place answers with explanations in a separate section. Use unambiguous wording and avoid duplicate questions.",
                ],
                "values": {
                    "topic": "SQL joins, foreign keys and transactions",
                    "question_count": "3",
                    "level": "undergraduate beginners",
                },
            },
        ],
    },
    {
        "key": "demo-release-notes",
        "name": "Demo · Release Notes",
        "description": "Showcase: engineering summaries, rollback readiness and failure recovery.",
        "prompts": [
            {
                "key": "release-summary",
                "name": "Customer-facing release summary",
                "templates": [
                    "Summarize these changes: {{changes}}.",
                    "Summarize {{changes}} for {{audience}}. Group features, fixes and known limitations.",
                    "Changes: {{changes}}\nAudience: {{audience}}\nWrite a title, three benefit-focused bullets and a known-limitations section. State only facts in the input. Do not expose internal credentials, issue IDs or implementation details irrelevant to users.",
                ],
                "values": {
                    "changes": "Added verified-email registration; fixed duplicate prompt version numbers; added project invitations. Real provider access depends on account free-tier quota.",
                    "audience": "PromptVault demo users",
                },
            },
            {
                "key": "incident-update",
                "name": "Service incident update",
                "templates": [
                    "Write an incident update for {{incident}}.",
                    "Write an update for {{incident}} using the current status {{status}}. Avoid unsupported recovery promises.",
                    "Incident: {{incident}}\nConfirmed status: {{status}}\nReturn Impact, Current action and Next update. Separate confirmed facts from unknowns. Do not invent an ETA or blame a provider without evidence.",
                ],
                "values": {
                    "incident": "Some verification emails are delayed after SMTP authentication failed.",
                    "status": "A replacement App Password has been configured and SMTP authentication now passes; end-to-end inbox delivery still needs confirmation.",
                },
            },
        ],
    },
]
COMMITS = [
    "Initial baseline for the local demo",
    "Add context and factual guardrails",
    "Define output structure and acceptance criteria",
]


async def prepare(owner_email):
    from urllib.parse import urlsplit

    settings = Settings(_env_file=ROOT / ".env")
    parts = urlsplit(settings.database_url)
    if (
        settings.environment != "development"
        or parts.hostname not in {"localhost", "127.0.0.1", "::1"}
        or (parts.port or 5432) != 5432
        or parts.path != "/promptvault"
    ):
        raise ValueError(
            "Demo preparation requires development localhost:5432/promptvault"
        )
    pool = create_pool(settings)
    await pool.open()
    request_id = "demo-prepare-" + uuid4().hex
    report = {
        "prepared_at": datetime.now(UTC).isoformat(),
        "owner": owner_email,
        "projects": [],
        "runs": [],
    }
    runnable = []
    try:
        async with pool.connection() as c:
            actor = await UserRepository(c).get_by_email(owner_email)
            if (
                not actor
                or actor.role != "admin"
                or not actor.is_active
                or not actor.email_verified_at
            ):
                raise ValueError(
                    "Select an existing active, verified administrator; accounts are never modified"
                )
        # All metadata is one transaction. Existing project keys fail closed on owner/description mismatch.
        async with pool.connection() as c, c.transaction():
            projects = ProjectService(
                ProjectRepository(c), UserRepository(c), request_id, settings
            )
            prompts = PromptVersioningService(
                PromptRepository(c),
                VersionRepository(c),
                ProjectRepository(c),
                request_id,
                allow_mock=True,
            )
            admin = AdminGovernanceService(
                AdminRepository(c),
                request_id,
                settings.resolved_provider_encryption_key,
                allow_mock=True,
            )
            for spec in PROJECTS:
                row = await (
                    await c.execute(
                        "SELECT id,owner_id,description FROM projects WHERE key=%s",
                        (spec["key"],),
                    )
                ).fetchone()
                if row:
                    if (
                        row["owner_id"] != actor.id
                        or row["description"] != spec["description"]
                    ):
                        raise ValueError(
                            "Existing showcase key belongs to unrelated data"
                        )
                    pid = row["id"]
                else:
                    project = await projects.create(
                        ProjectCreate(
                            **{k: spec[k] for k in ("key", "name", "description")}
                        ),
                        actor,
                    )
                    pid = project.id
                entry = {
                    "name": spec["name"],
                    "key": spec["key"],
                    "id": str(pid),
                    "prompts": [],
                }
                for ps in spec["prompts"]:
                    existing = await (
                        await c.execute(
                            "SELECT id FROM prompts WHERE project_id=%s AND key=%s",
                            (pid, ps["key"]),
                        )
                    ).fetchone()
                    if existing:
                        prompt_id = existing["id"]
                        versions = (
                            await prompts.list_versions(
                                prompt_id,
                                actor,
                                page=1,
                                page_size=100,
                                sort="version_number",
                                direction="asc",
                            )
                        ).items
                        if len(versions) < 3 or any(
                            v.template_body != ps["templates"][i]
                            or v.model_configuration.model_dump() != MOCK
                            for i, v in enumerate(versions[:3])
                        ):
                            raise ValueError(
                                "Existing showcase versions differ; refusing to overwrite"
                            )
                    else:
                        p = await prompts.create_prompt(
                            pid,
                            PromptCreate(
                                key=ps["key"],
                                name=ps["name"],
                                description="Local showcase; deterministic mock execution, not external AI output.",
                                template_body=ps["templates"][0],
                                model_config=MOCK,
                                commit_message=COMMITS[0],
                            ),
                            actor,
                        )
                        prompt_id = p.id
                        versions = [p.latest_version]
                        for i in (1, 2):
                            versions.append(
                                await prompts.create_version(
                                    prompt_id,
                                    PromptVersionCreate(
                                        parent_version_id=versions[-1].id,
                                        template_body=ps["templates"][i],
                                        model_config=MOCK,
                                        commit_message=COMMITS[i],
                                    ),
                                    actor,
                                )
                            )
                    for version in versions[:3]:
                        values = {k: ps["values"][k] for k in version.variables}
                        runnable.append((version, values, False))
                    entry["prompts"].append(
                        {
                            "id": str(prompt_id),
                            "key": ps["key"],
                            "name": ps["name"],
                            "versions": [str(v.id) for v in versions[:3]],
                            "variables": ps["values"],
                        }
                    )
                if not await (
                    await c.execute("SELECT 1 FROM budgets WHERE project_id=%s", (pid,))
                ).fetchone():
                    await admin.create_budget(
                        BudgetCreate(
                            project_id=pid,
                            monthly_limit="10",
                            timezone="Asia/Kolkata",
                        ),
                        actor,
                    )
                report["projects"].append(entry)
            # A live configuration is saved, never executed by this helper.
            pid = report["projects"][0]["id"]
            if not await (
                await c.execute(
                    "SELECT 1 FROM prompts WHERE project_id=%s AND key='live-gemini-reply'",
                    (pid,),
                )
            ).fetchone():
                live = next(m for m in MODELS if m.provider == "gemini")
                p = await prompts.create_prompt(
                    pid,
                    PromptCreate(
                        key="live-gemini-reply",
                        name="Live Gemini reply (free-tier check required)",
                        description="Saved live-provider configuration. No external execution was performed by demo preparation.",
                        template_body=PROJECTS[0]["prompts"][0]["templates"][2],
                        model_config={
                            "provider": live.provider,
                            "model": live.id,
                            "temperature": 0,
                            "max_output_tokens": 500,
                        },
                        commit_message="Prepare optional live Gemini comparison; not yet executed",
                    ),
                    actor,
                )
                report["live_prompt_id"] = str(p.id)
            # A real execution of the internal failure adapter leaves a genuine failed ledger row.
            pid = report["projects"][2]["id"]
            recovery = await (
                await c.execute(
                    "SELECT id FROM prompts WHERE project_id=%s AND key='provider-recovery-drill'",
                    (pid,),
                )
            ).fetchone()
            if not await (
                await c.execute(
                    "SELECT 1 FROM model_pricing WHERE provider='mock' AND model='deterministic-error'",
                )
            ).fetchone():
                await admin.create_pricing(
                    ModelPricingCreate(
                        provider="mock",
                        model="deterministic-error",
                        input_price_per_million="0",
                        output_price_per_million="0",
                        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                    actor,
                )
            if recovery:
                versions = (
                    await prompts.list_versions(
                        recovery["id"],
                        actor,
                        page=1,
                        page_size=100,
                        sort="version_number",
                        direction="asc",
                    )
                ).items
            else:
                p = await prompts.create_prompt(
                    pid,
                    PromptCreate(
                        key="provider-recovery-drill",
                        name="Provider recovery drill (simulated)",
                        description="Intentional mock failure in v1, working deterministic adapter in v2. No external outage is simulated as real.",
                        template_body="Explain the recovery step for {{incident}}.",
                        model_config=MOCK | {"model": "deterministic-error"},
                        commit_message="Demonstrate intentional internal provider failure",
                    ),
                    actor,
                )
                v = await prompts.create_version(
                    p.id,
                    PromptVersionCreate(
                        parent_version_id=p.latest_version.id,
                        template_body="Explain the recovery step for {{incident}}. State what was checked and what remains unverified.",
                        model_config=MOCK,
                        commit_message="Recover by choosing the working internal adapter",
                    ),
                    actor,
                )
                versions = [p.latest_version, v]
            runnable.extend(
                (
                    v,
                    {"incident": "A test provider returned an intentional error"},
                    i == 0,
                )
                for i, v in enumerate(versions[:2])
            )
        # Run service owns admission and reconciliation transactions, just as for the Playground.
        for v, values, expected_failure in runnable:
            service = RunExecutionService(
                pool,
                request_id + "-" + str(v.id),
                settings.provider_timeout_seconds,
                settings.resolved_provider_encryption_key,
                settings.gemini_api_base_url,
                settings.max_concurrent_runs_per_user,
                allow_mock=True,
            )
            async with pool.connection() as c:
                existing = await (
                    await c.execute(
                        "SELECT run_id FROM run_reservations WHERE user_id=%s AND idempotency_key=%s",
                        (actor.id, "showcase:" + str(v.id)),
                    )
                ).fetchone()
            if existing:
                continue
            try:
                r = await service.execute(
                    RunCreate(version_id=v.id, variables=values),
                    actor,
                    idempotency_key="showcase:" + str(v.id),
                )
                if expected_failure:
                    raise RuntimeError("Failure adapter unexpectedly succeeded")
                report["runs"].append({"id": str(r.id), "status": r.status})
            except AppError as e:
                if not expected_failure or e.code != "provider_error":
                    raise
                report["runs"].append(
                    {"version_id": str(v.id), "status": "failed", "error": e.code}
                )
        async with pool.connection() as c, c.transaction():
            deployments = DeploymentService(
                DeploymentRepository(c),
                VersionRepository(c),
                RunRepository(c),
                request_id,
            )
            for index, entry in enumerate(report["projects"]):
                main = entry["prompts"][0]
                if await (
                    await c.execute(
                        "SELECT 1 FROM deployments WHERE prompt_id=%s",
                        (main["id"],),
                    )
                ).fetchone():
                    continue
                await deployments.create(
                    DeploymentCreate(
                        version_id=main["versions"][0],
                        environment="dev",
                        request_note="Local showcase baseline",
                    ),
                    actor,
                )
                await deployments.create(
                    DeploymentCreate(
                        version_id=main["versions"][2],
                        environment="staging",
                        request_note="Structured v3 ready for review; mock evidence only",
                    ),
                    actor,
                )
                baseline = await deployments.create(
                    DeploymentCreate(
                        version_id=main["versions"][1],
                        environment="prod",
                        request_note="Local workflow baseline; no public hosting",
                    ),
                    actor,
                )
                await deployments.review(
                    baseline.id,
                    actor,
                    approve=True,
                    review_note="Approved for local demonstration; deterministic evidence only",
                )
                if index == 2:
                    candidate = await deployments.create(
                        DeploymentCreate(
                            version_id=main["versions"][2],
                            environment="prod",
                            request_note="Candidate to demonstrate rejection history",
                        ),
                        actor,
                    )
                    await deployments.review(
                        candidate.id,
                        actor,
                        approve=False,
                        review_note="Demo rejection: require an independent live-provider evaluation before advancing",
                    )
                else:
                    await deployments.create(
                        DeploymentCreate(
                            version_id=main["versions"][2],
                            environment="prod",
                            request_note="Demo candidate: review diff and v3 mock run; left pending for the presentation",
                        ),
                        actor,
                    )
            # Persist only a local private runtime token, never account passwords or provider keys.
            secret_path = ROOT / "secrets/demo-runtime.env"
            token_service = TokenService(TokenRepository(c), request_id)
            if not secret_path.exists():
                token = await token_service.create(
                    ApiTokenCreate(
                        project_id=report["projects"][0]["id"],
                        name="Local showcase Serve client",
                        expires_at=datetime.now(UTC) + timedelta(days=7),
                    ),
                    actor,
                )
                secret_path.parent.mkdir(exist_ok=True, mode=0o700)
                fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write("DEMO_RUNTIME_TOKEN=" + token.token + "\n")
            admin = AdminGovernanceService(
                AdminRepository(c),
                request_id,
                settings.resolved_provider_encryption_key,
                allow_mock=True,
            )
            await admin.refresh_views(actor)
        async with pool.connection() as c:
            ids = [entry["id"] for entry in report["projects"]]
            rows = await (
                await c.execute(
                    "SELECT r.id,r.status,r.provider,r.error_code FROM runs r "
                    "WHERE r.project_id = ANY(%s::uuid[]) ORDER BY r.created_at",
                    (ids,),
                )
            ).fetchall()
            report["runs"] = [{**row, "id": str(row["id"])} for row in rows]
            live_row = await (
                await c.execute(
                    "SELECT id FROM prompts WHERE project_id=%s AND key='live-gemini-reply'",
                    (report["projects"][0]["id"],),
                )
            ).fetchone()
            report["live_prompt_id"] = str(live_row["id"])
        output = ROOT / "evidence/demo/showcase.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            "Showcase ready: 3 projects, 8 prompts, 21 versions; no external calls or emails sent."
        )
        print(
            "Summary: evidence/demo/showcase.json; runtime token: secrets/demo-runtime.env (private)."
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner-email", required=True, help="Existing verified local admin account"
    )
    args = parser.parse_args()
    asyncio.run(prepare(args.owner_email))
