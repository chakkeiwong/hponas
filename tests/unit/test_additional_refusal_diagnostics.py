"""Prospective diagnostics on existing documented helper/refusal interfaces."""

import pytest

from hponas import GPSearcher, Knob, Result, SearchSpace
from hponas.executors.local_executor import LocalExecutor
from tests.unit.test_executor_evaluation_contract import Channel, Worker, install_worker, make_trial


@pytest.mark.parametrize("case,message", [
    ("empty", "Cannot prepare training data from empty results list"),
    ("invalid", "All results must be valid for GP training"),
    ("unregistered", "No valid training data found"),
])
def test_training_data_refusal_diagnostics(case, message):
    target = GPSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]))
    results = [] if case == "empty" else [Result("unregistered", 1., status="failed" if case == "invalid" else "completed")]
    with pytest.raises(ValueError) as error:
        target._prepare_training_data(results)
    assert str(error.value) == message


def test_local_worker_eof_retains_precise_failure_diagnostic():
    with pytest.MonkeyPatch.context() as monkeypatch:
        receive, worker = Channel(EOFError()), Worker()
        install_worker(monkeypatch, receive, worker)
        result = LocalExecutor(timeout=2.).execute(make_trial(), lambda c: 1.)
    assert result.status == "failed"
    assert result.metadata["error"] == "Objective worker exited without a result"
    assert receive.closed
