"""Normal local startup must not switch to another database server or test data."""

import importlib.util
import signal
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_startup", ROOT / "scripts/start-local.py"
)
startup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@localhost:55435/promptvault",
        "postgresql://user:pass@localhost:5432/promptvault_test",
        "postgresql://user:pass@localhost:5432/another_database",
        "postgresql://user:pass@example.com:5432/promptvault",
    ],
)
def test_normal_startup_rejects_alternate_database_targets(url: str) -> None:
    with pytest.raises(ValueError):
        startup.validate_database_url(url)


def test_normal_startup_reports_busy_port_instead_of_selecting_another() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="will not switch ports"):
            startup.require_free_port(port)


def test_normal_startup_can_reuse_a_port_after_the_previous_server_closes() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        with socket.create_connection(("127.0.0.1", port)) as client:
            connection, _ = listener.accept()
            connection.close()
            assert client.recv(1) == b""
    startup.require_free_port(port)


def test_prometheus_configuration_scrapes_api_over_loopback() -> None:
    configuration = yaml.safe_load((ROOT / "monitoring/prometheus.yml").read_text())

    assert configuration["global"]["scrape_interval"] == "5s"
    assert configuration["scrape_configs"] == [
        {
            "job_name": "promptvault-api",
            "static_configs": [{"targets": ["127.0.0.1:8000"]}],
        }
    ]
    assert "5432" not in str(configuration)


def test_resolve_prometheus_binary_reports_install_command(monkeypatch) -> None:
    monkeypatch.setattr(startup.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="brew install prometheus"):
        startup.resolve_prometheus_binary()


def test_prometheus_command_uses_fixed_loopback_port_and_separate_storage(
    tmp_path: Path,
) -> None:
    config = tmp_path / "configuration with spaces.yml"
    storage = tmp_path / "time series with spaces"

    command = startup.prometheus_command(
        "/opt/homebrew/bin/prometheus",
        config=config,
        storage=storage,
    )

    assert command == [
        "/opt/homebrew/bin/prometheus",
        f"--config.file={config}",
        f"--storage.tsdb.path={storage}",
        "--web.listen-address=127.0.0.1:9090",
    ]


def test_normal_startup_refuses_busy_prometheus_port() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 9090))

        with pytest.raises(RuntimeError, match="Port 9090.*will not switch ports"):
            startup.require_free_port(startup.PROMETHEUS_PORT)


def test_stop_process_groups_signals_every_child(monkeypatch) -> None:
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        startup.os,
        "killpg",
        lambda pid, requested_signal: signals.append((pid, requested_signal)),
    )
    children = [SimpleNamespace(pid=101), SimpleNamespace(pid=202)]

    startup.stop_process_groups(children)

    assert signals == [(101, signal.SIGTERM), (202, signal.SIGTERM)]
