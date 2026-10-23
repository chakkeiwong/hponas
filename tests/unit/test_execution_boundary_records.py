"""Cheap public checks of durable metadata, diagnostics and extension boundaries."""

from types import SimpleNamespace

import pytest

from hponas import LocalExecutor, Study
from hponas.events import EventLog, EventType
from hponas.executors.reporting import ReportDecision
from hponas.schedulers import (
    ASHAConfig, ASHAScheduler, BudgetedASHAConfig, BudgetedASHAScheduler,
    MOASHAConfig, MOASHAScheduler, PASHAConfig, PASHAScheduler,
)
from hponas.searchers.base import SearchSpaceExhaustedError
from tests.unit.test_executor_evaluation_contract import (
    Channel, Worker, install_worker, make_trial,
)
from tests.unit.test_study_checkpoint_additional import make_study, write_state
from tests.unit.test_study_public_entrypoints import searcher


def test_event_log_creates_nested_parents_and_reopens_the_durable_record(tmp_path):
    path = tmp_path / 'new' / 'nested' / 'events.jsonl'
    log = EventLog(path)
    event = log.record_observe('trial', fidelity=1., value=2., cost=3.)
    assert EventLog(path).get_events() == [event]


def test_deadline_result_records_the_censoring_boundary(monkeypatch):
    receive, worker = Channel(ready=False), Worker(alive=True)
    install_worker(monkeypatch, receive, worker)
    executor = LocalExecutor(timeout=2.)
    result = executor.execute(make_trial(), lambda config: 1.)
    assert result.status == 'timeout'
    assert result.metadata['execution']['censor_cause'] == 'external_deadline'
    assert result.metadata['execution']['deadline_seconds'] == 2.
    assert worker.terminated and receive.closed
    executor.shutdown()


@pytest.mark.parametrize('action', ['invalid', '', None])
def test_unknown_reporting_action_has_an_explanatory_refusal(action):
    with pytest.raises(ValueError) as caught:
        ReportDecision(action)
    assert str(caught.value) == 'Unknown reporting decision'


@pytest.mark.parametrize('count', [True, False, 1.5, 0, -1])
def test_median_reference_count_must_be_a_positive_integer(count):
    with pytest.raises(ValueError) as caught:
        ASHAConfig(median_min_completed=count)
    assert str(caught.value) == 'median_min_completed must be a positive integer'


@pytest.mark.parametrize('grid', [(1., 1.), (2., 1.)])
def test_duplicate_and_out_of_order_median_grid_points_have_precise_refusals(grid):
    with pytest.raises(ValueError) as caught:
        ASHAConfig(r_max=4., report_grid=grid)
    assert str(caught.value) == 'report_grid must be strictly increasing'


@pytest.mark.parametrize('scheduler,config,options', [
    (ASHAScheduler, ASHAConfig, {}),
    (BudgetedASHAScheduler, BudgetedASHAConfig, {}),
    (PASHAScheduler, PASHAConfig, {}),
    (MOASHAScheduler, MOASHAConfig, {'objectives': ['loss', 'work']}),
])
def test_unrepresentable_rung_progress_is_refused_without_looping(scheduler, config, options):
    class ObservedFactor(float):
        calls = 0

        def __rmul__(self, value):
            self.calls += 1
            assert self.calls == 1, 'Scheduler retried a non-progressing rung'
            return value * float(self)

    # IEEE-754 rounds this product back to the smallest positive subnormal.
    # Keep the real arithmetic, but fail deterministically on a repeated step
    # so a missing progress check cannot grow an unbounded rung list.
    assert 5e-324 * 1.1 == 5e-324
    factor = ObservedFactor(1.1)
    with pytest.raises(ValueError) as caught:
        scheduler(config(eta=factor, r_min=5e-324, r_max=2e-323, **options))
    assert str(caught.value) == 'Rung budgets must strictly increase at float precision'
    assert factor.calls == 1


@pytest.mark.parametrize('metadata', [{}, {'execution': {}}])
def test_resumed_optional_elapsed_metadata_defaults_to_zero(tmp_path, metadata):
    source = make_study(budget=1)
    source.run()
    state = source._snapshot()
    for row in state['results'].values():
        row['metadata'] = metadata
    target = make_study(budget=1)
    target.load_checkpoint(write_state(tmp_path, state))
    result = target.run()
    assert result.n_trials == 1 and result.total_elapsed_seconds == 0.


def test_finite_exhaustion_has_a_versioned_durable_event(tmp_path):
    class FiniteSearcher(type(searcher())):
        calls = 0

        def suggest(self):
            self.calls += 1
            assert self.calls <= 2, 'Study retried a terminal finite-space refusal'
            if self.trials:
                raise SearchSpaceExhaustedError('finite space exhausted')
            return super().suggest()

    original = searcher()
    finite = FiniteSearcher(original.search_space, seed=7)
    log = EventLog(tmp_path / 'exhausted.jsonl')
    result = Study(finite, LocalExecutor(), lambda config: 2., budget=2,
                   study_name='finite', event_log=log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert result.n_trials == 1 and result.reason == 'search_space_exhausted'
    events = [row for row in log.get_events() if row.event_type == EventType.SEARCH_EXHAUSTED]
    assert len(events) == 1 and events[0].data == {'schema_version': 1}


def test_scheduler_extension_with_finish_does_not_need_a_promotion_policy_field():
    class Scheduler:
        config = SimpleNamespace(r_min=1., r_max=1.)

        def __init__(self):
            self._terminal = {}

        def register_trial(self, trial_id):
            return 1.

        def promote(self):
            return []

        def report(self, trial_id, fidelity, value, **kwargs):
            return 'stop'

        def finish(self, trial_id, status):
            self._terminal[trial_id] = status

        def state_dict(self):
            return {'terminal': dict(self._terminal)}

        def load_state_dict(self, state):
            self._terminal = dict(state['terminal'])

    scheduler = Scheduler()
    result = Study(searcher(), LocalExecutor(), lambda config: 2., budget=1,
                   study_name='extension', scheduler=scheduler, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert result.status == 'completed'
    assert scheduler._terminal == {'extension_trial_0': 'completed'}
