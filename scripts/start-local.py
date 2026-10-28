"""Start the local app on fixed ports using the existing pgAdmin PostgreSQL server."""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app.config import Settings
from api.app.db.migrations import migrate_database

API_PORT = 8000
WEB_PORT = 5173
PROMETHEUS_PORT = 9090
PROMETHEUS_CONFIG = ROOT / 'monitoring' / 'prometheus.yml'
PROMETHEUS_STORAGE = ROOT / '.prometheus-data'


class ProcessLike(Protocol):
    pid: int


def validate_database_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.hostname not in {'localhost', '127.0.0.1', '::1'} or (parts.port or 5432) != 5432:
        raise ValueError('Normal local startup requires PostgreSQL on localhost:5432')
    if parts.path != '/promptvault':
        raise ValueError('Normal local startup requires the persistent promptvault database')


def require_free_port(port: int) -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(('127.0.0.1', port))
        except OSError as error:
            raise RuntimeError(f'Port {port} is already in use; stop that app and retry. '
                               'The launcher will not switch ports.') from error


def resolve_prometheus_binary() -> str:
    binary = shutil.which('prometheus')
    if binary is None:
        raise RuntimeError(
            'Prometheus is not installed; run `brew install prometheus` and retry.'
        )
    return binary


def prometheus_command(binary: str, *, config: Path, storage: Path) -> list[str]:
    return [
        binary,
        f'--config.file={config}',
        f'--storage.tsdb.path={storage}',
        f'--web.listen-address=127.0.0.1:{PROMETHEUS_PORT}',
    ]


def stop_process_groups(children: Iterable[ProcessLike]) -> None:
    for child in children:
        try:
            # npm starts Vite as a child: stopping only npm leaves the web
            # port occupied. Each app has its own process group here.
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check PostgreSQL settings without starting')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    settings = Settings(_env_file=ROOT / '.env')
    validate_database_url(settings.database_url)
    if settings.environment != 'development':
        raise ValueError('Normal local startup requires ENVIRONMENT=development')
    with psycopg.connect(settings.database_url, connect_timeout=5) as connection:
        database, port = connection.execute('SELECT current_database(),inet_server_port()').fetchone()
        if port != 5432:
            raise ValueError('Connected PostgreSQL server must use port 5432')
        if database != 'promptvault':
            raise ValueError('Connected database must be promptvault')
    print(f'PostgreSQL: localhost:5432 / {database}', flush=True)
    if args.check:
        return 0
    prometheus_binary = resolve_prometheus_binary()
    for port in (API_PORT, WEB_PORT, PROMETHEUS_PORT):
        require_free_port(port)
    # Preserve migration checksums and existing records; never reset or auto-seed.
    migrate_database(settings.database_url, ROOT / 'db' / 'migrations')
    PROMETHEUS_STORAGE.mkdir(exist_ok=True)
    environment = {
        **os.environ,
        'DATABASE_URL': settings.database_url,
        'CORS_ORIGINS': 'http://localhost:5173,http://127.0.0.1:5173',
        'VITE_API_BASE_URL': 'http://localhost:8000',
        'VITE_API_URL': 'http://localhost:8000',
        'VITE_USE_DEMO_DATA': 'false',
    }
    children = []
    stopping = False

    def stop(_signal=None, _frame=None) -> None:
        nonlocal stopping
        stopping = True
        stop_process_groups(children)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'api.app.main:app', '--host', '127.0.0.1',
             '--port', str(API_PORT)], cwd=ROOT, env=environment, start_new_session=True,
        ))
        children.append(subprocess.Popen(
            prometheus_command(
                prometheus_binary,
                config=PROMETHEUS_CONFIG,
                storage=PROMETHEUS_STORAGE,
            ),
            cwd=ROOT,
            env=environment,
            start_new_session=True,
        ))
        children.append(subprocess.Popen(
            ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(WEB_PORT), '--strictPort'],
            cwd=ROOT / 'web', env=environment, start_new_session=True,
        ))
        print(
            'App: http://localhost:5173 | API: http://localhost:8000 | '
            'Prometheus: http://localhost:9090',
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.2)
        return 0 if stopping else next((child.returncode for child in children if child.returncode), 0)
    finally:
        stop()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, psycopg.Error) as error:
        # Database credentials and DSNs must not appear in diagnostic output.
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print(f'Local startup stopped: {message}', file=sys.stderr)
        raise SystemExit(1) from None
