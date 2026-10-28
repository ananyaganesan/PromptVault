# Local monitoring with Prometheus

PromptVault starts a local Prometheus server with the API and web app. Prometheus
scrapes the API's existing metrics endpoint and keeps its time-series files separate
from PostgreSQL.

## Install Prometheus

Install the native Prometheus tools once with Homebrew:

```sh
brew install prometheus
```

Confirm both commands are available:

```sh
prometheus --version
promtool --version
```

The launcher reports `brew install prometheus` and stops safely when the executable
is missing. It does not fall back to Docker or another monitoring service.

## Start PromptVault and monitoring

Keep using the persistent `promptvault` database configured in the root `.env`, then
run the normal launcher from the repository root:

```sh
.venv/bin/python scripts/start-local.py
```

The launcher keeps all ports fixed and opens only loopback listeners:

- App: <http://localhost:5173>
- API metrics: <http://localhost:8000/metrics>
- Prometheus: <http://localhost:9090>

If port `5173`, `8000`, or `9090` is occupied, startup stops and asks you to close
the process using that port. It never switches to an unexpected port.

## Verify collection

Open <http://localhost:8000/metrics> to inspect the raw PromptVault counters. After
making a few requests in the app, open <http://localhost:9090> and run this query:

```promql
up{job="promptvault-api"}
```

A value of `1` means Prometheus can scrape the API. Useful application series include
`promptvault_http_requests_total`, `promptvault_errors_total`,
`promptvault_http_request_duration_seconds`, and
`promptvault_process_uptime_seconds`.

Validate the repository configuration directly with:

```sh
promtool check config monitoring/prometheus.yml
```

## Storage and shutdown

Prometheus writes local time-series data to `.prometheus-data/`. This ignored
directory is separate from PostgreSQL: monitoring does not reset, migrate, copy, or
store data in the existing `promptvault` database.

Stopping `scripts/start-local.py` stops Prometheus together with the API and web app.
If you want to discard monitoring history, first stop the launcher, then move or
delete only `.prometheus-data/`. Do not remove or reset the PostgreSQL database.
