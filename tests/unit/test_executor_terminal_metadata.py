"""Execution provenance must survive endpoint worker failure and deadlines."""

import pytest

from hponas import LocalExecutor
from hponas.types import Result
from tests.unit.test_executor_evaluation_contract import (
    Channel, Worker, install_worker, make_trial,
)


@pytest.mark.parametrize('outcome', ['completed', 'eof', 'deadline'])
@pytest.mark.parametrize('continuation', ['restart', 'resume'])
def test_endpoint_terminal_record_identifies_execution_boundary(monkeypatch, outcome, continuation):
    trial = make_trial()
    trial.continuation = continuation
    trial.resume_from = 2. if continuation == 'resume' else 0.
    trial.checkpoint = {'step': 2} if continuation == 'resume' else None
    worker_result = Result(trial.trial_id, 7., cost=3., fidelity=trial.fidelity,
                           metadata={'artifact': 'endpoint.json'})
    channel = Channel(EOFError() if outcome == 'eof' else worker_result,
                      ready=outcome != 'deadline')
    worker = Worker(alive=outcome == 'deadline')
    install_worker(monkeypatch, channel, worker)
    executor = LocalExecutor(timeout=2.)
    try:
        result = executor.execute(trial, lambda config: 7.)
    finally:
        executor.shutdown()
    assert result.status == trial.status == {
        'completed': 'completed', 'eof': 'failed', 'deadline': 'timeout',
    }[outcome]
    expected = {
        'schema_version': 1,
        'elapsed_seconds': 0.,
        'duration_scope': 'worker_including_startup',
        'accounting': 'measured',
        'continuation': continuation,
        'resume_from': 2. if continuation == 'resume' else 0.,
    }
    if outcome == 'deadline':
        expected.update(censor_cause='external_deadline', deadline_seconds=2.)
    assert result.metadata['execution'] == expected
    assert channel.closed and worker.started
    if outcome == 'completed':
        assert result.objective_value == 7. and result.cost == 3.
        assert result.metadata['artifact'] == 'endpoint.json'
