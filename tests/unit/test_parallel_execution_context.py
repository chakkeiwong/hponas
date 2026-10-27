"""Resource dispatch contracts without a cluster or physical GPU allocation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from queue import Queue, Empty
from types import SimpleNamespace
import sys

import pytest

from hponas import ResourceSpec
from hponas.evaluation import EvaluationContext, _RoleObjective
from hponas.evaluation_streaming import _StreamingRoleObjective
from hponas.executors.base import evaluate_trial
from hponas.executors.ray_executor import RayExecutor
from hponas.executors.resources import ExecutionContext
from hponas.executors.reporting import ReportDecision
from hponas.types import Config, Trial
from tests.integration.test_declared_evaluation import declaration


@pytest.fixture
def execution_context():
    return ExecutionContext('worker-a', 'attempt-a', 'trial-a', (0,), (), 1, 'cpu')


def trial():
    return Trial(Config({'x': 3}), 'trial-a', fidelity=.5, seed=17)


@pytest.mark.parametrize('declared', [False, True])
@pytest.mark.parametrize('streaming', [False, True])
def test_execution_context_identity_survives_worker_and_declared_wrappers(declared, streaming, execution_context):
    seen, reports = [], []
    contract = declaration()
    evaluation = EvaluationContext('tuning', contract.tuning_folds[0], contract.identity)
    def endpoint(config, execution, evaluation=None):
        seen.append((config, execution, evaluation))
        return {'value': 9., 'cost': 2.}
    def stream(config, execution, reporter, evaluation=None):
        seen.append((config, execution, evaluation))
        reporter(.5, 9., cost=2.)
        return {'value': 9., 'cost': 2.}
    objective = stream if streaming else endpoint
    if declared:
        objective = (_StreamingRoleObjective if streaming else _RoleObjective)(objective, evaluation)
    result = evaluate_trial(trial(), objective,
        lambda progress: reports.append(progress) or ReportDecision(), execution_context=execution_context)
    assert result.status == 'completed' and result.objective_value == 9. and result.cost == 2.
    assert len(seen) == 1 and seen[0][0] == {'x': 3} and seen[0][1] is execution_context
    assert seen[0][2] is (evaluation if declared else None)
    assert len(reports) == int(streaming)
    assert result.metadata['execution']['mode'] == ('streaming' if streaming else 'endpoint')


class RayError(Exception):
    pass


class GetTimeoutError(RayError):
    pass


class LocalTransport:
    """Execute actual remote closures; replace only transport and assignment."""
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.options, self.channels, self.cancelled = [], [], []
        self.exceptions = SimpleNamespace(RayError=RayError, GetTimeoutError=GetTimeoutError)

    def is_initialized(self):
        return True

    def cluster_resources(self):
        return {'CPU': 2., 'GPU': 0.}

    def remote(self, **options):
        self.options.append(options)
        return lambda fn: SimpleNamespace(remote=lambda *args: self.pool.submit(fn, *args))

    def wait(self, futures, timeout=0):
        assert timeout == 0
        return ([f for f in futures if f.done()], [f for f in futures if not f.done()])

    def get(self, future, timeout=None):
        return future.result(timeout=timeout)

    def cancel(self, future, force=False):
        self.cancelled.append((future, force))
        future.cancel()

    def queue(self, actor_options):
        assert actor_options == {'num_cpus': 0}
        class Channel(Queue):
            closed = False
            def shutdown(self, force=False):
                assert force is True
                self.closed = True
        channel = Channel()
        self.channels.append(channel)
        return channel


@pytest.mark.parametrize('mode', ['endpoint', 'streaming', 'stop'])
def test_ray_resource_dispatch_executes_real_worker_wrapper_and_reporting(monkeypatch, mode, execution_context):
    from hponas.executors import ray_resources
    transport = LocalTransport()
    monkeypatch.setitem(sys.modules, 'ray', transport)
    monkeypatch.setitem(sys.modules, 'ray.util.queue', SimpleNamespace(Queue=transport.queue, Empty=Empty))
    spec = ResourceSpec()
    assignments, seen, reports = [], [], []
    @contextmanager
    def assigned(task_id, resources):
        assignments.append((task_id, resources))
        assert task_id == 'trial-a' and resources is spec
        yield execution_context
    monkeypatch.setattr(ray_resources, 'assigned_context', assigned)
    def endpoint(config, execution):
        seen.append(execution)
        return {'value': 9., 'cost': 2.}
    def stream(config, execution, reporter):
        seen.append(execution)
        reporter(.25, 4., cost=1.)
        reporter(.5, 9., cost=2.)
        return {'value': 9., 'cost': 2.}
    def report(progress):
        reports.append(progress)
        return ReportDecision('stop', 'bounded stop') if mode == 'stop' else ReportDecision()
    executor = RayExecutor(1, max_retries=0, resources=spec, timeout=5.)
    try:
        result = executor.execute(trial(), endpoint if mode == 'endpoint' else stream,
                                  on_report=None if mode == 'endpoint' else report)
    finally:
        executor.shutdown()
        transport.pool.shutdown(wait=True)
    assert assignments == [('trial-a', spec)]
    assert len(seen) == 1 and seen[0] is execution_context
    assert result.trial_id == 'trial-a' and result.fidelity == .5
    assert result.status == ('pruned' if mode == 'stop' else 'completed')
    assert result.objective_value == (4. if mode == 'stop' else 9.)
    assert result.cost == (1. if mode == 'stop' else 2.)
    assert result.metadata['execution']['worker'] == execution_context.to_dict()
    assert result.metadata['execution']['cpu_placement'] == 'ray_logical_reservation_not_exclusive_affinity'
    assert transport.options == [{'num_cpus': 1, 'num_gpus': 0, 'max_retries': 0, 'retry_exceptions': False}]
    assert len(reports) == {'endpoint': 0, 'streaming': 2, 'stop': 1}[mode]
    assert [p.step for p in reports] == ([] if mode == 'endpoint' else [.25] if mode == 'stop' else [.25, .5])
    assert len(transport.channels) == (0 if mode == 'endpoint' else 2)
    assert all(c.closed for c in transport.channels) and not transport.cancelled
