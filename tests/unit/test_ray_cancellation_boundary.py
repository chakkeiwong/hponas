"""A delayed cancellation must finish before its reporting actors disappear."""

from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import sys
import threading

import pytest

from hponas.executors import ray_executor as module
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.types import Config, Trial


class RayError(Exception):
    pass


class GetTimeoutError(RayError):
    pass


class Empty(Exception):
    pass


class DelayedCancellation:
    """Model the interval between a force-cancel request and worker exit.

    The task remains blocked on its live reporting channels until cancellation
    is acknowledged. Destroying a channel first permits the worker to return to
    the shared pool while its forced exit is still pending, as in the Ray log.
    """

    def __init__(self, *, stuck=False, fail_report=False, exit_delay=0.):
        self.clock = 0.0
        self.stuck, self.fail_report = stuck, fail_report
        self.exit_delay = exit_delay
        self.termination_waits = []
        self.cancel_requested = self.terminal = self.released_early = False
        self.channels = []
        self.future = object()
        self.exceptions = SimpleNamespace(RayError=RayError, GetTimeoutError=GetTimeoutError)

    def is_initialized(self):
        return True

    def remote(self, **options):
        return lambda fn: SimpleNamespace(remote=lambda *args: self.future)

    def wait(self, refs, timeout=None):
        # Ray's omitted timeout blocks. Driver polling must be explicitly
        # nonblocking while workers can be waiting for reporting replies.
        assert timeout == 0
        return ([self.future], []) if self.terminal else ([], refs)

    def cancel(self, future, force=False):
        assert future is self.future and force
        self.cancel_requested = True

    def get(self, future, timeout=None):
        assert future is self.future
        assert timeout is not None and 0 < timeout <= 30
        self.termination_waits.append(timeout)
        if self.stuck or self.exit_delay > timeout:
            raise GetTimeoutError("termination not acknowledged")
        self.clock += self.exit_delay
        self.terminal = True
        raise RayError("worker exited after cancellation")

    def queue(self, actor_options):
        owner = self

        class Channel:
            closed = False

            def get(self, timeout):
                # The exact virtual deadline must end polling. Without this
                # contract check a wrong > boundary can loop forever at zero.
                assert timeout > 0
                if owner.fail_report:
                    return ProgressReport("trial", "trial", 1., 5., 1., .1)
                owner.clock += timeout
                raise Empty()

            def shutdown(self, force=False):
                self.closed = True
                if owner.cancel_requested and not owner.terminal:
                    owner.released_early = True

        channel = Channel()
        self.channels.append(channel)
        return channel


def install(monkeypatch, **kwargs):
    transport = DelayedCancellation(**kwargs)
    monkeypatch.setitem(sys.modules, "ray", transport)
    monkeypatch.setitem(sys.modules, "ray.util.queue", SimpleNamespace(Queue=transport.queue, Empty=Empty))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: transport.clock))
    return transport


def test_streaming_timeout_does_not_release_channels_before_worker_exit(monkeypatch):
    transport = install(monkeypatch)
    executor = module.RayExecutor(max_retries=0, timeout=.05)
    trial = Trial(Config({}), "trial", fidelity=4.)
    result = executor.execute(trial, lambda _: 1, on_report=lambda _: ReportDecision())
    assert result.status == "timeout" and result.metadata["attempts"] == 1
    assert transport.cancel_requested and transport.terminal
    assert not transport.released_early
    assert all(channel.closed for channel in transport.channels)
    assert len(transport.termination_waits) == 1


def test_controller_failure_also_waits_for_owned_worker_exit(monkeypatch):
    transport = install(monkeypatch, fail_report=True)
    executor = module.RayExecutor(max_retries=0, timeout=1)

    def refuse(report):
        raise ValueError("foreign report")

    with pytest.raises(ValueError, match="^foreign report$"):
        executor.execute(Trial(Config({}), "trial", fidelity=4.), lambda _: 1, on_report=refuse)
    assert transport.cancel_requested and transport.terminal
    assert not transport.released_early
    assert all(channel.closed for channel in transport.channels)


def test_unacknowledged_cancellation_refuses_to_return_a_completed_cleanup(monkeypatch):
    transport = install(monkeypatch, stuck=True)
    executor = module.RayExecutor(max_retries=1, timeout=.05)
    with pytest.raises(RuntimeError, match="^Ray worker cancellation did not finish within 30 seconds$"):
        executor.execute(Trial(Config({}), "trial", fidelity=4.), lambda _: 1,
                         on_report=lambda _: ReportDecision())
    assert transport.cancel_requested and not transport.terminal
    assert len(transport.channels) == 2  # No fresh attempt enters a poisoned pool.
    assert all(channel.closed for channel in transport.channels)
    with pytest.raises(RuntimeError, match="unconfirmed worker cancellation"):
        executor.execute(Trial(Config({}), "later", fidelity=4.), lambda _: 1)
    assert len(transport.channels) == 2


def test_completed_task_needs_no_cancellation(monkeypatch):
    transport = install(monkeypatch)
    transport.terminal = True
    module.RayExecutor()._cancel_and_drain(transport.future)
    assert not transport.cancel_requested


@pytest.mark.parametrize("streaming", [False, True])
def test_unconfirmed_cancellation_refuses_trials_already_queued_in_batch(monkeypatch, streaming):
    transport = install(monkeypatch, stuck=True)
    queued = threading.Event()
    remote_calls = []
    original_get, original_remote = transport.get, transport.remote

    class ObservedPool(ThreadPoolExecutor):
        submissions = 0

        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            self.submissions += 1
            if self.submissions == 2:
                queued.set()
            return future

    def await_submission(*args, **kwargs):
        assert queued.wait(2), "batch did not queue its second trial"
        return original_get(*args, **kwargs)

    def remote(**options):
        def decorate(fn):
            wrapped = original_remote(**options)(fn)

            def submit(*args):
                remote_calls.append(args)
                return wrapped.remote(*args)

            return SimpleNamespace(remote=submit)

        return decorate

    monkeypatch.setattr(module, "ThreadPoolExecutor", ObservedPool)
    transport.get, transport.remote = await_submission, remote
    executor = module.RayExecutor(num_workers=1, max_retries=0, timeout=.05)
    batch = [Trial(Config({}), name, fidelity=4.) for name in ("first", "queued")]
    callback = (lambda _: ReportDecision()) if streaming else None
    with pytest.raises(RuntimeError, match="^Ray worker cancellation did not finish within 30 seconds$"):
        executor.execute_batch(batch, lambda _: 1, on_report=callback)
    assert len(remote_calls) == 1, "queued trial entered the unconfirmed worker pool"
    assert len(transport.channels) == (2 if streaming else 0)


def test_failed_attempt_accounts_for_work_until_cancellation_is_acknowledged(monkeypatch):
    transport = install(monkeypatch, exit_delay=29.5)
    executor = module.RayExecutor(max_retries=0, timeout=.05)
    result = executor.execute(Trial(Config({}), "trial", fidelity=4.), lambda _: 1,
                              on_report=lambda _: ReportDecision())
    assert result.status == "timeout"
    assert result.cost == pytest.approx(29.55)
    assert result.metadata["failed_attempt_elapsed_seconds"] == pytest.approx(29.55)
    assert result.metadata["execution"]["elapsed_seconds"] == pytest.approx(29.55)
    assert transport.termination_waits == [30.]
