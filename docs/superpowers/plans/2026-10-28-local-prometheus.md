# Local Prometheus Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal local PromptVault launcher start a native, loopback-only Prometheus server that scrapes the existing API metrics endpoint without touching PostgreSQL data.

**Architecture:** A repository-owned Prometheus configuration scrapes `127.0.0.1:8000`, while focused helpers in `scripts/start-local.py` resolve the installed binary and build its fixed local command. The existing launcher owns Prometheus as another process-group child, so its current shutdown path terminates all three services; time-series files live in an ignored repository-local directory.

**Tech Stack:** Python 3.11+, Prometheus configuration YAML, pytest, native Prometheus binary

**Spec:** `docs/superpowers/specs/2026-10-28-local-prometheus-design.md`

## Global Constraints

- Normal startup must continue to use PostgreSQL at `localhost:5432/promptvault` from the root `.env`.
- Existing migration/checksum validation must run unchanged and no startup path may reset or seed the database.
- API, web, and Prometheus ports are fixed at `8000`, `5173`, and `9090` respectively.
- Prometheus must bind and scrape only through loopback.
- Prometheus time-series storage must remain separate from PostgreSQL and ignored by Git.
- Do not add Docker, Grafana, Alertmanager, deployment configuration, or any LLM provider changes.

## Review Focus

- Missing `prometheus` executable must produce an actionable `RuntimeError` mentioning `brew install prometheus`; tested in Task 1.
- A busy port `9090` must stop startup rather than select another port; tested in Task 1.
- Paths containing spaces must remain single subprocess arguments; tested in Task 1.
- The scrape target must be the loopback API endpoint and must not include PostgreSQL; tested in Task 1.
- Launcher shutdown must signal every owned process group, including Prometheus; tested through an extracted shutdown helper in Task 1.

---

### Task 1: Prometheus configuration and launcher integration

**Files:**
- Create: `monitoring/prometheus.yml`
- Modify: `scripts/start-local.py`
- Modify: `.gitignore`
- Test: `tests/delivery/test_local_startup.py`

**Interfaces:**
- Consumes: existing `ROOT`, `require_free_port(port: int) -> None`, and launcher child-process lifecycle in `scripts/start-local.py`
- Produces: `PROMETHEUS_PORT: int`, `PROMETHEUS_CONFIG: Path`, `PROMETHEUS_STORAGE: Path`, `resolve_prometheus_binary() -> str`, `prometheus_command(binary: str, *, config: Path, storage: Path) -> list[str]`, and `stop_process_groups(children: Iterable[ProcessLike]) -> None`

- [ ] **Step 1: Add failing launcher and configuration tests**

Add tests named:

- `test_prometheus_configuration_scrapes_api_over_loopback`
- `test_resolve_prometheus_binary_reports_install_command`
- `test_prometheus_command_uses_fixed_loopback_port_and_separate_storage`
- `test_normal_startup_refuses_busy_prometheus_port`
- `test_stop_process_groups_signals_every_child`

Assert the configuration contains job `promptvault-api` and target `127.0.0.1:8000`, excludes `5432`, missing binary errors contain `brew install prometheus`, command arguments contain exact `--config.file=...`, `--storage.tsdb.path=...`, and `--web.listen-address=127.0.0.1:9090` values, port `9090` uses the existing fixed-port refusal behavior, and shutdown sends `SIGTERM` to every supplied child process group.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest tests/delivery/test_local_startup.py -q`

Expected: FAIL because the Prometheus constants/helpers/configuration do not exist.

- [ ] **Step 3: Add the minimal Prometheus configuration and launcher helpers**

Create `monitoring/prometheus.yml` with a 5-second global scrape interval and one static target, `127.0.0.1:8000`, under job `promptvault-api`. Add the constants and exact helper signatures above. Resolve with `shutil.which("prometheus")`; raise an actionable error when absent. Build the command as a list of complete arguments so paths with spaces are preserved. Extract the existing process-group termination loop into `stop_process_groups` without changing its behavior.

- [ ] **Step 4: Integrate Prometheus into normal startup**

Resolve the executable, validate port `9090` along with existing ports, create the local storage directory only after all validations and migrations pass, and append Prometheus via `subprocess.Popen(..., start_new_session=True)` to the same `children` list. Print `Prometheus: http://localhost:9090` with the existing local URLs. Have the existing nested `stop()` function call the tested `stop_process_groups` helper.

- [ ] **Step 5: Ignore local time-series data**

Add `.prometheus-data/` to `.gitignore`, matching `PROMETHEUS_STORAGE` exactly.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `python3 -m pytest tests/delivery/test_local_startup.py api/tests/unit/test_metrics.py -q`

Expected: all selected tests PASS.

- [ ] **Step 7: Commit the independently testable launcher integration**

```bash
git add monitoring/prometheus.yml scripts/start-local.py .gitignore tests/delivery/test_local_startup.py
git commit -m "feat: start Prometheus with local app"
```

### Task 2: Local monitoring documentation and verification

**Files:**
- Create: `docs/local-monitoring.md`
- Modify: `docs/demo-walkthrough.md`
- Test: `tests/delivery/test_local_startup.py`

**Interfaces:**
- Consumes: Task 1's fixed URLs `http://localhost:8000/metrics` and `http://localhost:9090`, and command `.venv/bin/python scripts/start-local.py`
- Produces: documented install, startup, health-check, query, storage, and troubleshooting workflow

- [ ] **Step 1: Add a failing documentation-contract test**

Add `test_local_monitoring_documentation_covers_install_start_and_query` asserting `docs/local-monitoring.md` contains `brew install prometheus`, the normal launcher command, both monitoring URLs, query `up{job="promptvault-api"}`, and a statement that `.prometheus-data/` is separate from PostgreSQL.

- [ ] **Step 2: Run the documentation test and verify RED**

Run: `python3 -m pytest tests/delivery/test_local_startup.py::test_local_monitoring_documentation_covers_install_start_and_query -q`

Expected: FAIL because `docs/local-monitoring.md` does not exist.

- [ ] **Step 3: Write the local monitoring guide and demo link**

Document Homebrew installation, one-command startup, raw metrics inspection, Prometheus UI/query verification, repository-local data retention, safe deletion only when the launcher is stopped, missing-binary and busy-port errors, and the fact that PostgreSQL remains untouched. Link the guide from `docs/demo-walkthrough.md` without changing the demo's database startup instructions.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python3 -m pytest tests/delivery/test_local_startup.py -q`

Expected: all local-startup delivery tests PASS.

- [ ] **Step 5: Validate configuration when Prometheus is available**

Run: `promtool check config monitoring/prometheus.yml`

Expected when installed: `SUCCESS`. If unavailable, record that limitation and rely on the configuration-contract test; do not install software or alter PostgreSQL automatically.

- [ ] **Step 6: Run repository verification**

Run: `python3 -m pytest -q`

Run: `npm run build` from `web/`

Expected: both commands exit `0`. Report any pre-existing dependency or database availability failures by exact test/command rather than hiding them.

- [ ] **Step 7: Commit documentation and verification contract**

```bash
git add docs/local-monitoring.md docs/demo-walkthrough.md tests/delivery/test_local_startup.py
git commit -m "docs: explain local Prometheus workflow"
```
