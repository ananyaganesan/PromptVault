"""The icon opens the browser only after the fixed local servers are ready."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('macos_launcher', ROOT / 'scripts/macos/launch.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_existing_ready_servers_open_browser_without_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'servers_ready', lambda: True)
    start = Mock()
    open_browser = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', start)
    monkeypatch.setattr(launcher.subprocess, 'run', open_browser)
    launcher.launch(tmp_path)
    start.assert_not_called()
    open_browser.assert_called_once_with(['/usr/bin/open', 'http://localhost:5173'], check=True)


def test_new_servers_wait_for_readiness_and_detach_output(monkeypatch, tmp_path):
    readiness = iter([False, False, True])
    monkeypatch.setattr(launcher, 'servers_ready', lambda: next(readiness))
    monkeypatch.setattr(launcher.time, 'sleep', lambda _: None)
    child = Mock(pid=12345)
    child.poll.return_value = None
    start = Mock(return_value=child)
    open_browser = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', start)
    monkeypatch.setattr(launcher.subprocess, 'run', open_browser)
    launcher.launch(tmp_path)
    args, kwargs = start.call_args
    assert args[0] == [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/start-local.py')]
    assert kwargs['start_new_session'] is True
    assert kwargs['stdin'] == launcher.subprocess.DEVNULL
    assert kwargs['stdout'].closed
    assert kwargs['stderr'] is kwargs['stdout']
    open_browser.assert_called_once()


@pytest.mark.parametrize('exited', [True, False])
def test_failed_or_timed_out_servers_do_not_open_browser(monkeypatch, tmp_path, exited):
    monkeypatch.setattr(launcher, 'servers_ready', lambda: False)
    child = Mock(pid=12345)
    child.poll.return_value = 1 if exited else None
    monkeypatch.setattr(launcher.subprocess, 'Popen', Mock(return_value=child))
    open_browser = Mock()
    monkeypatch.setattr(launcher.subprocess, 'run', open_browser)
    with pytest.raises(RuntimeError, match='stopped' if exited else 'did not become ready'):
        launcher.launch(tmp_path, timeout=0)
    open_browser.assert_not_called()


def test_repeated_click_reuses_starting_process(monkeypatch, tmp_path):
    readiness = iter([False, True])
    monkeypatch.setattr(launcher, 'servers_ready', lambda: next(readiness))
    monkeypatch.setattr(launcher, 'process_running', lambda _: True)
    start = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', start)
    open_browser = Mock()
    monkeypatch.setattr(launcher.subprocess, 'run', open_browser)
    launcher.launch(tmp_path)
    start.assert_not_called()
    open_browser.assert_called_once()
