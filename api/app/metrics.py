"""Low-cardinality process metrics safe for Prometheus scraping."""

from collections import defaultdict
from threading import Lock
from time import monotonic

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class ApplicationMetrics:
    def __init__(self) -> None:
        self.started = monotonic()
        self.requests: dict[tuple[str, int], int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.duration_count = 0
        self.duration_sum = 0.0
        self.lock = Lock()

    def record(self, method: str, status: int, duration_seconds: float) -> None:
        with self.lock:
            self.requests[(method, status)] += 1
            self.duration_count += 1
            self.duration_sum += duration_seconds

    def record_error(self, code: str) -> None:
        with self.lock:
            self.errors[code] += 1

    def render(self) -> str:
        with self.lock:
            lines = [
                "# HELP promptvault_http_requests_total HTTP responses by method and status.",
                "# TYPE promptvault_http_requests_total counter",
            ]
            for (method, status), count in sorted(self.requests.items()):
                lines.append(
                    "promptvault_http_requests_total"
                    f'{{method="{_label(method)}",status="{status}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP promptvault_errors_total Application errors by stable code.",
                    "# TYPE promptvault_errors_total counter",
                ]
            )
            for code, count in sorted(self.errors.items()):
                lines.append(f'promptvault_errors_total{{code="{_label(code)}"}} {count}')
            lines.extend(
                [
                    "# HELP promptvault_http_request_duration_seconds Request duration.",
                    "# TYPE promptvault_http_request_duration_seconds summary",
                    f"promptvault_http_request_duration_seconds_count {self.duration_count}",
                    f"promptvault_http_request_duration_seconds_sum {self.duration_sum:.9f}",
                    "# HELP promptvault_process_uptime_seconds Process uptime.",
                    "# TYPE promptvault_process_uptime_seconds gauge",
                    f"promptvault_process_uptime_seconds {monotonic() - self.started:.3f}",
                ]
            )
        return "\n".join(lines) + "\n"


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp, *, metrics: ApplicationMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        started = monotonic()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            self.metrics.record(
                str(scope.get("method", "UNKNOWN")),
                status,
                monotonic() - started,
            )
