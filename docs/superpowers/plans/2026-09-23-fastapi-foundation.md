# FastAPI Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a tested FastAPI foundation with validated settings, an async Psycopg pool lifecycle, request IDs, safe structured errors, CORS, liveness, database readiness, and reproducible test/lint commands.

**Architecture:** `create_app()` is an application factory so tests can inject settings and a fake pool without a running database. FastAPI lifespan owns one `AsyncConnectionPool`; routers obtain it from `app.state`. Request-ID middleware runs outside exception handling so every response, including failures, carries one correlation ID.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings v2, Psycopg 3 async pool, Uvicorn, Pytest, HTTPX/TestClient, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-23-backend-contract-design.md`

## Global Constraints

- Do not modify any file under `web/`.
- Application endpoints use `/api/v1`; liveness/readiness use `/health` and `/ready`; Serve remains `/serve/v1`.
- Errors use `code`, `message`, nullable `field_errors`, and `request_id`.
- Every response returns `X-Request-ID`; accepted client IDs are 1-128 visible ASCII characters.
- Secrets, SQL details, stack traces, and database constraint names never enter responses.
- Settings use environment variables; production rejects missing/placeholder secrets.
- New behavior follows red-green-refactor and each task ends with the full API suite passing.

## Review Focus

1. A malformed or oversized `X-Request-ID` must be replaced, not reflected into response headers or logs; Task 3 tests it.
2. A database outage must make `/ready` return a safe 503 while `/health` remains 200; Task 4 tests both in the same app instance.
3. Pydantic validation errors must retain useful field paths without exposing request values; Task 3 tests nested field formatting and absence of raw input.
4. Pool startup failure must abort application startup and never report readiness; Task 2 tests lifespan propagation and cleanup.
5. An unapproved browser origin must not receive an access-control allow-origin header; Task 4 tests allowed and denied origins.

---

## File map

| File | Responsibility |
|---|---|
| `api/requirements.txt` | Runtime dependency constraints |
| `api/requirements-dev.txt` | Test and lint dependency constraints |
| `api/pyproject.toml` | Package, Pytest, and Ruff configuration |
| `.env.example` | Safe documented configuration names |
| `api/app/config.py` | Validated environment settings and cached loader |
| `api/app/db/pool.py` | Psycopg async pool construction and request dependency |
| `api/app/db/health.py` | One bounded database readiness query |
| `api/app/dependencies/request_context.py` | Request-ID creation, validation, lookup, and middleware |
| `api/app/errors.py` | Error schemas, application exception, and handlers |
| `api/app/routers/health.py` | Liveness and readiness routes |
| `api/app/main.py` | Application factory, lifespan, middleware, handlers, and routers |
| `api/tests/unit/test_config.py` | Settings validation tests |
| `api/tests/unit/test_pool.py` | Pool construction and lifecycle tests |
| `api/tests/unit/test_errors.py` | Error-envelope and request-ID tests |
| `api/tests/integration/test_health.py` | App, CORS, liveness, and readiness tests |
| `api/tests/conftest.py` | Reusable settings, fake pool, and app fixtures |

### Task 1: Reproducible Python tooling and validated settings

**Files:**
- Modify: `api/requirements.txt`
- Create: `api/requirements-dev.txt`
- Modify: `api/pyproject.toml`
- Modify: `.env.example`
- Modify: `api/app/config.py`
- Create: `api/tests/unit/test_config.py`

**Interfaces:**
- Consumes: Environment variables documented in `.env.example`.
- Produces: `Settings`, `get_settings() -> Settings`, and `clear_settings_cache() -> None` from `api.app.config`.

- [ ] **Step 1: Declare and install the foundation dependencies**

Use these dependency bounds:

```text
# api/requirements.txt
fastapi>=0.115,<1
pydantic-settings>=2.6,<3
psycopg[binary,pool]>=3.2,<4
uvicorn[standard]>=0.30,<1
```

```text
# api/requirements-dev.txt
-r requirements.txt
httpx>=0.27,<1
pytest>=8,<9
pytest-asyncio>=0.24,<2
ruff>=0.8,<1
```

Configure `api/pyproject.toml` with Python `>=3.11`, Pytest `asyncio_mode = "auto"`, test path `tests`, and Ruff line length 100 with Python 3.11 target. Run:

```bash
python3 -m pip install -r api/requirements-dev.txt
```

Expected: dependencies install successfully.

- [ ] **Step 2: Write failing settings tests**

```python
# api/tests/unit/test_config.py
import pytest
from pydantic import ValidationError

from api.app.config import Settings


BASE = {
    "database_url": "postgresql://promptvault:promptvault@localhost:5432/promptvault",
    "secret_key": "test-secret-that-is-long-enough",
}


def test_settings_parse_comma_separated_cors_origins() -> None:
    settings = Settings(**BASE, cors_origins="http://localhost:5173, https://app.example.com")
    assert settings.cors_origins == (
        "http://localhost:5173",
        "https://app.example.com",
    )


def test_settings_reject_invalid_pool_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(**BASE, db_pool_min_size=10, db_pool_max_size=2)


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "environment": "production", "secret_key": "change-me"})
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```bash
pytest -q api/tests/unit/test_config.py
```

Expected: FAIL because `Settings` is not implemented.

- [ ] **Step 4: Implement minimal validated settings**

Implement `Settings(BaseSettings)` with:

```python
environment: Literal["development", "test", "production"] = "development"
database_url: str
secret_key: str
cors_origins: tuple[str, ...] = ("http://localhost:5173",)
db_pool_min_size: int = 1
db_pool_max_size: int = 10
db_pool_timeout_seconds: float = 5.0
database_health_timeout_seconds: float = 2.0
```

Use `SettingsConfigDict(env_file=".env", extra="ignore")`, a `field_validator` to split comma-separated origins, and a `model_validator` to require `0 <= min <= max`, positive timeouts, and a non-placeholder production secret of at least 32 characters. Cache `get_settings()` with `functools.lru_cache`; `clear_settings_cache()` calls `get_settings.cache_clear()`.

Update `.env.example` to include `ENVIRONMENT`, `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`, pool bounds, and health timeout. Keep `VITE_API_URL` unchanged for frontend compatibility.

- [ ] **Step 5: Run focused and full tests**

```bash
pytest -q api/tests/unit/test_config.py
pytest -q api/tests
ruff check api
```

Expected: all pass with no warnings or lint errors.

- [ ] **Step 6: Commit Task 1**

```bash
git add .env.example api/requirements.txt api/requirements-dev.txt api/pyproject.toml api/app/config.py api/tests/unit/test_config.py
git commit -m "build: configure FastAPI foundation tooling"
```

### Task 2: Async database pool and lifespan ownership

**Files:**
- Modify: `api/app/db/pool.py`
- Modify: `api/app/main.py`
- Modify: `api/tests/conftest.py`
- Create: `api/tests/unit/test_pool.py`

**Interfaces:**
- Consumes: `Settings` from Task 1.
- Produces: `PoolProtocol`, `PoolFactory`, `create_pool(settings)`, `get_pool(request)`, and `create_app(settings=None, pool_factory=create_pool)`.

- [ ] **Step 1: Write failing pool-construction and lifespan tests**

```python
# api/tests/unit/test_pool.py
import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app


class FakePool:
    def __init__(self, fail_open: bool = False) -> None:
        self.fail_open = fail_open
        self.opened = False
        self.closed = False

    async def open(self, *, wait: bool = True) -> None:
        if self.fail_open:
            raise ConnectionError("database unavailable")
        self.opened = True

    async def close(self) -> None:
        self.closed = True


def test_lifespan_opens_and_closes_one_pool(test_settings: Settings) -> None:
    pool = FakePool()
    app = create_app(test_settings, pool_factory=lambda _: pool)
    with TestClient(app):
        assert pool.opened is True
        assert app.state.db_pool is pool
    assert pool.closed is True


def test_pool_open_failure_aborts_startup(test_settings: Settings) -> None:
    pool = FakePool(fail_open=True)
    app = create_app(test_settings, pool_factory=lambda _: pool)
    with pytest.raises(ConnectionError, match="database unavailable"):
        with TestClient(app):
            pass
    assert pool.closed is False
```

At the top of `api/tests/conftest.py`, set test-safe `DATABASE_URL` and `SECRET_KEY` defaults before importing `api.app.main`; this permits its fail-fast module-level `app` to be constructed during test collection. Add a `test_settings` fixture that creates `Settings(environment="test", database_url=..., secret_key=..., _env_file=None)` so tests never read a developer `.env` file.

- [ ] **Step 2: Run the tests and verify RED**

```bash
pytest -q api/tests/unit/test_pool.py
```

Expected: FAIL because `create_app` does not accept a pool factory and no pool protocol exists.

- [ ] **Step 3: Implement the pool boundary and lifespan**

In `db/pool.py`, define a typing protocol covering `open`, `close`, and `connection`, plus:

```python
PoolFactory = Callable[[Settings], PoolProtocol]


def create_pool(settings: Settings) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_pool_timeout_seconds,
        open=False,
        kwargs={"autocommit": False},
    )


def get_pool(request: Request) -> PoolProtocol:
    return request.app.state.db_pool
```

In `main.py`, create an application factory. Its `asynccontextmanager` lifespan constructs the pool, calls `await pool.open(wait=True)`, stores it at `app.state.db_pool`, yields, and closes it in `finally` only after a successful open. Keep module-level `app = create_app()` for Uvicorn.

- [ ] **Step 4: Run focused and full tests**

```bash
pytest -q api/tests/unit/test_pool.py
pytest -q api/tests
ruff check api
```

Expected: all pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add api/app/db/pool.py api/app/main.py api/tests/conftest.py api/tests/unit/test_pool.py
git commit -m "feat: manage asynchronous database pool lifecycle"
```

### Task 3: Request IDs and safe error envelopes

**Files:**
- Modify: `api/app/dependencies/request_context.py`
- Modify: `api/app/errors.py`
- Modify: `api/app/main.py`
- Create: `api/tests/unit/test_errors.py`

**Interfaces:**
- Consumes: `create_app()` from Task 2.
- Produces: `RequestIdMiddleware`, `get_request_id(request) -> str`, `ErrorEnvelope`, `AppError`, and `install_exception_handlers(app) -> None`.

- [ ] **Step 1: Write failing request-ID tests**

Create a test-only route on the app that returns its request ID, then verify generated, accepted, and rejected IDs:

```python
def test_generated_request_id_is_shared_by_header_and_context(app_client) -> None:
    response = app_client.get("/__test__/request-id")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_valid_client_request_id_is_preserved(app_client) -> None:
    response = app_client.get("/__test__/request-id", headers={"X-Request-ID": "client-123"})
    assert response.headers["X-Request-ID"] == "client-123"


@pytest.mark.parametrize("bad_id", ["", "x" * 129, "contains space"])
def test_invalid_request_id_is_replaced(app_client, bad_id: str) -> None:
    response = app_client.get("/__test__/request-id", headers={"X-Request-ID": bad_id})
    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.headers["X-Request-ID"] != bad_id
```

- [ ] **Step 2: Write failing error-envelope tests**

Add test-only routes that raise `AppError`, trigger request validation, and raise `RuntimeError`. Assert exact bodies, status codes, matching request IDs, nullable `field_errors`, and that validation input values and exception text do not appear in responses.

```python
def test_app_error_uses_contract_envelope(app_client) -> None:
    response = app_client.get("/__test__/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "code": "conflict",
        "message": "Resource already changed",
        "field_errors": None,
        "request_id": response.headers["X-Request-ID"],
    }


def test_unhandled_exception_is_redacted(app_client_no_raise) -> None:
    response = app_client_no_raise.get("/__test__/explode")
    assert response.status_code == 500
    assert response.json()["message"] == "An unexpected error occurred"
    assert "database-password" not in response.text
```

- [ ] **Step 3: Run tests and verify RED**

```bash
pytest -q api/tests/unit/test_errors.py
```

Expected: FAIL because middleware and handlers are absent.

- [ ] **Step 4: Implement request context**

`RequestIdMiddleware` validates `X-Request-ID` with `^[\x21-\x7E]{1,128}$`, otherwise creates `req_` plus `uuid4().hex`. Store it at `request.state.request_id`, call the downstream app, and set the response header. `get_request_id()` returns state or creates a safe fallback.

- [ ] **Step 5: Implement error schema and handlers**

Define:

```python
class ErrorEnvelope(BaseModel):
    code: str
    message: str
    field_errors: dict[str, list[str]] | None = None
    request_id: str


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None: ...
```

Install handlers for `AppError`, `RequestValidationError`, Starlette `HTTPException`, and `Exception`. Convert validation locations to dot-separated field names, omit raw `input` and context values, map unknown HTTP errors to safe standard messages, and return JSON through one `_error_response()` helper.

Middleware order must ensure exception responses receive `X-Request-ID`. Add `RequestIdMiddleware` after installing CORS in source so it executes outermost in Starlette's reverse middleware stack.

- [ ] **Step 6: Run focused and full tests**

```bash
pytest -q api/tests/unit/test_errors.py
pytest -q api/tests
ruff check api
```

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add api/app/dependencies/request_context.py api/app/errors.py api/app/main.py api/tests/unit/test_errors.py api/tests/conftest.py
git commit -m "feat: add request IDs and safe API errors"
```

### Task 4: Liveness, database readiness, CORS, and OpenAPI assembly

**Files:**
- Modify: `api/app/db/health.py`
- Create: `api/app/routers/health.py`
- Modify: `api/app/main.py`
- Create: `api/tests/integration/test_health.py`
- Modify: `api/tests/conftest.py`

**Interfaces:**
- Consumes: `PoolProtocol`, `get_pool`, `Settings`, request context, and error handlers.
- Produces: `check_database(pool, timeout_seconds) -> None`, public `/health`, public `/ready`, configured CORS, and OpenAPI metadata.

- [ ] **Step 1: Write failing health/readiness tests**

Build fake async connection/cursor context managers whose `execute("SELECT 1")` either succeeds or raises. Tests must prove:

```python
def test_health_does_not_query_database(app_client, fake_pool) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_pool.connection_count == 0


def test_ready_queries_database(app_client, fake_pool) -> None:
    response = app_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert fake_pool.executed == ["SELECT 1"]


def test_database_outage_only_breaks_readiness(unready_client) -> None:
    ready = unready_client.get("/ready")
    live = unready_client.get("/health")
    assert ready.status_code == 503
    assert ready.json()["code"] == "not_ready"
    assert "connection refused" not in ready.text
    assert live.status_code == 200
```

Also test that a connection taking longer than `database_health_timeout_seconds` returns 503.

- [ ] **Step 2: Write failing CORS and OpenAPI tests**

```python
def test_configured_origin_receives_cors_header(app_client) -> None:
    response = app_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_is_not_allowed(app_client) -> None:
    response = app_client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_openapi_describes_operational_routes(app_client) -> None:
    document = app_client.get("/openapi.json").json()
    paths = document["paths"]
    assert "/health" in paths
    assert "/ready" in paths
    serialized = str(document).lower()
    for forbidden in ("password_hash", "token_hash", "encrypted_secret"):
        assert forbidden not in serialized
```

- [ ] **Step 3: Run tests and verify RED**

```bash
pytest -q api/tests/integration/test_health.py
```

Expected: FAIL because readiness and CORS assembly are absent.

- [ ] **Step 4: Implement bounded database readiness**

`check_database()` uses `asyncio.timeout(timeout_seconds)`, obtains a pool connection, and executes the constant query `SELECT 1`. It propagates internal errors to the router. The router catches timeout/database exceptions and raises `AppError(503, "not_ready", "Database readiness check failed")` without including the original exception.

- [ ] **Step 5: Assemble the application**

In `create_app()`:

- Set title `PromptVault API`, version `0.1.0`, and docs/OpenAPI URLs enabled outside production.
- Add `CORSMiddleware` using only `settings.cors_origins`, credentials enabled, explicit common methods, and `Authorization`, `Content-Type`, `X-Request-ID` headers.
- Add request-ID middleware outermost.
- Install exception handlers.
- Include the health router.
- Preserve module-level `app = create_app()`.

- [ ] **Step 6: Run focused and full verification**

```bash
pytest -q api/tests/integration/test_health.py
pytest -q api/tests
ruff check api
python3 -m compileall -q api/app api/tests
```

Expected: all tests pass, Ruff exits 0, and compilation exits 0.

- [ ] **Step 7: Commit Task 4**

```bash
git add api/app/db/health.py api/app/routers/health.py api/app/main.py api/tests/conftest.py api/tests/integration/test_health.py
git commit -m "feat: expose API liveness and database readiness"
```

### Task 5: Foundation documentation and clean verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/phase-0-task-list.md`

**Interfaces:**
- Consumes: Completed Batch 1 application factory and contract.
- Produces: Repeatable developer commands and documentation aligned with the implemented foundation.

- [ ] **Step 1: Document exact foundation commands**

Add README sections covering:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r api/requirements-dev.txt
cp .env.example .env
uvicorn api.app.main:app --reload --port 8000
pytest -q api/tests
ruff check api
```

Document `/health` versus `/ready`, required variables, and that database migrations arrive in Batch 2. Update architecture with the actual module names if implementation differs. Mark Batch 0's review gate complete without changing any implementation-status row to `Verified` prematurely.

- [ ] **Step 2: Run all Batch 1 verification**

```bash
pytest -q api/tests
ruff check api
python3 -m compileall -q api/app api/tests
git diff --check
```

Expected: zero test failures, zero lint errors, successful compilation, and no whitespace errors.

- [ ] **Step 3: Commit Task 5**

```bash
git add README.md docs/architecture.md docs/phase-0-task-list.md
git commit -m "docs: add FastAPI foundation workflow"
```

## Batch 1 completion gate

Run from the repository root:

```bash
pytest -q api/tests
ruff check api
python3 -m compileall -q api/app api/tests
git diff --check
```

Batch 1 is complete only when the API starts with valid configuration, pool startup/shutdown is proven, every response carries a request ID, errors match the shared envelope, `/health` stays independent of PostgreSQL, `/ready` performs a bounded database round trip, configured CORS works, OpenAPI loads safely, and every command above exits successfully.
