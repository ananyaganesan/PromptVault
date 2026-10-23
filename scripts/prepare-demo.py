"""Prepare Gemini prompt/version metadata without provider calls, mail or release changes."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psycopg
from psycopg.types.json import Jsonb

from api.app.config import Settings
from api.app.db.commands import require_development_seed
from api.app.providers.catalog import MODELS

PROJECTS = [
    {
        "description": "Showcase: customer support templates, safe replies and controlled "
        "releases.",
        "key": "demo-support-desk",
        "name": "Demo · Support Desk",
        "prompts": [
            {
                "key": "order-reply",
                "name": "Order support reply",
                "templates": [
                    "Reply to {{customer_message}} about order {{order_id}}.",
                    ("You are a support agent. Reply empathetically to "
                    "{{customer_message}} about order {{order_id}}. Use only "
                    "this policy: {{policy}}. Never invent a refund or delivery "
                    "date."),
                    ("You are a support agent. Customer: {{customer_message}}\n"
                    "Order: {{order_id}}\n"
                    "Approved policy: {{policy}}\n"
                    "Write under 120 words with: Acknowledgement, Policy-based "
                    "next step, Escalation if needed. Do not invent facts, "
                    "promises or private account data."),
                ],
                "values": {
                    "customer_message": "My parcel arrived with a cracked mug. Can "
                    "I get a replacement?",
                    "order_id": "PV-1042",
                    "policy": "Damaged items reported within 7 days qualify for a "
                    "replacement after photo review.",
                },
            },
            {
                "key": "ticket-triage",
                "name": "Support ticket triage",
                "templates": [
                    "Classify this ticket: {{ticket}}.",
                    ("Classify {{ticket}} into billing, delivery, product or "
                    "account. Explain the urgency using {{priority_rules}}."),
                    ("Ticket: {{ticket}}\n"
                    "Rules: {{priority_rules}}\n"
                    "Return category, priority, reason and suggested_team. "
                    "Quote evidence from the ticket. Do not include personal "
                    "data or invent details."),
                ],
                "values": {
                    "priority_rules": "Duplicate payments are high priority; "
                    "account takeover is urgent; ordinary "
                    "delivery questions are normal.",
                    "ticket": "I was charged twice for order PV-1042 and need help "
                    "before the billing cutoff.",
                },
            },
        ],
    },
    {
        "description": "Showcase: improve educational explanations and quiz structure across "
        "versions.",
        "key": "demo-study-coach",
        "name": "Demo · Study Coach",
        "prompts": [
            {
                "key": "concept-explainer",
                "name": "Database concept explainer",
                "templates": [
                    "Explain {{topic}} to a student.",
                    ("Explain {{topic}} to {{audience}}. Use a simple analogy "
                    "and one concrete database example."),
                    ("Topic: {{topic}}\n"
                    "Audience: {{audience}}\n"
                    "Give a short definition, an analogy, a PostgreSQL example "
                    "and one common mistake. End with a question to check "
                    "understanding. Clearly label assumptions."),
                ],
                "values": {
                    "audience": "a second-year computer science student",
                    "topic": "third normal form and transitive dependencies",
                },
            },
            {
                "key": "practice-quiz",
                "name": "Revision quiz generator",
                "templates": [
                    "Write a quiz about {{topic}}.",
                    ("Write {{question_count}} questions about {{topic}} for "
                    "{{level}}. Include answers."),
                    ("Create {{question_count}} questions about {{topic}} for "
                    "{{level}}. Mix recall and application. Number each "
                    "question; place answers with explanations in a separate "
                    "section. Use unambiguous wording and avoid duplicate "
                    "questions."),
                ],
                "values": {
                    "level": "undergraduate beginners",
                    "question_count": "3",
                    "topic": "SQL joins, foreign keys and transactions",
                },
            },
        ],
    },
    {
        "description": "Showcase: engineering summaries, rollback readiness and failure "
        "recovery.",
        "key": "demo-release-notes",
        "name": "Demo · Release Notes",
        "prompts": [
            {
                "key": "release-summary",
                "name": "Customer-facing release summary",
                "templates": [
                    "Summarize these changes: {{changes}}.",
                    ("Summarize {{changes}} for {{audience}}. Group features, "
                    "fixes and known limitations."),
                    ("Changes: {{changes}}\n"
                    "Audience: {{audience}}\n"
                    "Write a title, three benefit-focused bullets and a "
                    "known-limitations section. State only facts in the input. "
                    "Do not expose internal credentials, issue IDs or "
                    "implementation details irrelevant to users."),
                ],
                "values": {
                    "audience": "PromptVault demo users",
                    "changes": "Added verified-email registration; fixed duplicate "
                    "prompt version numbers; added project invitations. "
                    "Real provider access depends on account free-tier "
                    "quota.",
                },
            },
            {
                "key": "incident-update",
                "name": "Service incident update",
                "templates": [
                    "Write an incident update for {{incident}}.",
                    ("Write an update for {{incident}} using the current status "
                    "{{status}}. Avoid unsupported recovery promises."),
                    ("Incident: {{incident}}\n"
                    "Confirmed status: {{status}}\n"
                    "Return Impact, Current action and Next update. Separate "
                    "confirmed facts from unknowns. Do not invent an ETA or "
                    "blame a provider without evidence."),
                ],
                "values": {
                    "incident": "Some verification emails are delayed after SMTP "
                    "authentication failed.",
                    "status": "A replacement App Password has been configured and "
                    "SMTP authentication now passes; end-to-end inbox "
                    "delivery still needs confirmation.",
                },
            },
        ],
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-email",
        help="Existing active administrator; defaults to the earliest active admin",
    )
    args = parser.parse_args()
    settings = Settings()
    require_development_seed(environment=settings.environment)
    model = MODELS[0]
    config = {
        "provider": "gemini",
        "model": model.id,
        "temperature": 0,
        "max_output_tokens": 500,
    }
    created = 0
    with psycopg.connect(settings.database_url) as c:
        admin = c.execute(
            "SELECT id FROM users WHERE role='admin' AND is_active AND (%s::text IS NULL OR email=%s) ORDER BY created_at LIMIT 1",
            (args.admin_email, args.admin_email),
        ).fetchone()
        if admin is None:
            raise SystemExit(
                "An existing active Super Admin is required; no accounts were created."
            )
        actor = admin[0]
        c.execute(
            "SELECT set_config('app.user_id',%s,true),set_config('app.request_id','prepare-gemini-demo',true)",
            (str(actor),),
        )
        for project in PROJECTS:
            row = c.execute(
                "SELECT id FROM projects WHERE key=%s", (project["key"],)
            ).fetchone()
            pid = (
                row[0]
                if row
                else c.execute(
                    "INSERT INTO projects(name,key,description,owner_id) VALUES(%s,%s,%s,%s) RETURNING id",
                    (project["name"], project["key"], project["description"], actor),
                ).fetchone()[0]
            )
            for prompt in project["prompts"]:
                row = c.execute(
                    "SELECT id FROM prompts WHERE project_id=%s AND key=%s",
                    (pid, prompt["key"]),
                ).fetchone()
                prompt_id = (
                    row[0]
                    if row
                    else c.execute(
                        "INSERT INTO prompts(project_id,key,name,description) VALUES(%s,%s,%s,%s) RETURNING id",
                        (
                            pid,
                            prompt["key"],
                            prompt["name"],
                            "Gemini prompt version demonstration",
                        ),
                    ).fetchone()[0]
                )
                for number, template in enumerate(prompt["templates"], 1):
                    existing = c.execute(
                        "SELECT 1 FROM version_context WHERE prompt_id=%s AND template_body=%s AND model_config=%s",
                        (prompt_id, template, Jsonb(config)),
                    ).fetchone()
                    if existing:
                        continue
                    parent = c.execute(
                        "SELECT id FROM prompt_versions WHERE prompt_id=%s ORDER BY version_number DESC LIMIT 1",
                        (prompt_id,),
                    ).fetchone()
                    import re

                    variables = list(
                        dict.fromkeys(
                            re.findall(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", template)
                        )
                    )
                    c.execute(
                        "SELECT create_prompt_version(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            prompt_id,
                            parent[0] if parent else None,
                            template,
                            Jsonb(variables),
                            Jsonb(config),
                            f"Gemini demo revision {number}",
                            actor,
                        ),
                    )
                    created += 1
    print(
        f"Gemini showcase metadata ready; {created} versions added. No provider calls, emails or release changes."
    )


if __name__ == "__main__":
    main()
