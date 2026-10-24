# Jobin Demo: PromptVault Walkthrough

This guide covers the complete PromptVault workflow using the existing
**Demo · Support Desk** project. It includes prompt versioning, Gemini
execution, staging, production approval, role-based access, production rollback,
and restoration after the rollback demonstration.

The walkthrough uses the local Docker application and the persistent PostgreSQL
database on `localhost:5432`.

## 1. Demo scope

The walkthrough demonstrates how PromptVault provides:

- Project-scoped access to prompts and execution history.
- Immutable, numbered prompt versions.
- Gemini-only prompt execution with saved inputs and model settings.
- Separate development, staging, and production environments.
- Super Admin approval for production deployments.
- Auditable production rollback to an earlier immutable version.
- Preserved deployment history after approval and rollback.

## 2. Demo project

Use the existing project:

**Demo · Support Desk**

The project contains these prompts:

| Prompt | Key | Version 3 variables |
|---|---|---|
| Support ticket triage | `ticket-triage` | `priority_rules`, `ticket` |
| Order support reply | `order-reply` | `customer_message`, `order_id`, `policy` |
| Response quality review | `quality-review` | `draft_response`, `policy`, `tone` |

Each prompt has three immutable versions configured for Gemini
`gemini-3.5-flash-lite`.

Use **Support ticket triage**, version 3, for the main workflow.

At the time this guide was created, `ticket-triage` had no deployments. The
walkthrough creates its staging and production history before demonstrating a
rollback. If its deployment state has already changed, select the current
active production version and an earlier version when demonstrating rollback.

## 3. User and Super Admin responsibilities

PromptVault separates account roles from project ownership.

### Regular project member

A regular member can:

- View assigned projects.
- View and create prompts within assigned projects.
- Create immutable prompt versions.
- Compare versions and inspect version lineage.
- Execute accessible prompt versions in Playground.
- View scoped runs and deployment history.
- Create development and staging deployments.
- Submit production deployment requests.

A regular member cannot:

- Edit project-level settings unless they are the project owner.
- Manage project members unless they are the project owner.
- Approve or reject production requests.
- Perform production rollbacks.
- Manage organization-wide accounts or Gemini credentials.

### Project owner

A project owner has all regular-member capabilities and can also:

- Edit the owned project.
- Invite registered users to the project.
- View pending project invitations.
- Cancel pending invitations.
- Remove project members other than the owner.
- Manage project-scoped API tokens.

The regular user in this walkthrough owns **Demo · Support Desk**.

### Super Admin

A Super Admin can:

- Access all projects.
- Create and delete projects.
- Perform the same prompt and Playground operations as project users.
- Review, approve, or reject production deployment requests.
- Roll back active production deployments.
- Manage user access and roles.
- Manage encrypted Gemini credentials.
- View organization-wide audit information.

The interface displays this role as **Super Admin**. The backend stores it as
`admin`.

### Capability summary

| Capability | Regular member | Project owner | Super Admin |
|---|:---:|:---:|:---:|
| View assigned projects | Yes | Yes | All projects |
| Create prompts and versions | Yes | Yes | Yes |
| Execute prompts | Yes | Yes | Yes |
| Create development/staging deployments | Yes | Yes | Yes |
| Request production deployment | Yes | Yes | Yes |
| Edit project details | No | Yes | Yes |
| Manage project members | No | Yes | Yes |
| Approve or reject production | No | No | Yes |
| Roll back production | No | No | Yes |
| Create or delete projects | No | No | Yes |
| Manage users and Gemini credentials | No | No | Yes |
| View organization audit information | No | No | Yes |

## Copy/paste prompt values and notes

Use the following values throughout the walkthrough.

### Playground prompt inputs

`ticket`:

```text
I was charged twice for invoice INV-4821. The duplicate charge is still
showing after three business days, and I need the funds for an upcoming payment.
Please resolve this today.
```

`priority_rules`:

```text
Use High priority for duplicate charges, payment failures, account lockouts,
or issues with an immediate financial impact. Use Medium for delayed deliveries
and degraded product functionality. Use Low for general questions. Route
billing issues to the Billing team. Do not include personal data that is not
needed for triage.
```

### Notes entered during the deployment workflow

| Form | Field | Text to enter |
|---|---|---|
| Staging deployment | Deployment note | `Validated ticket classification and routing output in Playground` |
| Production request | Deployment note | `Promote the validated support ticket triage rules` |
| Super Admin approval | Review note | `Playground result reviewed. Category, priority, evidence, and team routing are grounded in the submitted ticket and ready for production.` |
| Rollback | Rollback reason | `Production review found that the v3 four-field output is too restrictive for a legacy ticket consumer. Restore the previously validated v2 triage format while the consumer is updated.` |
| Re-promotion request | Deployment note | `Re-promote ticket-triage v3 after validating the updated consumer` |
| Re-promotion approval | Review note | `Legacy consumer validation completed. Restore the structured ticket-triage v3 output in production.` |

The existing version 3 already has a commit message, so creating another prompt
version is not required. If a separate prompt-editing demonstration is needed,
save the edit as a new immutable version with this commit note:

```text
Clarify evidence grounding and Billing team routing for duplicate charges
```

## 4. Start the local application

Double-click the **PromptVault** application in `~/Applications`, or run the
following command from the repository root:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
```

Open:

- Frontend: <http://localhost:5173>
- API readiness: <http://localhost:8000/ready>
- API documentation: <http://localhost:8000/docs>
- Prometheus-compatible metrics: <http://localhost:8000/metrics>

The local application uses:

- React/nginx on port `5173`.
- FastAPI on port `8000`.
- The existing PostgreSQL server on `localhost:5432`.
- Gemini as the only execution provider.
- Configured SMTP for account verification, password reset, and invitations.

## 5. Verify demo readiness

Complete these checks before running the walkthrough:

1. Confirm the frontend and API are healthy.
2. Confirm that the regular user and Super Admin accounts can sign in.
3. Sign in as Super Admin.
4. Open **Administration → Provider keys**.
5. Confirm that an active Gemini key exists without exposing its secret.
6. Run a small Playground request to confirm current Gemini free-tier access.
7. Open **Projects → Demo · Support Desk** and confirm that its three
   prompts and version histories are available.

PromptVault does not use another provider or automatically fall back to a paid
model. A live execution can fail if the external Gemini free-tier quota is
temporarily unavailable.

## 6. Regular-user walkthrough

### 6.1 Sign in

Sign in using the existing regular-user account that owns
**Demo · Support Desk**.

The workspace navigation should be visible without the Super Admin
administration section.

### 6.2 Open the project

Navigate to:

**Projects → Demo · Support Desk**

Verify that the project shows:

- Support ticket triage.
- Order support reply.
- Response quality review.
- Project membership information.
- Project settings available to the project owner.

### 6.3 Open the prompt

Select **Support ticket triage**.

Verify that versions 1, 2, and 3 appear in the version history. Each version is
an immutable snapshot with its own template, variables, Gemini configuration,
commit message, and creation metadata.

### 6.4 Inspect version 3

Open version 3 and review:

- Prompt template.
- Variable declarations.
- Provider: Gemini.
- Model: `gemini-3.5-flash-lite`.
- Temperature.
- Maximum output tokens.
- Commit message.
- Version number and ancestry.

The expected variables are:

```text
priority_rules
ticket
```

### 6.5 Compare versions

Open the version comparison screen and compare version 3 against version 2.

Verify that the comparison identifies additions and removals without changing
either version. Return to version 3 using the back arrow.

### 6.6 Validate version 2 as the rollback target

Open **Playground** and select:

- Project: **Demo · Support Desk**
- Prompt version: `ticket-triage · v2`

Enter the `ticket` and `priority_rules` values from
**Copy/paste prompt values and notes**, then click **Run prompt**.

Verify that the run completes and classifies the issue as a high-priority
billing ticket. This run establishes execution evidence for the version that
will later be used as the rollback target.

### 6.7 Execute version 3 in Playground

Open **Playground** and select:

- Project: **Demo · Support Desk**
- Prompt version: `ticket-triage · v3`

Enter these sample values:

```text
ticket:
I was charged twice for invoice INV-4821. The duplicate charge is still
showing after three business days, and I need the funds for an upcoming payment.
Please resolve this today.

priority_rules:
Use High priority for duplicate charges, payment failures, account lockouts,
or issues with an immediate financial impact. Use Medium for delayed deliveries
and degraded product functionality. Use Low for general questions. Route
billing issues to the Billing team. Do not include personal data that is not
needed for triage.
```

Click **Run prompt**.

After a successful execution, verify:

- Status is Completed.
- A Gemini-generated output appears.
- Prompt token count is recorded.
- Completion token count is recorded.
- Latency is recorded.
- The run has a persistent identifier.
- The output contains exactly Category, Priority, Evidence, and Suggested team.
- The run is connected to `ticket-triage` version 3.

## 7. Staging deployment

Open **Deployments → New deployment**.

Select:

- Prompt version: `ticket-triage · v3`
- Environment: **Staging**

Enter this deployment note:

```text
Validated ticket classification and routing output in Playground
```

Click **Create deployment**.

The staging deployment becomes active without entering the Super Admin approval
queue. If version 3 is already active in staging, open and review the existing
deployment instead of creating an unnecessary duplicate.

## 8. Production deployment request

While signed in as the regular user, open **Deployments → New deployment**.

Select:

- Prompt version: `ticket-triage · v3`
- Environment: **Production**

Enter this deployment note:

```text
Promote the validated support ticket triage rules
```

Click **Request approval**.

Verify that:

- The deployment has Pending approval status.
- Production does not change before approval.
- The regular user can cancel their own pending request.
- The regular user cannot approve or reject the request.

If version 3 is already active in production, use its existing deployment
record when reviewing the approved state. Create a new production request only
when the workflow needs to be demonstrated again.

## 9. Super Admin production approval

### 9.1 Switch accounts

Sign out of the regular-user account and sign in as the existing Super Admin.

Verify that the **Administration** section contains:

- Approvals.
- Rollback.
- Users.
- Provider keys.
- Audit log.

### 9.2 Open the approval queue

Navigate to **Administration → Approvals**.

Select the pending `ticket-triage v3` production request.

### 9.3 Review evidence

Verify the approval screen displays:

- Project and prompt.
- Requested version.
- Immutable candidate template.
- Candidate variables and Gemini model.
- Commit message.
- Recent runs for the exact candidate version.
- Current production version, if one exists.
- Requester and deployment note.

### 9.4 Approve production

Enter a review note:

```text
Playground result reviewed. Category, priority, evidence, and team routing are
grounded in the submitted ticket and ready for production.
```

Click **Approve production** and confirm the action.

Verify that:

- The deployment becomes Active.
- Production points to version 3.
- The reviewer is recorded.
- Review and activation timestamps are recorded.
- The deployment appears in deployment history.
- The action appears in audit history.

### 9.5 Optional rejection path

For a separate pending request, the Super Admin can select **Reject request**.
A rejection reason is required. Rejection does not replace the currently active
production version.

## 10. Production rollback

Rollback requires:

- An active Super Admin account.
- An active production deployment.
- An earlier immutable version of the same prompt.
- A non-empty rollback reason.

Use these values:

- Active deployment: `Demo · Support Desk · ticket-triage · production v3`
- Restore version: `v2 · Demo refinement 2: improve structure, safety, and clarity`

### 10.1 Open the rollback screen

Navigate to **Administration → Rollback**.

Under **Active deployment**, select:

```text
Demo · Support Desk · ticket-triage · production v3
```

Under **Restore version**, select version 2.

### 10.2 Verify deployment impact

Confirm the impact panel shows:

| Field | Expected value |
|---|---|
| Project | Demo · Support Desk |
| Prompt | ticket-triage |
| Environment | Production |
| Current version | v3 |
| Rollback target | v2 |
| History | Preserved |

### 10.3 Enter a rollback reason

Enter:

```text
Production review found that the v3 four-field output is too restrictive for a
legacy ticket consumer. Restore the previously validated v2 triage format while
the consumer is updated.
```

Click **Review rollback**.

### 10.4 Confirm rollback

Verify that the confirmation identifies:

- Prompt: `ticket-triage`.
- Current production version: v3.
- Restore version: v2.
- Creation of a new deployment record.

Confirm the rollback.

### 10.5 Verify the rollback result

PromptVault performs the following changes atomically:

1. The former active production v3 deployment becomes **Rolled back**.
2. A new production deployment targeting version 2 becomes **Active**.
3. The new deployment is linked to the deployment it replaced.
4. The rollback reason is preserved.
5. The Super Admin is recorded as requester and reviewer.
6. Review and activation timestamps are recorded.
7. Staging remains on version 3.
8. Prompt versions 2 and 3 remain unchanged.

Open **Deployments** and filter by:

- Project: **Demo · Support Desk**
- Environment: **Production**

Open the new version 2 deployment and verify:

- Active status.
- Rollback reason.
- Link to the replaced deployment.
- Deployment timeline.
- Super Admin actor information.

Open the former version 3 deployment and verify its **Rolled back** status.

## 11. Restore production to version 3

Rollback moves production to an earlier version. Returning from version 2 to
version 3 requires a new production deployment request and approval; it is not
performed through the rollback screen.

### 11.1 Submit a new request as the regular user

1. Sign out of the Super Admin account.
2. Sign in as the regular user.
3. Open **Deployments → New deployment**.
4. Select `ticket-triage · v3`.
5. Select **Production**.
6. Enter:

```text
Re-promote ticket-triage v3 after validating the updated consumer
```

7. Click **Request approval**.

### 11.2 Approve as Super Admin

1. Sign out of the regular-user account.
2. Sign in as Super Admin.
3. Open **Administration → Approvals**.
4. Select the new version 3 request.
5. Review its version and run evidence.
6. Enter a review note.
7. Click **Approve production** and confirm.

Production points to version 3 again. The original approval, rollback to version
2, and re-promotion to version 3 remain visible as separate immutable deployment
records.

The resulting lifecycle is:

```text
v3 tested
  → regular user requests production
  → Super Admin approves v3
  → Super Admin rolls production back to v2
  → regular user submits v3 again
  → Super Admin approves v3 again
```

## 12. Additional features

### Project invitations

The project owner can invite an existing registered account from the project
Members section. PromptVault sends a one-use email invitation. The recipient
must sign in using the invited account and accept the invitation before project
access is granted.

### API tokens

An authorized project owner can create a project-scoped Serve token. The
plaintext token is displayed only once. An external local application can use
the token to fetch the active prompt for a selected environment without using a
person's login session.

### Audit log

The Super Admin can open **Administration → Audit log** to inspect governance
and security actions. Secret values are redacted.

### Provider keys

The Super Admin can manage Gemini credentials under
**Administration → Provider keys**. Provider secrets are encrypted in
PostgreSQL and are never returned in plaintext after creation.

### Operational metrics

The API exposes Prometheus-compatible process metrics at
<http://localhost:8000/metrics>. The local launcher exposes the endpoint but
does not start a separate Prometheus interface.

## 13. Troubleshooting

### Model provider is unavailable

Rebuild and recreate the local containers with the local override:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
```

Confirm that an active Gemini key appears under
**Administration → Provider keys**. Do not configure another provider or an
automatic paid fallback.

### Gemini free-tier quota reached

Wait for the Gemini account quota to recover and retry. PromptVault does not
switch to a paid model.

### Production request does not appear

Confirm that:

- Production was selected as the environment.
- The request completed successfully.
- The request has not already been approved, rejected, or cancelled.
- The current account is a Super Admin.

### Rollback target is unavailable

Confirm that:

- The prompt has an active production deployment.
- The selected target belongs to the same prompt.
- The target version number is lower than the active version number.
- A rollback reason has been entered.
- The current account is an active Super Admin.

An active version 1 deployment cannot be rolled back because it has no earlier
version.

## 14. Completion checklist

- [ ] Local frontend and API are healthy.
- [ ] Regular user opens Demo · Support Desk.
- [ ] Version 3 is inspected and compared with version 2.
- [ ] Version 2 is executed to establish rollback-target evidence.
- [ ] Version 3 is executed successfully through Gemini.
- [ ] Staging deployment is shown.
- [ ] Regular user submits a production request.
- [ ] Super Admin reviews and approves the request.
- [ ] Production version 3 becomes active.
- [ ] Super Admin rolls production back to version 2.
- [ ] Version 3 is marked Rolled back and version 2 becomes active.
- [ ] Regular user submits version 3 again.
- [ ] Super Admin approves version 3 again.
- [ ] Final deployment and audit history are reviewed.

