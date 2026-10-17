"""Public executor adapters must preserve work, elapsed cost and interruption."""

import json
import threading
from types import SimpleNamespace

import pytest

from hponas import LocalExecutor, RandomSearcher, Study
from hponas.capabilities import SearcherCapabilities
import hponas.study as study_module
from hponas.executors import reporting
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Result


def searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=11)


class BatchSequence(RandomSearcher):
    """A deterministic batch-interface fixture with observable proposals."""

    def __init__(self, limit=None):
        super().__init__(SearchSpace([Knob('x', 'ordinal', (0, 20))]), seed=11)
        self.support = SearcherCapabilities(('ordinal',), joint_batch=True, partial_fidelity=True)
        self.batch_requests = []
        self.proposed = 0
        if limit is not None:
            self.max_batch_size = limit

    def suggest(self):
        config = Config({'x': self.proposed})
        self.proposed += 1
        return config

    def suggest_batch(self, count):
        self.batch_requests.append(count)
        return [self.suggest() for _ in range(count)]


@pytest.mark.parametrize('limit,expected_batches', [(None, [4, 3]), (2, [2, 2, 2])])
def test_joint_dispatch_respects_remaining_configuration_budget_and_optional_batch_limit(
        tmp_path, limit, expected_batches):
    source = BatchSequence(limit)
    dispatched = []

    def objective(config, trial_id):
        dispatched.append((trial_id, config['x']))
        return (config['x'] - 2) ** 2

    study = Study(source, LocalExecutor(), objective, budget=7, max_concurrent=4,
                  maximize=False, study_name='bounded', checkpoint_dir=tmp_path)
    result = study.run()
    assert source.batch_requests == expected_batches
    assert source.proposed == result.n_trials == 7
    assert dispatched == [('bounded_trial_' + str(i), i) for i in range(7)]
    assert result.best_config.values == {'x': 2} and result.best_value == 0.
    checkpoint = json.loads((tmp_path / 'bounded_checkpoint.json').read_text())
    assert len(checkpoint['trials']) == len(checkpoint['results']) == 7
    assert checkpoint['pending'] == []


def test_joint_proposals_leave_room_for_queued_promotions():
    source = BatchSequence()
    scheduler = ASHAScheduler(ASHAConfig(eta=3, r_min=1, r_max=3))
    dispatched = []

    def objective(config, trial_id, fidelity):
        dispatched.append((trial_id, fidelity))
        return float(config['x'])

    result = Study(source, LocalExecutor(), objective, budget=8, max_concurrent=3,
                   scheduler=scheduler, maximize=False, study_name='promoted').run()
    # After three roots, ASHA promotes one; only two slots remain for new roots.
    assert source.batch_requests[:2] == [3, 2]
    assert source.proposed == 8
    assert ('promoted_trial_0_fidelity_3', 3.) in dispatched
    assert result.best_config.values == {'x': 0}


def test_legacy_duck_searcher_without_capabilities_keeps_scalar_dispatch():
    class LegacyDuck:
        def __init__(self):
            self.search_space = SearchSpace([Knob('x', 'ordinal', (0, 3))])
            self.seed = 1
            self.trials = {}
            self.history = []

        def suggest(self):
            return Config({'x': len(self.trials)})

        def observe(self, result):
            self.history.append(result)

        def get_state(self):
            return {'seed': self.seed, 'history': [r.to_dict() for r in self.history],
                    'trials': {tid: config.to_dict() for tid, config in self.trials.items()}}

    source = LegacyDuck()
    result = Study(source, LocalExecutor(), lambda c: c['x'], budget=3,
                   max_concurrent=2, maximize=False).run()
    assert result.evaluation['status'] == 'legacy_unqualified'
    assert result.n_trials == 3 and result.best_value == 0.
    assert [r.objective_value for r in source.history] == [0., 1., 2.]


def test_single_evaluation_adapter_measures_elapsed_time_without_overwriting_reported_cost(monkeypatch):
    tick = [100.]
    monkeypatch.setattr(study_module, "time", SimpleNamespace(monotonic=lambda: tick[0]))

    class Executor:
        def __init__(self):
            self.calls, self.closed = [], False

        def execute(self, trial, objective_fn, on_report):
            self.calls.append(trial.trial_id)
            tick[0] += 3.
            return Result(trial.trial_id, objective_fn(trial.config.values), 7., trial.fidelity)

        def shutdown(self):
            self.closed = True

    executor = Executor()
    study = Study(searcher(), executor, lambda config: 5., budget=2, max_concurrent=2,
                  study_name="adapter", compute_budget_seconds=20.)
    result = study.run()
    assert executor.closed and executor.calls == ["adapter_trial_0", "adapter_trial_1"]
    assert result.total_elapsed_seconds == 6. and result.total_cost == 14.
    assert [row.metadata for row in result.history] == [
        {"execution": {"elapsed_seconds": 3.}}, {"execution": {"elapsed_seconds": 3.}}]


def test_batch_executor_prepares_once_per_dispatch_and_keeps_return_order():
    class Executor:
        def __init__(self):
            self.calls = []

        def prepare(self):
            self.calls.append("prepare")

        def execute_batch(self, trials, objective_fn, on_report):
            self.calls.append(tuple(t.trial_id for t in trials))
            return [Result(t.trial_id, objective_fn(t.config.values), 2., t.fidelity,
                           {"execution": {"elapsed_seconds": 3.}}) for t in trials]

        def execute(self, *args, **kwargs):
            pytest.fail("Declared batch interface was bypassed")

        def shutdown(self):
            self.calls.append("shutdown")

    executor = Executor()
    study = Study(searcher(), executor, lambda config: 5., budget=3, max_concurrent=2,
                  study_name="batch", compute_budget_seconds=20.)
    result = study.run()
    assert executor.calls == ["prepare", ("batch_trial_0", "batch_trial_1"),
                              "prepare", ("batch_trial_2",), "shutdown"]
    assert [row.trial_id for row in result.history] == ["batch_trial_0", "batch_trial_1", "batch_trial_2"]
    assert result.total_cost == 6. and result.total_elapsed_seconds == 9.


def test_repeated_recovery_charges_each_acknowledged_attempt_once(tmp_path, monkeypatch):
    tick = [0.]
    monkeypatch.setattr(reporting, "time", SimpleNamespace(monotonic=lambda: tick[0]))

    def interrupted(config, reporter):
        tick[0] = reporter.started + 2.
        reporter(1., 5., cost=3.)
        raise KeyboardInterrupt("restart after progress")

    path = tmp_path / "repeated_checkpoint.json"
    for attempt in range(2):
        study = Study(searcher(), LocalExecutor(), interrupted, budget=1,
                      study_name="repeated", checkpoint_dir=tmp_path)
        if attempt:
            study.load_checkpoint(path)
        with pytest.raises(KeyboardInterrupt, match="restart after progress"):
            study.run()

    def complete(config, reporter):
        tick[0] = reporter.started + 2.
        reporter(1., 5., cost=3.)
        assert restored.resource_report()['tuning_elapsed_seconds'] == 6.
        return {"value": 5., "cost": 3.}

    restored = Study(searcher(), LocalExecutor(), complete, checkpoint_dir=tmp_path)
    restored.load_checkpoint(path)
    result = restored.run()
    assert result.n_trials == 1 and result.total_cost == 9.
    assert result.total_elapsed_seconds == 6.
    assert result.history[0].metadata["execution"]["accounting"] == "lower_bound_after_interruption"
    state = json.loads(path.read_text())
    for name in ("live_elapsed", "live_cost", "abandoned_elapsed", "abandoned_cost"):
        assert state[name] == {}


def test_checkpoint_interruption_releases_other_reporting_worker_with_cancellation(tmp_path, monkeypatch):
    interrupted = threading.Event()
    tails = []
    original_write = study_module.atomic_json

    def interrupt_write(path, state):
        if state["results"] and not interrupted.is_set():
            interrupted.set()
            raise KeyboardInterrupt("checkpoint interrupted")
        return original_write(path, state)

    monkeypatch.setattr(study_module, "atomic_json", interrupt_write)

    class CapturingExecutor(LocalExecutor):
        def __init__(self):
            super().__init__(mode="async", max_workers=2)
            self.dispatched = []

        def execute_async(self, *args, **kwargs):
            future = super().execute_async(*args, **kwargs)
            self.dispatched.append(future)
            return future

    def objective(config, trial_id, reporter):
        if trial_id.endswith("_1"):
            assert interrupted.wait(3.), "First result did not reach the checkpoint boundary"
        reporter(1., 5., cost=2.)
        tails.append(trial_id)
        return {"value": 5., "cost": 2.}

    executor = CapturingExecutor()
    study = Study(searcher(), executor, objective, budget=2, max_concurrent=2,
                  study_name="drain", checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt, match="checkpoint interrupted"):
        study.run()
    assert len(executor.dispatched) == 2 and all(future.done() for future in executor.dispatched)
    remaining = executor.dispatched[1].result()
    assert remaining.status == "cancelled"
    assert remaining.metadata["stop_reason"] == "study_interrupted"
    assert tails == ["drain_trial_0"]


def test_exact_time_cap_stops_new_proposals_and_preserves_public_resource_report(monkeypatch):
    tick = [100.]
    monkeypatch.setattr(study_module, 'time', SimpleNamespace(monotonic=lambda: tick[0]))
    calls = []

    class Clocked:
        def execute(self, trial, objective_fn, on_report):
            calls.append(trial.trial_id)
            tick[0] += 3.
            return Result(trial.trial_id, 5., 7., trial.fidelity)

        def shutdown(self):
            pass

    source = Study(searcher(), Clocked(), lambda config: 5., budget=4,
                   study_name='cap', compute_budget_seconds=3.)
    result = source.run()
    assert calls == ['cap_trial_0'] and result.n_trials == 1
    assert result.reason == 'compute_budget_exhausted'
    assert result.total_cost == 7. and result.total_elapsed_seconds == 3.
    report = result.resources
    assert report['mode'] == 'legacy_controls'
    assert report['configuration_limit'] == 4
    assert report['configurations_proposed'] == report['tuning_evaluations'] == 1
    assert report['tuning_elapsed_seconds'] == report['tuning_seconds_limit'] == 3.
    assert report['work_unit'] is None and report['full_run_equivalents'] is None
    assert report['final_work_reserved'] is False
    assert report['admission']['status'] == 'admitted'
    assert source.resource_report() == report


def test_seed_zero_dispatch_preserves_assigned_trial_seeds():
    source = RandomSearcher(SearchSpace([Knob('x', 'ordinal', (0, 3))]), seed=0)
    seeds = []

    def objective(config, seed):
        seeds.append(seed)
        return 1.

    result = Study(source, LocalExecutor(), objective, budget=3).run()
    assert result.n_trials == 3 and seeds == [0, 1, 2]
