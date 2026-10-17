"""Independent Optuna parity and recovery for the optional CMA-ES wrapper."""

import copy
import json
import math

import pytest

pytest.importorskip("cmaes", reason="Install hponas[cmaes] for optional wrapper conformance")
import optuna

from hponas import CMAESSearcher, Config, Knob, Result, SearchSpace, Study, LocalExecutor


def space():
    return SearchSpace([
        Knob("rate", "continuous", (1e-5, 1e-1), transform="log"),
        Knob("width", "continuous", (-3., 5.)),
    ])


@pytest.mark.parametrize("maximize", [True, False])
@pytest.mark.parametrize("batch", [1, 4])
def test_real_vendor_parity_across_generations_failures_and_pending_recovery(maximize, batch):
    target = CMAESSearcher(space(), seed=23, maximize=maximize)
    vendor = optuna.create_study(direction="minimize", sampler=optuna.samplers.CmaEsSampler(seed=23))
    for offset in range(0, 40, batch):
        pending = []
        for i in range(offset, offset + batch):
            config = target.suggest()
            trial = vendor.ask()
            u = trial.suggest_float("rate", 0., 1.)
            v = trial.suggest_float("width", 0., 1.)
            expected = {"rate": math.exp(math.log(1e-5) + u * (math.log(1e-1) - math.log(1e-5))), "width": -3 + 8 * v}
            assert config.values == pytest.approx(expected, rel=1e-13, abs=1e-15)
            target.trials[str(i)] = config
            pending.append((i, config, trial))
        saved = json.loads(json.dumps(target.get_state()))
        target = CMAESSearcher(space(), seed=99)
        target.set_state(saved)
        assert target.get_state() == saved
        # Result arrival can differ from suggestion order without changing asks.
        for i, config, trial in reversed(pending):
            value = (math.log10(config["rate"]) + 3) ** 2 + config["width"] ** 2
            failed = i in (4, 17)
            target.observe(Result(str(i), value, status="failed" if failed else "completed"))
            vendor.tell(trial, None if failed else -value if maximize else value,
                        state=optuna.trial.TrialState.FAIL if failed else optuna.trial.TrialState.COMPLETE)
    assert not target._pending
    assert len(target.history) == 40
    assert target._study.sampler.__class__ is optuna.samplers.CmaEsSampler


def test_study_selects_direction_and_checkpoint_restores_pending(tmp_path):
    study = Study(CMAESSearcher(space(), seed=1), LocalExecutor(),
                  lambda c: c["width"] ** 2, budget=12, maximize=False,
                  checkpoint_dir=tmp_path, study_name="cma")
    result = study.run()
    assert result.n_trials == 12
    assert result.best_value == min(r.objective_value for r in result.history)
    assert [t.value for t in study.searcher._study.trials] == [r.objective_value for r in result.history]


def test_rejected_recovery_keeps_live_searcher_unchanged():
    target = CMAESSearcher(space())
    target.suggest()
    original = target.get_state()
    for field, value in [("versions", {}), ("space", {}), ("kind", "other")]:
        corrupted = copy.deepcopy(original)
        corrupted[field] = value
        with pytest.raises(ValueError):
            target.set_state(corrupted)
        assert target.get_state() == original
    corrupted = copy.deepcopy(original)
    corrupted["events"][0]["config"]["rate"] = 0.01
    with pytest.raises(ValueError, match="exactly"):
        target.set_state(corrupted)
    assert target.get_state() == original


def test_duplicate_unknown_results_direction_and_deep_checkpoint():
    target = CMAESSearcher(space())
    config = target.suggest()
    with pytest.raises(ValueError, match="registered"):
        target.observe(Result("unknown", 1.))
    target.trials["a"] = config
    target.observe(Result("a", 1.))
    with pytest.raises(ValueError, match="revise"):
        target.observe(Result("a", 2.))
    target.trials["orphan"] = Config({"rate": 0.01, "width": 1.})
    with pytest.raises(ValueError, match="pending"):
        target.observe(Result("orphan", 2.))
    state = target.get_state()
    state["events"][0]["config"]["rate"] = -1
    assert target.get_state()["events"][0]["config"]["rate"] > 0
    target.maximize = False
    with pytest.raises(ValueError, match="direction"):
        target.suggest()


@pytest.mark.parametrize("knob_specs", [
    [], [{"name": "x", "kind": "ordinal", "bounds": (1, 4)}],
    [{"name": "x", "kind": "categorical", "bounds": ["a", "b"]}],
    [{"name": "x", "kind": "continuous", "bounds": (0., 1.)},
     {"name": "y", "kind": "continuous", "bounds": (0., 1.), "condition": ("x", .5)}],
], ids=["knobs0", "knobs1", "knobs2", "knobs3"])
def test_unsupported_spaces_fail_explicitly(knob_specs):
    knobs = [Knob(**spec) for spec in knob_specs]
    with pytest.raises(ValueError, match="unconditional continuous"):
        CMAESSearcher(SearchSpace(knobs))


@pytest.mark.parametrize("seed", [True, -1, 2**32, 0.5, None])
def test_invalid_seed_is_rejected(seed):
    with pytest.raises(ValueError, match="seed"):
        CMAESSearcher(space(), seed=seed)
