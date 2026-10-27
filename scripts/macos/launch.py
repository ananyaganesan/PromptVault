"""Open the local app in the default browser after both servers are ready."""

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = Path.home() / 'Library' / 'Logs' / 'PromptVault'
WEB_URL = 'http://localhost:5173'
API_URL = 'http://127.0.0.1:8000/ready'


def servers_ready() -> bool:
    for url in (API_URL, WEB_URL):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status != 200:
                    return False
        except (OSError, URLError):
            return False
    return True


def process_running(pid_file: Path) -> bool:
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def launch(log_dir: Path = LOG_DIR, timeout: float = 120) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / 'launcher.lock').open('a') as lock:
        # Serialize repeated icon clicks without starting duplicate servers.
        fcntl.flock(lock, fcntl.LOCK_EX)
        child = None
        pid_file = log_dir / 'local-server.pid'
        if not servers_ready():
            if not process_running(pid_file):
                with (log_dir / 'local-server.log').open('a') as log:
                    child = subprocess.Popen(
                        [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/start-local.py')],
                        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        start_new_session=True,
                    )
                pid_file.write_text(str(child.pid))
            deadline = time.monotonic() + timeout
            while not servers_ready():
                if child is not None and child.poll() is not None:
                    raise RuntimeError(f'Local servers stopped. See {log_dir / "local-server.log"}.')
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'Local servers did not become ready. See {log_dir / "local-server.log"}.')
                time.sleep(0.5)
        # Run this directly, before any optional notification, and close all
        # server output handles so AppleScript can finish its shell command.
        subprocess.run(['/usr/bin/open', WEB_URL], check=True)


if __name__ == '__main__':
    try:
        launch()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'PromptVault could not open: {error}', file=sys.stderr)
        raise SystemExit(1) from None
