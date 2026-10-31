"""Start the local app on fixed ports using the persistent Supabase database."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app.config import Settings
from api.app.db.migrations import migrate_database

API_PORT = 8000
WEB_PORT = 5173
SUPABASE_PROJECT_REF = 'ehnufhcdgxllubnpjfuc'
SUPABASE_POOLER_HOST = 'aws-0-eu-west-1.pooler.supabase.com'
SUPABASE_POOLER_PORT = 5432
SUPABASE_DATABASE = 'postgres'
SUPABASE_USERNAME = f'postgres.{SUPABASE_PROJECT_REF}'


def validate_database_url(url: str) -> None:
    parts = urlsplit(url)
    ssl_modes = parse_qs(parts.query).get('sslmode', [])
    if (
        parts.scheme != 'postgresql'
        or parts.hostname != SUPABASE_POOLER_HOST
        or parts.port != SUPABASE_POOLER_PORT
        or parts.username != SUPABASE_USERNAME
        or parts.path != f'/{SUPABASE_DATABASE}'
        or ssl_modes != ['require']
    ):
        raise ValueError(
            'Normal local startup requires the approved Supabase session pooler '
            'on port 5432 with sslmode=require'
        )


def require_free_port(port: int) -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(('127.0.0.1', port))
        except OSError as error:
            raise RuntimeError(f'Port {port} is already in use; stop that app and retry. '
                               'The launcher will not switch ports.') from error


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
        if port != SUPABASE_POOLER_PORT:
            raise ValueError('Connected PostgreSQL server must use port 5432')
        if database != SUPABASE_DATABASE:
            raise ValueError('Connected database must be postgres')
    print(f'PostgreSQL: Supabase session pooler / {database}', flush=True)
    if args.check:
        return 0
    for port in (API_PORT, WEB_PORT):
        require_free_port(port)
    # Preserve migration checksums and existing records; never reset or auto-seed.
    migrate_database(settings.database_url, ROOT / 'db' / 'migrations')
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
        for child in children:
            try:
                # npm starts Vite as a child: stopping only npm leaves the web
                # port occupied. Each app has its own process group here.
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'api.app.main:app', '--host', '127.0.0.1',
             '--port', str(API_PORT)], cwd=ROOT, env=environment, start_new_session=True,
        ))
        children.append(subprocess.Popen(
            ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(WEB_PORT), '--strictPort'],
            cwd=ROOT / 'web', env=environment, start_new_session=True,
        ))
        print('App: http://localhost:5173 | API: http://localhost:8000', flush=True)
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
