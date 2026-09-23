# PromptVault backend contract design

**Date:** 2026-09-23

**Owner:** Jobin

**Scope:** Phase 0 contract freeze and the architecture that later backend batches must follow

## Intent

Build the backend and PostgreSQL half of PromptVault independently from the frontend while preserving one explicit shared contract. Success means Ananya can use mock adapters shaped like the API, and Jobin can validate real endpoints through OpenAPI and Pytest without either developer waiting on the other's implementation.

## Constraints

- Do not modify `web/` as part of Jobin's work.
- Preserve the two-role model: stored roles are `user` and `admin`, with `admin` displayed as Super Admin.
- PostgreSQL owns critical integrity and concurrency guarantees.
- The deterministic mock provider is mandatory for automated tests and offline demonstrations.
- Secrets, password hashes, encrypted key material, and token hashes never cross API boundaries.
- Shared-contract changes are recorded in `docs/contract-questions.md`.

## Selected architecture

Use an async FastAPI service with a Psycopg 3 pool. Routers validate HTTP inputs and call services; services own transaction boundaries; repositories contain parameterized SQL; provider adapters isolate external LLM behavior. PostgreSQL procedures own production approval and rollback. Application endpoints are versioned under `/api/v1`, while operational health and the consumer-facing Serve API keep independent paths.

The backend will be delivered foundation-first and then by vertical slice:

1. FastAPI configuration, lifecycle, error model, health/readiness, and tests.
2. Transactional migration runner and normalized PostgreSQL schema.
3. Database invariants, procedures, views, partitions, and grants.
4. Authentication and reusable authorization dependencies.
5. Projects/members and prompts/versions.
6. Providers/runs/pricing/budgets.
7. Deployments/approval/rollback/tokens/Serve.
8. Governance, analytics, verification, and delivery.

## Data and security decisions

Project owners control project metadata and membership. Members may author and execute project prompts. Admin access is explicit and does not weaken project scoping accidentally. Prompt keys are unique per project; a Serve token selects exactly one project. User and project budgets both apply, and all applicable limits must pass.

JWT access tokens are short-lived and validated against the current database user on every protected request. Provider secrets use PostgreSQL `pgcrypto`; Serve token plaintext is returned once and only its SHA-256 hash is stored. Audited writes set `app.user_id` transaction-locally.

## Failure model

All non-2xx responses use the shared error envelope with a request ID. Known validation, authentication, authorization, missing-resource, conflict, budget, provider, and database failures have stable codes. Internal database details are logged only in redacted structured form and are never returned to clients.

## Verification

Each production behavior begins with a failing automated test. Unit tests use isolated helpers; database behavior is proven against PostgreSQL 16; API tests exercise the published contract; concurrency tests demonstrate version numbering, approval, and budget invariants. A fresh environment must migrate, seed, run tests, and complete the demo storyboard.

## Phase 0 completion criteria

- Every v1 feature appears in `requirements-matrix.md` with observable acceptance evidence.
- Every frontend route has an access class and page responsibility.
- Every backend operation has a method/path, request/response contract, and authorization class.
- Ownership, error, pagination, date, money, and token conventions are explicit.
- The demo and primary technical risks are documented.
- No unresolved placeholder or contradictory decision remains in the Phase 0 documents.
