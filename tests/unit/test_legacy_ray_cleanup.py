"""Legacy cleanup cancels pending work without resubmitting settled tasks."""
from types import SimpleNamespace

import pytest

from hponas import legacy_executors as module


@pytest.mark.parametrize('initialized', [False, True])
def test_cleanup_preserves_terminal_tasks_and_shared_cluster(monkeypatch, initialized):
    completed, failed, pending = object(), object(), object()
    checked, cancelled = [], []

    def wait(refs, timeout):
        assert initialized, 'Cleanup restarted a stopped cluster'
        assert timeout == 0, 'Cleanup blocked waiting for unfinished work'
        checked.extend(refs)
        return ([refs[0]], []) if refs[0] in (completed, failed) else ([], refs)

    def cancel(future):
        assert future is pending, 'Cleanup cancelled a terminal task'
        cancelled.append(future)

    # There is deliberately no init/shutdown: this executor does not own the
    # shared cluster and must not restart it or disconnect other clients.
    monkeypatch.setattr(module, 'ray', SimpleNamespace(
        is_initialized=lambda: initialized, wait=wait, cancel=cancel))
    executor = object.__new__(module.RayExecutor)
    executor._futures = dict(completed=completed, failed=failed, pending=pending)
    executor._trial_configs = {name: {} for name in executor._futures}
    executor.shutdown()
    assert checked == ([completed, failed, pending] if initialized else [])
    assert cancelled == ([pending] if initialized else [])
    assert executor._futures == executor._trial_configs == {}
    executor.shutdown()
    assert cancelled == ([pending] if initialized else [])
