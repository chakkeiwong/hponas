"""Real GP/qLogEI execution resumes across the random-to-model transition."""

import pytest

from hponas import GPSearcher, Knob, LocalExecutor, SearchSpace, Study


@pytest.mark.parametrize("maximize", [True, False])
def test_fitted_gp_trace_matches_uninterrupted_study_after_crash(tmp_path, maximize):
    space = SearchSpace([Knob("rate", "continuous", (1e-4, 1e-1), transform="log")])
    calls = []

    def objective(config, trial_id):
        calls.append(trial_id)
        if len(calls) == 4:
            raise KeyboardInterrupt("simulated interruption at first fitted-GP trial")
        return (config["rate"] - .01)**2

    def plain(config):
        return (config["rate"] - .01)**2

    interrupted = Study(GPSearcher(space, seed=12, initial_random_samples=3, num_restarts=2),
                        LocalExecutor(), objective, budget=6, maximize=maximize,
                        study_name="gp", checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    with pytest.raises(KeyboardInterrupt):
        interrupted.run()
    resumed = Study(GPSearcher(space, seed=999), LocalExecutor(), plain,
                    study_name="restored", checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    resumed.load_checkpoint(tmp_path / "gp_checkpoint.json")
    actual = resumed.run()
    baseline = Study(GPSearcher(space, seed=12, initial_random_samples=3, num_restarts=2),
                     LocalExecutor(), plain, budget=6, maximize=maximize, study_name="gp", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    expected = baseline.run()
    assert [r.objective_value for r in actual.history] == [r.objective_value for r in expected.history]
    assert [t.config.values for t in resumed.trials.values()] == [t.config.values for t in baseline.trials.values()]
    assert actual.best_config == expected.best_config
    assert actual.best_value == expected.best_value
    assert actual.n_trials == 6
