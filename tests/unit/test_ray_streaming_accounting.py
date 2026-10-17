"""Deterministic public streaming checks; live Ray conformance stays required."""

from types import SimpleNamespace
import math
import sys

import pytest

import hponas.executors.ray_executor as implementation
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.types import Config, Trial


class RayError(Exception):
    pass


class GetTimeoutError(RayError):
    pass


class Empty(Exception):
    pass


class ScriptedRay:
    def __init__(self, scenarios=(), fail_channel=None):
        self.clock = 0.
        self.scenarios = list(scenarios)
        self.channels, self.options, self.submissions, self.decisions = [], [], [], []
        self.poll_intervals = []
        self.cancelled = []
        self.fail_channel = fail_channel
        self.queue_calls = 0
        self.exceptions = SimpleNamespace(RayError=RayError, GetTimeoutError=GetTimeoutError)

    def is_initialized(self):
        return True

    def queue(self, actor_options=None):
        self.queue_calls += 1
        # The public executor promises zero-CPU control actors so a fully
        # occupied worker pool can still initialize reporting channels.
        assert actor_options == {"num_cpus": 0}
        if self.queue_calls == self.fail_channel:
            raise RayError("channel startup failed")
        owner = self

        class Channel:
            closed = False
            future = None

            def get(self, timeout=None):
                assert timeout is not None and timeout > 0
                owner.poll_intervals.append(timeout)
                if not self.future.reports:
                    owner.clock += timeout
                    raise Empty()
                owner.clock += .25
                return self.future.reports.pop(0)

            def put(self, decision):
                owner.decisions.append(decision)

            def shutdown(self, force=False):
                assert force is True
                self.closed = True

        channel = Channel()
        self.channels.append(channel)
        return channel

    def remote(self, **options):
        self.options.append(options)

        def decorate(function):
            def submit(trial, objective, requests, replies):
                scenario = self.scenarios.pop(0)
                future = SimpleNamespace(reports=list(scenario.get("reports", [])),
                                         outcome=scenario["outcome"], terminal=False,
                                         ready_at=scenario.get("ready_at", 0.),
                                         collect_seconds=scenario.get("collect_seconds", .5))
                requests.future = replies.future = future
                self.submissions.append((trial, objective, requests, replies, function))
                return future
            return SimpleNamespace(remote=submit)
        return decorate

    def wait(self, futures, timeout=None):
        assert timeout == 0 and len(futures) == 1
        future = futures[0]
        return ([], futures) if future.reports or self.clock < future.ready_at else (futures, [])

    def get(self, future, timeout=None):
        self.clock += future.collect_seconds
        future.terminal = True
        if isinstance(future.outcome, BaseException):
            raise future.outcome
        return future.outcome

    def cancel(self, future, force=False):
        self.cancelled.append((future, force))


def installed(monkeypatch, **kwargs):
    fake = ScriptedRay(**kwargs)
    monkeypatch.setitem(sys.modules, "ray", fake)
    monkeypatch.setitem(sys.modules, "ray.util.queue", SimpleNamespace(Queue=fake.queue, Empty=Empty))
    monkeypatch.setattr(implementation, "time", SimpleNamespace(monotonic=lambda: fake.clock))
    return fake


def payload(status="completed", value=9., cost=2.):
    return {"objective_value": value, "cost": cost, "fidelity": 4., "status": status,
            "metadata": {"user": "retained"}}


def trial():
    return Trial(Config({"x": 3}), "trial", fidelity=4., seed=17,
                 continuation="resume", resume_from=2.)


@pytest.mark.parametrize("failure", [RayError("worker died"), GetTimeoutError("deadline")])
def test_streaming_retry_retains_resource_policy_progress_identity_and_all_failed_costs(failure):
    progress = ProgressReport("trial", "trial", 3., 5., 4., .25)
    with pytest.MonkeyPatch.context() as monkeypatch:
        fake = installed(monkeypatch, scenarios=[
            {"reports": [progress], "outcome": failure},
            {"reports": [progress], "outcome": payload()},
        ])
        target = implementation.RayExecutor(num_workers=1, max_retries=1,
            resources_per_trial={"num_cpus": 2, "num_gpus": .25, "max_retries": 9})
        observations = []
        decision = ReportDecision("continue", "accepted")

        def callback(report):
            observations.append(report)
            return decision

        objective = lambda config: config["x"]
        original = trial()
        result = target.execute(original, objective, on_report=callback)
        assert result.status == original.status == "completed"
        assert result.objective_value == 9. and result.cost == 6.
        assert result.trial_id == "trial" and result.fidelity == 4.
        assert result.metadata == {
            "user": "retained", "attempts": 2, "failed_attempt_elapsed_seconds": .75,
            "execution": {"schema_version": 1, "elapsed_seconds": 1.5,
                          "continuation": "resume", "resume_from": 2.},
        }
        assert [(r.cost, r.elapsed_seconds) for r in observations] == [(4., .25), (8., 1.)]
        assert all(r.trial_id == "trial" and r.root_trial_id == "trial" for r in observations)
        assert progress.cost == 4. and progress.elapsed_seconds == .25
        assert fake.options == [{"num_cpus": 2, "num_gpus": .25, "max_retries": 0,
                                 "retry_exceptions": False}] * 2
        assert len(fake.submissions) == 2 and not fake.scenarios
        assert all(args[0] is original and args[1] is objective for args in fake.submissions)
        assert fake.decisions == [decision, decision]
        assert fake.poll_intervals == [.02, .02]
        assert len(fake.channels) == 4 and all(c.closed for c in fake.channels)
        assert not fake.cancelled


@pytest.mark.parametrize("failure,status", [(RayError("worker died"), "failed"),
                                           (GetTimeoutError("deadline"), "timeout")])
@pytest.mark.parametrize("retries", [0, 2])
def test_streaming_failure_before_progress_accounts_for_elapsed_work_and_exact_attempts(failure, status, retries):
    with pytest.MonkeyPatch.context() as monkeypatch:
        fake = installed(monkeypatch, scenarios=[{"outcome": failure}] * (retries + 1))
        target = implementation.RayExecutor(num_workers=1, max_retries=retries)
        original = trial()
        result = target.execute(original, lambda _: 9, on_report=lambda _: ReportDecision())
        assert result.status == original.status == status
        assert math.isnan(result.objective_value)
        assert result.cost == .5 * (retries + 1)
        assert result.metadata == {"error": str(failure), "attempts": retries + 1,
            "failed_attempt_elapsed_seconds": .5 * (retries + 1),
            "execution": {"schema_version": 1, "elapsed_seconds": .5 * (retries + 1)}}
        assert result.trial_id == "trial" and result.fidelity == 4.
        assert len(fake.submissions) == retries + 1 and not fake.scenarios
        assert all(c.closed for c in fake.channels)


def test_completed_worker_is_collected_before_the_deadline_after_an_empty_poll():
    with pytest.MonkeyPatch.context() as monkeypatch:
        fake = installed(monkeypatch, scenarios=[
            {"outcome": payload(), "ready_at": .03, "collect_seconds": 0.},
        ])
        target = implementation.RayExecutor(num_workers=1, max_retries=0, timeout=.05)
        original = trial()
        result = target.execute(original, lambda _: 9, on_report=lambda _: ReportDecision())
        assert result.status == original.status == "completed"
        assert result.objective_value == 9. and result.cost == 2.
        assert result.metadata["execution"]["elapsed_seconds"] < .05
        assert fake.submissions[0][2].closed and fake.submissions[0][3].closed
        assert not fake.cancelled


@pytest.mark.parametrize("channel", [1, 2])
def test_partial_channel_startup_preserves_the_original_failure_and_cleans_owned_channels(channel):
    with pytest.MonkeyPatch.context() as monkeypatch:
        fake = installed(monkeypatch, fail_channel=channel)
        result = implementation.RayExecutor(num_workers=1, max_retries=0).execute(
            trial(), lambda _: 9, on_report=lambda _: ReportDecision())
        assert result.status == "failed"
        assert result.metadata["error"] == "channel startup failed"
        assert result.cost == 0 and result.metadata["attempts"] == 1
        assert not fake.submissions and not fake.cancelled
        assert len(fake.channels) == channel - 1 and all(c.closed for c in fake.channels)


def test_streaming_deadline_is_closed_and_never_polls_a_zero_remaining_interval():
    from tests.unit.test_ray_cancellation_boundary import install

    with pytest.MonkeyPatch.context() as monkeypatch:
        fake = install(monkeypatch)
        make_queue = fake.queue

        def queue(actor_options):
            channel = make_queue(actor_options)
            receive = channel.get

            def get(timeout):
                # Exact deterministic time reaches the deadline. The controller
                # must cancel there, rather than enter another polling call.
                assert timeout > 0, "polling continued at the closed deadline"
                return receive(timeout)

            channel.get = get
            return channel

        monkeypatch.setitem(sys.modules, "ray.util.queue", SimpleNamespace(Queue=queue,
                            Empty=sys.modules["ray.util.queue"].Empty))
        result = implementation.RayExecutor(num_workers=1, max_retries=0, timeout=.05).execute(
            trial(), lambda _: 9, on_report=lambda _: ReportDecision())
        assert result.status == "timeout" and result.cost == pytest.approx(.05)
        assert fake.clock == pytest.approx(.05)
        assert fake.cancel_requested and fake.terminal
