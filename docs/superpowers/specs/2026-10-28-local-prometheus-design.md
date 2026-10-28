# Local Prometheus Integration Design

## Intent

PromptVault's normal local launcher should start a native Prometheus process beside the API and web app so local request and error metrics are available without a separate manual command. Monitoring must remain local and must not alter or depend on the persistent PostgreSQL data.

## Goals

- Start Prometheus from `scripts/start-local.py` using the installed `prometheus` binary.
- Scrape the API's existing `http://127.0.0.1:8000/metrics` endpoint.
- Expose the Prometheus UI on `http://127.0.0.1:9090`.
- Store time-series data in a repository-local ignored directory that is separate from PostgreSQL.
- Stop Prometheus whenever the launcher stops the API and web processes.
- Report actionable errors for a missing binary or an occupied port without switching ports.
- Document installation, startup, and basic verification.

## Non-goals and anti-goals

- No Grafana, alert manager, remote storage, deployment, or production configuration.
- No Docker dependency or alternate startup workflow.
- No database reset, database copy, schema bypass, or Prometheus data in PostgreSQL.
- No other LLM provider or provider-related configuration change.

## Constraints

- Normal startup continues to use PostgreSQL at `localhost:5432/promptvault` from the root `.env`.
- Existing migration and checksum validation remains in place and runs before child processes start.
- API and web ports remain fixed at `8000` and `5173`; Prometheus uses fixed port `9090`.
- Prometheus listens only on loopback.

## Approaches

1. **Native one-command startup (selected):** keep a repository-owned Prometheus configuration and launch the locally installed binary from `scripts/start-local.py`. This best matches the existing native local workflow and avoids Docker.
2. **Docker sidecar:** isolate the executable but require Docker Desktop and special host routing. Rejected because the user selected the simpler native workflow.
3. **Manual Prometheus command:** add only configuration and documentation. Rejected because it would not provide the requested integrated startup.

## Design

Add `monitoring/prometheus.yml` with one static scrape target, `127.0.0.1:8000`, and a conservative local scrape interval. Add small launcher helpers that resolve the binary, build a deterministic command, and retain the existing process-group shutdown behavior. Before migrations or child startup, validate that the binary exists and ports `5173`, `8000`, and `9090` are free. Start Prometheus after the API process with loopback web binding, the repository configuration, and a repository-local storage path.

Ignore the time-series storage directory in Git. Add delivery tests for the configuration contract and command construction, plus launcher validation for a missing binary and fixed monitoring port. Update local documentation with installation and URLs.

## Completion criteria

Automated tests prove the scrape target and launcher command, the existing local-startup tests remain green, the web build succeeds, and a configuration validation or equivalent Prometheus startup check passes when the binary is available. If the local database or Prometheus binary is unavailable, report that limitation explicitly rather than modifying the database or claiming an end-to-end run.
