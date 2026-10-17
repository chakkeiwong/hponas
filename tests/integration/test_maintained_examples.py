"""Maintained examples use the public API and preserve existing user artifacts."""

import json

from examples.spike_branin import _run_study
from examples.spike_crash_recovery import run_demo


def test_branin_example_uses_promotions_and_preserves_prior_run(tmp_path):
    marker = tmp_path / "existing.txt"
    marker.write_text("keep")
    result, first = _run_study("local", 42, 8, tmp_path)
    _, second = _run_study("local", 42, 8, tmp_path)
    assert first == second
    assert {r.fidelity for r in result.history} == {1., 2., 4.}
    assert result.best_value == min(r.objective_value for r in result.history if r.fidelity == 4)
    assert len(list(tmp_path.glob("branin-local-*/study.db"))) == 2
    assert marker.read_text() == "keep"


def test_recovery_example_preserves_committed_prefix_and_full_trace(tmp_path):
    marker = tmp_path / "existing.txt"
    marker.write_text("keep")
    receipt = run_demo(tmp_path, crash_after=3, n_trials=8)
    assert receipt["committed_preserved"] == 3
    assert receipt["trials"] == 8
    assert receipt["exact_reference_trace"]
    assert not receipt["scientific_acceptance"]
    assert marker.read_text() == "keep"


def test_ppo_example_never_labels_integration_as_acceptance(tmp_path, monkeypatch):
    import examples.v14_day_one_walk as example

    monkeypatch.setattr(example, "campaign", lambda directory: {"trials": [{"training_seed": 42}]})
    result = example.run_day_one_walk(tmp_path)
    assert result["scientific_acceptance"] is False
    assert "verdict" not in result and "passed" not in result
    saved = list(tmp_path.glob("hponas-ppo-example-*/example-result.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text()) == result
