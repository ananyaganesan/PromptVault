# PromptVault: complete demo walkthrough

Allow **25–30 minutes** for the full tour. Spend **5–7 minutes** on **Find the best version**.

## Local setup and checks

Use the existing PostgreSQL server on `localhost:5432` and the persistent
`promptvault` database configured in the root `.env`. Keep `.env` private.

For an existing checkout with dependencies installed, start from the repository root:

```sh
.venv/bin/python scripts/start-local.py
```

The app opens at <http://localhost:5173>, the API at <http://localhost:8000/docs>,
and local Prometheus at <http://localhost:9090>. Install Prometheus with Homebrew
before the first start; see [local monitoring](local-monitoring.md) for setup and
queries. Startup checks migration checksums and preserves existing accounts and data.
Use `.venv/bin/python scripts/start-local.py --check` to check the database connection.

For a fresh checkout, create a Python 3.11+ virtual environment, install
`api/requirements-dev.lock`, run `npm ci` in `web`, and copy `.env.example` to `.env`.
Configure the local database, a private secret, SMTP, and free-access Gemini credentials.
Run `scripts/run-migrations.py` with the virtual-environment Python. Optional demo seeds
are available through `scripts/seed-database.py`; do not seed over existing accounts.
Use `scripts/configure-smtp.py` for interactive email setup and
`scripts/backup-local.py` for a private database backup with an isolated restore check.

Run `.venv/bin/python -m pytest -q` for backend checks. Database tests require
`TEST_DATABASE_URL` pointing to a separate database ending in `_test`; never point it
at `promptvault`. Email acceptance uses loopback SMTP through
`scripts/run-local-auth-acceptance.py`. In `web`, run `npm test`, `npm run typecheck`,
`npm run lint`, and `npm run build` for frontend checks.

## Before starting

- Open [PromptVault](http://localhost:5173).
- Use separate browser windows for **User/project owner**, **Admin**, and **Super Admin**.
- Use the existing **CampusCart Support Demo** project and **Customer Support Reply** prompt.
- Keep [sample inputs and references](../examples/prompt-evaluation/cases.json) open.
- Have a working free-access Gemini key and an inbox you control for email demonstrations.
- Start with empty deployments. The existing prompt versions do not need to be recreated.
- Use a temporary account/project for account closure, access removal, or project deletion.
- Keep passwords, API keys, and tokens off-screen.

**Opening line:** “PromptVault helps us create, test, compare, approve, and safely release better prompts.”

## 1. Registration, verification, and account approval

1. Register a temporary account using an email address you control.
2. Show the verification email. Use **Resend verification email** if needed.
3. Open the verification link. It is single-use and expires after 30 minutes.
4. Try signing in before approval: access is blocked.
5. As Admin, open **Users/User approvals**, find the account, and choose **Approve user**.
6. Sign in with the approved account.

**Say:** “New accounts need both email verification and administrator approval.”

## 2. Login, password reset, profile, and logout

1. Show **Forgot password** using the temporary account.
2. Open its reset email and set a new password.
3. Sign in again and open **Profile**.
4. Edit **Display name**, save, and show the account role.
5. Use **Sign out**, then sign in as the project owner.

**Say:** “Passwords and sessions are managed separately from project access.”

## 3. Dashboards and navigation

1. As User, show project/prompt counts and recent personal runs on **Dashboard**.
2. As Admin, show **Admin dashboard**: user approvals, deployment approvals, and active/inactive user counts.
3. Point out the Admin links: **Users**, **Approvals**, and **Rollback**.
4. As Super Admin, show the additional system-management links.
5. Collapse/expand the sidebar. Use the mobile menu if demonstrating on a small screen.

**Say:** “Each role gets the controls relevant to its responsibilities.”

## 4. Projects, ownership, and membership

1. Open **Projects**. Try project search and the ownership filter.
2. Open **CampusCart Support Demo** and show **Overview**, **Prompts**, **Members**, and **Settings**.
3. Show the owner and the existing members. Project ownership is separate from account role.
4. As owner, invite the temporary approved account by email.
5. As the recipient, open the invitation and choose **Accept invitation**.
6. Show that access appears only after acceptance.
7. Show **Cancel invitation** for a pending invitation and **Remove** for a temporary member.
8. In **Settings**, edit the project description and save it.

As Super Admin, open **New project** to show creation. If creating a temporary project, delete it in step 18; keep CampusCart for the main demo.

## 5. Prompt creation and the prompt library

1. Open the project's **Prompts** tab. Show prompt search.
2. Open **New prompt** and show the key, name, description, template, model settings, and commit message.
3. Explain that `{{customer_message}}` and `{{store_policy}}` are template variables.
4. Create a practice prompt if you want to demonstrate creation; otherwise return to the existing **Customer Support Reply**.
5. Show the prompt library's search, project filter, and environment filter.

**Say:** “A prompt has a stable identity; its content and model settings live in versioned snapshots.”

## 6. Immutable versions, comparison, and lineage

Open **Customer Support Reply** and show:

| Version | Purpose |
|---|---|
| v1 | General support instructions |
| v2 | Policy safeguards, empathy, and useful next steps |
| v3 | Experimental response requesting at least 180 words |

1. Open v2 and choose **Compare versions**. Compare it with v1.
2. Show template, variable, and model-configuration differences.
3. Open **View lineage/Full lineage** and show the parent relationships.
4. Explain that editing the prompt and adding a commit message creates a **new version**.
5. Save an edited draft only if you want an additional version; use v1 and v2 for the prepared comparison.

**Say:** “Saving a new version preserves earlier versions. The latest draft is not automatically active.”

## 7. Playground: execute a saved version

1. Open **Playground**. It starts with **Select a project**.
2. Select **CampusCart Support Demo**, then **Customer Support Reply · v2**.
3. Show the saved Gemini model, temperature, and output-token limit.
4. Copy the first case's `customer_message` and `store_policy` from [cases.json](../examples/prompt-evaluation/cases.json).
5. Leave a required input empty once to show validation, then fill it.
6. Click **Run prompt**. Show the answer, token counts, and latency.
7. Change temperature or the output limit. Show that **Save configuration** creates a new immutable version before that configuration can run.
8. Show **Refresh providers**. Compatible prompts may also offer **Load demo inputs**; CampusCart's inputs are supplied in `cases.json`.

**Say:** “Execution uses saved settings and the project's configured free-access Gemini access.”

## 8. Find the best version: define success

Return to **Customer Support Reply → Find the best version**.

1. Select **v1 and v2**.
2. Choose the **Customer support** preset. Show the other presets: accurate answers, summarization, and organized information.
3. Review or enter this goal:

> Give an empathetic, accurate answer using only the store policy. Answer the refund-timing question directly and provide a useful next step in at most 100 words.

4. Add the first case from `cases.json`, including its reference. The saved setup may already contain it.
5. Explain the scenario: an unused item arrived three days ago, and the customer asks for a refund today.
6. Explain the reference: returns are allowed within seven days, but refunds take five business days **after inspection**.

**Say:** “Best means best for our requirements and examples, not best for every possible situation.”

## 9. Find the best version: cases, requirements, and weights

1. Show **Suggest scenarios**. Review suggestions before choosing **Use suggested scenarios and preferences**.
2. Show **Use inputs from past runs** to reuse real run inputs. Add a trusted reference again if needed; previous outputs are not automatically treated as correct answers.
3. Show how to add, edit, and remove cases. Keep one case for the first live comparison.
4. Set **Answer length limit = 100**.
5. Explain that format checks follow the selected task and saved preferences automatically; users do not configure JSON fields.
6. Open **Advanced** and review these weights:

| Metric | Weight | Question |
|---|---:|---|
| Correctness | 25% | Does the answer agree with the reference? |
| Relevance | 25% | Does it answer the customer's question? |
| Instruction following | 20% | Does it follow the task and constraints? |
| Completeness | 15% | Does it include essential information and next steps? |
| Clarity | 15% | Is it understandable and well organized? |

7. Show that weights must total **100**. Click **Save setup**.

A comparison supports 2–5 versions, up to 5 cases, and at most 15 version/case combinations.

**Say:** “Mandatory requirements are pass/fail. Gemini assesses quality. Without a reference, correctness is unverified and its weight is redistributed.”

## 10. Find the best version: evaluate and explain the result

1. Click **Compare versions** once. Show progress.
2. Explain that both versions receive the same scenario inputs.
3. Explain that the judge sees anonymous candidates without version numbers.
4. Show each answer and its mandatory-check results.
5. Expand a metric to show its **0–5 score**, explanation, and exact quotation from the answer.
6. Explain that weighted quality scores become percentages; multiple case scores are averaged. When a trusted answer is supplied, Gemini Embedding 2 creates 768-dimensional vectors for the output and reference. The final answer score is 80% quality plus 20% cosine similarity (negative similarity contributes zero). Show the similarity and combined score below each answer. Examples without a trusted answer use quality only; similarity is not a factual accuracy check.
7. Show the recommendation, or explain **No clear winner** if the leading eligible scores are within three points.
8. Explain that incomplete or invalid assessments prevent a recommendation.
9. Open **Evaluation history** and show the saved goal, settings, results, and usage. Show **Use these preferences again**.

**Say:** “The score summarizes the comparison. The evidence helps us judge whether the recommendation is convincing.”

Optional: include v3. Its instructions request at least 180 words, but the evaluation requires at most 100. Check the actual output: a mandatory failure makes a version ineligible even if it has strong quality scores.

One case across two versions uses two generation calls and up to two judge calls. A trusted reference adds one reference embedding call (reused across versions) and one embedding call per generated answer. Vectors and similarity are saved with the result, and embedding requests are recorded in the evaluation call ledger. Failed embedding requests leave the answer unscored and prevent a recommendation. Existing historical evaluations keep their original scores. Do not promise a particular winner or run extra cases just to obtain a preferred result.

## 11. Generate and save an improvement

1. From a completed evaluation, select a version and click **Suggest an improvement**.
2. Read the explanation and edit the suggested template.
3. Add a commit message and choose **Save as a new version**.
4. Show the new version in history.

**Say:** “An improvement is an editable draft. It must be evaluated again, and saving it does not activate it.”

## 12. Development and staging releases

1. As a project member, open **Deployments → New deployment**.
2. Choose v1 and **Development**. Reuse the saved evaluation cases or enter release cases here.
3. Click **Validate release**. Open the report to show compatibility checks, outputs, required checks, and metric evidence. Every case needs at least 70/100.
4. If validation fails, choose **Suggest a fix**, review the proposed template, and click **Save fix and validate**. This creates a new immutable version and reruns the cases.
5. When the report passes, click **Create deployment**.
6. Repeat for **Staging**.
7. Show the active environment badges and deployment details.
8. Use the deployment project, environment, status, and page controls to inspect release records.

**Say:** “Development, staging, and production are prompt-release slots in this local application.”

## 13. Production approval, rejection, and cancellation

1. Select **Production**, validate the candidate, add a note, and click **Request approval**.
2. As Admin, open **Approvals**. Inspect the version, current active version, release validation report, and run evidence. Approval is disabled until validation passes. Add a review note and approve.
3. Validate and request Production deployment of the next version and approve it the same way. That version becomes active.
4. Submit another experimental request and demonstrate **Reject request** with a reason.
5. Submit a separate request and, as its requester, use **Cancel request** before review.
6. Show the resulting statuses and timeline. If the active release or saved test suite changes while a request is pending, show **Revalidate this request** in its details. The requester can attach fresh evidence without creating another request.

**Say:** “The evaluator recommends. An admin explicitly authorizes activation.”

## 14. API tokens and the Serve API

1. As project owner, open **API tokens → Issue token**.
2. Select CampusCart, enter a name, and choose an expiration.
3. Copy the token privately; its full value is shown only once.
4. In an API client, send this request using the token as a Bearer credential:

```http
GET http://localhost:8000/serve/v1/prompts/customer-support-reply?env=prod
Authorization: Bearer <SERVE_TOKEN>
```

5. Show the active version, template, variables, and model settings returned to the consuming application.
6. Optionally repeat with the returned ETag in `If-None-Match` to demonstrate a **304 Not Modified** response.

**Say:** “Another application can retrieve the approved prompt using a project-scoped token.”

## 15. Rollback and preserved history

1. As Admin, open **Rollback** and select the active v2 Production deployment.
2. Choose v1 and enter: “Restore the previous stable response while reviewing the new version.”
3. Click **Review rollback**, inspect the impact, and confirm.
4. Show the restored version and the new rollback record, reason, and previous release history.
5. Repeat the Serve request: it now returns v1.
6. Revoke the temporary API token and repeat the request to show that access is blocked.

**Say:** “Admins can restore a previous version without erasing the release history.”

## 16. Admin account management

1. Open **Users/User approvals** and demonstrate search, role/status filters, and pagination.
2. Approve the temporary verified user if not already approved.
3. Deactivate that temporary user and show that access stops. Reactivate it afterward.
4. As Super Admin, show **Make admin**, **Make user**, and **Make Super Admin**.
5. If demonstrating a role change, use a temporary account and restore its role afterward.

**Say:** “Admins manage regular users. Only Super Admins assign roles or manage administrator accounts. Role/access changes revoke existing sessions, and the last active approved Super Admin is protected.”

## 17. Super Admin software and database controls

1. Open **Provider keys**. Show encrypted-key metadata, **Add provider key**, and **Deactivate** controls. Keep the working Gemini key unchanged during the demo.
2. Open **Audit log**. Filter events and show who changed a resource and when.
3. Open **Database maintenance**. Show readiness, run partitions, and analytics-view refresh status. Use **Refresh materialized views** if needed.
4. Explain that Super Admin inherits all Admin operations.

Direct PostgreSQL/pgAdmin access uses separate database credentials. The application does not expose a SQL console.

## 18. Project deletion

As Super Admin, open a **temporary project's Settings → Delete project**. Review the confirmation and delete it only if it was created for this demonstration.

Explain that project deletion removes its associated project data. Keep CampusCart for the rest of the presentation.

## 19. API-only features and operational checks

Open [Swagger](http://localhost:8000/docs). Use `POST /api/v1/auth/login` with a demo account, then use its access token in **Authorize**. Keep the token private.

These features do not have dedicated pages in the current navigation:

| Feature | Where to show it | Simple demonstration |
|---|---|---|
| Run history and filters | `GET /api/v1/runs`, `GET /api/v1/runs/{run_id}` | Filter by prompt, version, status, model, or date; inspect output and usage. |
| Version-list controls | `GET /api/v1/prompts/{prompt_id}/versions` | Show version sorting, direction, and pagination. |
| Personal analytics | `GET /api/v1/dashboard/me` | Select a month and show counts, usage, and recent runs. |
| Organization analytics | `GET /api/v1/admin/dashboard` | As Super Admin, show organization totals, model spend, trends, and top spenders. |
| Organization run inspection | `GET /api/v1/admin/runs` | As Super Admin, search and filter runs across projects/users. |
| Spend limits | `/api/v1/admin/budgets` | As Super Admin, show user/project monthly limits and create, update, or delete a temporary limit. Free-access Gemini runs record zero cost. |
| Model-pricing history | `/api/v1/admin/model-pricing` | As Super Admin, inspect effective-date history. Use only zero-price Gemini configuration for this project. |
| Prompt metadata editing | `PATCH /api/v1/prompts/{prompt_id}` | Show name/description updates separately from immutable version content. |
| Account export | `GET /api/v1/auth/account/export` | Export the signed-in account's records. |
| Account closure | `DELETE /api/v1/auth/account` | Show the password-confirmed request; execute only for a disposable demo account. |
| Next run partition | `POST /api/v1/admin/maintenance/create-next-partition` | As Super Admin, show the maintenance operation and its result. |
| Idempotent execution | `POST /api/v1/runs` with `Idempotency-Key` | Repeat an identical request with the same key; show that it reuses the recorded execution. |
| Health and readiness | [Health](http://localhost:8000/health), [Ready](http://localhost:8000/ready) | Show that the API and database connection are available. |
| Operational metrics | [Metrics](http://localhost:8000/metrics) | Show local request counts and timing metrics. |

Swagger documents the full request bodies, filters, and responses. User/account access rules still apply to API calls.

## 20. Show validation and access boundaries

- A missing required Playground input blocks execution.
- Invalid evaluation weights block comparison.
- Users cannot open Admin controls; Admins cannot use database/software-management controls.
- Pending invitations do not grant project access.
- Expired/revoked tokens do not grant runtime access.
- Gemini quota/timeouts and invalid judge responses appear as failures, not invented answers or scores.
- Paid model configuration and removed providers cannot be used as fallbacks.
- Reload a saved prompt, evaluation, or release to show persistence.
- Use sign-out to demonstrate session revocation.

## Closing line

“PromptVault covers the full prompt lifecycle: create, version, test, evaluate, improve, approve, serve, monitor, and roll back.”

For a shorter presentation, prioritize steps **6–11** and **13–15**. Use a single evaluation case to reduce waiting and free-access quota usage.
