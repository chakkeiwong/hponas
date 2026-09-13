"""
Contract tests: verify all components implement their protocol contracts.

Validation coverage:
- V01 foundation: contract conformance before implementation parity
- V02 foundation: scheduler protocol before async property tests
- V14 foundation: end-to-end contract before reproduction check

Test categories:
1. Searcher protocol: propose/observe/state_dict/capabilities
2. Scheduler protocol: report/promote interface
3. Executor protocol: launch/checkpoint/load_checkpoint
4. Store protocol: write/read/lineage queries
5. SearchSpace protocol: knob validation, conditional structure
"""

import pytest
import tempfile
from pathlib import Path

from hponas.types import SearchSpace, Parameter, ParameterType
from hponas.searchers import SobolSearcher, RandomSearcher


def test_searcher_protocol_sobol():
    """SobolSearcher implements Searcher protocol."""
    space = SearchSpace(parameters={
        "x": Parameter(
            name="x",
            type=ParameterType.CONTINUOUS,
            bounds=(0, 1)
        )
    })

    searcher = SobolSearcher(space, seed=42)

    # suggest() returns Config
    configs = []
    for _ in range(5):
        config = searcher.suggest()
        configs.append(config.values)

    assert len(configs) == 5
    assert all(isinstance(c, dict) for c in configs)
    assert all("x" in c for c in configs)

    # state_dict() returns serializable state
    state = searcher.state_dict()
    assert isinstance(state, dict)
    assert "seed" in state

    # load_state_dict() restores state
    searcher2 = SobolSearcher(space, seed=999)
    searcher2.load_state_dict(state)

    # capabilities declares support
    caps = searcher.capabilities
    assert isinstance(caps, dict)
    assert "parameter_types" in caps
    assert "continuous" in caps["parameter_types"]


def test_searcher_protocol_random():
    """RandomSearcher implements Searcher protocol."""
    space = SearchSpace(parameters={
        "lr": Parameter(
            name="lr",
            type=ParameterType.CONTINUOUS,
            bounds=(1e-5, 1e-2),
            log_scale=True
        ),
        "n": Parameter(
            name="n",
            type=ParameterType.INTEGER,
            bounds=(1, 10)
        ),
        "opt": Parameter(
            name="opt",
            type=ParameterType.CATEGORICAL,
            choices=["sgd", "adam"]
        )
    })

    searcher = RandomSearcher(space, seed=42)

    # Protocol conformance
    configs = [searcher.suggest().values for _ in range(3)]
    assert len(configs) == 3

    state = searcher.state_dict()
    assert "seed" in state

    caps = searcher.capabilities
    assert "continuous" in caps["parameter_types"]
    assert "integer" in caps["parameter_types"]
    assert "categorical" in caps["parameter_types"]


def test_scheduler_protocol_asha():
    """ASHAScheduler implements Scheduler protocol."""
    config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
    scheduler = ASHAScheduler(config)

    # report() returns decision
    decision = scheduler.report("trial_0", fidelity=1.0, value=0.5)
    assert decision in ["continue", "stop", "pause"]

    # promote() returns list of (trial_id, next_fidelity)
    scheduler.report("trial_1", fidelity=1.0, value=0.3)
    promotions = scheduler.promote()
    assert isinstance(promotions, list)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in promotions)


def test_executor_protocol_local():
    """LocalExecutor implements Executor protocol."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = LocalExecutor(checkpoint_dir=tmpdir)

        # launch() returns trial_id
        def dummy_objective(config):
            return config["x"] ** 2

        trial_id = executor.launch(
            trial_id="test_trial",
            config={"x": 0.5},
            objective_fn=dummy_objective,
            fidelity=1.0
        )
        assert trial_id == "test_trial"

        # get_result() returns trial result
        result = executor.get_result(trial_id)
        assert "value" in result
        assert "cost" in result

        # checkpoint() saves state
        ckpt_path = Path(tmpdir)
        executor.checkpoint(trial_id, ckpt_path)
        assert (ckpt_path / f"{trial_id}.pkl").exists()

        # load_checkpoint() restores state
        loaded = executor.load_checkpoint(trial_id, ckpt_path)
        assert loaded is not None


def test_store_protocol():
    """Store implements persistence protocol."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        # write_study() persists study
        study = Study(
            study_id="test_study",
            space_json="{}",
            objective="minimize",
            seed=42,
            budget=100.0,
            status="running"
        )
        store.write_study(study)

        # read_study() retrieves study
        retrieved = store.read_study("test_study")
        assert retrieved is not None
        assert retrieved.study_id == "test_study"

        # write_trial() persists trial
        trial = Trial(
            trial_id="trial_0",
            config={"x": 0.5},
            seed=42,
            fidelity=1.0,
            value=0.25,
            cost=1.5,
            status="completed"
        )
        store.write_trial(trial, "test_study")

        # read_trials() retrieves trials
        trials = store.read_trials("test_study")
        assert len(trials) == 1
        assert trials[0].trial_id == "trial_0"

        # lineage() traces parent pointers
        lineage = store.lineage("trial_0")
        assert "trial_0" in lineage

        store.close()


def test_searchspace_protocol():
    """SearchSpace validates knob structure."""
    space = SearchSpace()

    # add_knob() registers knob
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    assert len(space.knobs) == 1

    # Duplicate names rejected
    with pytest.raises(ValueError, match="Duplicate"):
        space.add_knob(Knob("x", kind="continuous", bounds=(0, 2)))

    # Invalid bounds rejected
    with pytest.raises(ValueError):
        space.add_knob(Knob("bad", kind="continuous", bounds=(1, 0)))

    # Categorical requires list
    with pytest.raises(ValueError):
        space.add_knob(Knob("cat", kind="categorical", bounds=(0, 1)))


def test_contract_batch_consistency():
    """All searchers return requested batch size."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    for SearcherClass in [SobolSearcher, RandomSearcher]:
        searcher = SearcherClass(space, seed=42)
        for n in [1, 8, 16]:
            configs = searcher.propose(n)
            assert len(configs) == n, f"{SearcherClass.__name__} failed to return {n} configs"


def test_contract_state_roundtrip():
    """State serialization round-trips correctly."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    for SearcherClass in [SobolSearcher, RandomSearcher]:
        # Original sequence
        s1 = SearcherClass(space, seed=42)
        batch1 = s1.propose(5)
        state = s1.state_dict()
        batch2 = s1.propose(5)

        # Restored sequence
        s2 = SearcherClass(space, seed=999)
        s2.load_state_dict(state)
        batch2_restored = s2.propose(5)

        # Should match
        for c1, c2 in zip(batch2, batch2_restored):
            for key in c1.keys():
                assert abs(c1[key] - c2[key]) < 1e-9, f"{SearcherClass.__name__} state recovery failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
