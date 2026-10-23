"""Owned-process and argument boundaries of the fixed offline install helper."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'gap_installation_helper', ROOT / 'program_operations/verify_gap_installation.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def test_install_helper_refuses_cli_and_unowned_or_aliased_output(tmp_path):
    for args in (['extra'], ['--python', sys.executable], ['--output', str(tmp_path)]):
        result = subprocess.run([sys.executable, '-I', str(SPEC.origin), *args],
                                capture_output=True, timeout=5)
        assert result.returncode == 2
        assert b'accepts no arguments' in result.stderr
    for path in ('', str(tmp_path), str(ROOT / 'docs/program/operations-runs/absent')):
        with pytest.raises(ValueError, match='fixed runner'):
            helper.operation_directory(path)
    assert not list(tmp_path.iterdir())


def test_timeout_retires_child_and_grandchild_in_the_operation_group(tmp_path):
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    run = helper.BoundedRun(tmp_path, tmp_path, env, seconds=5)
    code = """import os,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
print(os.getpid(), child.pid, os.getpgrp(), flush=True)
time.sleep(30)
"""
    began = time.monotonic()
    with pytest.raises(TimeoutError, match='fixed deadline'):
        run.run('owned', [sys.executable, '-c', code], seconds=.5)
    assert time.monotonic() - began < 5
    own, descendant, group = map(int, (tmp_path / 'owned.log').read_text().split())
    assert group == os.getpgrp()  # Neither child escaped the runner's group.
    for pid in (own, descendant):
        assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    assert not run.cleanup()
    assert len(run.steps) == 1 and 'TimeoutError' in run.steps[0]['failure']


def test_failed_install_step_keeps_log_and_stops_immediately(tmp_path):
    run = helper.BoundedRun(tmp_path, tmp_path, dict(os.environ), seconds=5)
    with pytest.raises(RuntimeError, match='failed with code 7'):
        run.run('failure', [sys.executable, '-c', 'print("retained failure");raise SystemExit(7)'])
    assert (tmp_path / 'failure.log').read_text() == 'retained failure\n'
    assert run.steps[0]['returncode'] == 7
    assert not run.cleanup()


def test_machine_output_stays_parseable_with_retained_dependency_warning(tmp_path):
    run = helper.BoundedRun(tmp_path, tmp_path, dict(os.environ), seconds=5)
    code = 'import json,warnings;warnings.warn("retained dependency warning");print(json.dumps({"completed":True}))'
    run.run('json-with-warning', [sys.executable, '-c', code])
    assert json.loads((tmp_path / 'json-with-warning.log').read_text()) == {'completed': True}
    assert 'retained dependency warning' in (tmp_path / 'json-with-warning.stderr.log').read_text()
    assert run.steps[0]['returncode'] == 0
    assert not run.cleanup()
