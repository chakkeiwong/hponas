"""
R8 Mutation Tests - Target scheduler and space survivors

Focus: Kill 86+ survivors to reach 90% from 89.54%
Priority: Scheduler rungs (80 survivors), space serialization (13 survivors)
"""

import pytest
import numpy as np
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.space import Knob, SearchSpace


class TestASHASchedulerBoundaryConditions:
    """Tests for ASHA scheduler edge cases that survived mutation testing."""

    def test_rungs_when_r_max_is_exact_power_of_eta(self):
        """Rung computation must include r_max when r_max = r_min * eta^k exactly."""
        # This kills mutant_4: while r <= config.r_max vs while r < config.r_max
        config = ASHAConfig(r_min=1, r_max=27, eta=3)  # 27 = 1 * 3^3
        scheduler = ASHAScheduler(config)

        # Expected rungs: [1, 3, 9, 27]
        assert 27 in scheduler.rungs, "r_max must be in rungs when it's an exact power"
        assert scheduler.rungs == [1.0, 3.0, 9.0, 27.0]

    def test_rungs_when_r_max_between_powers(self):
        """Rung computation must append r_max when it's between powers."""
        config = ASHAConfig(r_min=1, r_max=50, eta=3)  # 50 is between 27 and 81
        scheduler = ASHAScheduler(config)

        # Expected rungs: [1, 3, 9, 27, 50]
        assert 50 in scheduler.rungs, "r_max must be appended when not an exact power"
        assert scheduler.rungs[-1] == 50.0
        assert len(scheduler.rungs) == 5

    def test_rungs_with_eta_2(self):
        """Rung computation with eta=2 (binary search)."""
        config = ASHAConfig(r_min=1, r_max=16, eta=2)  # 16 = 1 * 2^4
        scheduler = ASHAScheduler(config)

        assert scheduler.rungs == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_promote_boundary_at_eta_threshold(self):
        """Promotion logic when population size equals eta exactly."""
        # This targets mutant_16: if n_pop <= self.config.eta vs if n_pop < self.config.eta
        config = ASHAConfig(r_min=1, r_max=9, eta=3)
        scheduler = ASHAScheduler(config)

        # Simulate 3 paused trials at rung 0 (exactly eta trials)
        scheduler._rung_populations[0] = [
            ('trial_1', 0.5),  # best (lowest value)
            ('trial_2', 0.6),
            ('trial_3', 0.8),
        ]
        scheduler._trial_state = {
            'trial_1': (0, 1.0, 0.5, 'paused'),
            'trial_2': (0, 1.0, 0.6, 'paused'),
            'trial_3': (0, 1.0, 0.8, 'paused'),
        }

        # Should promote all 3 trials when n_pop <= eta
        promotions = scheduler.promote()
        assert len(promotions) == 3
        assert ('trial_1', 3.0) in promotions  # promoted to next rung (3.0)

    def test_promote_boundary_below_eta(self):
        """Promotion with population < eta."""
        config = ASHAConfig(r_min=1, r_max=9, eta=3)
        scheduler = ASHAScheduler(config)

        # Simulate 2 paused trials at rung 0 (below eta)
        scheduler._rung_populations[0] = [
            ('trial_1', 0.5),
            ('trial_2', 0.6),
        ]
        scheduler._trial_state = {
            'trial_1': (0, 1.0, 0.5, 'paused'),
            'trial_2': (0, 1.0, 0.6, 'paused'),
        }

        # Should promote both trials when n_pop < eta
        promotions = scheduler.promote()
        assert len(promotions) == 2


class TestSpaceSerializationRoundTrip:
    """Tests for space serialization edge cases that survived mutation testing."""

    def test_knob_from_dict_with_missing_transform(self):
        """from_dict must handle missing 'transform' key with correct default."""
        # This targets mutant_40: transform=data.get("transform", "none") vs None
        data = {
            "name": "lr",
            "kind": "continuous",
            "bounds": [0.001, 0.1],
            # transform key missing
        }

        knob = Knob.from_dict(data)
        assert knob.transform == "none", "Default transform must be 'none', not None"

    def test_knob_from_dict_with_explicit_none_transform(self):
        """from_dict must handle explicit transform='none'."""
        data = {
            "name": "lr",
            "kind": "continuous",
            "bounds": [0.001, 0.1],
            "transform": "none",
        }

        knob = Knob.from_dict(data)
        assert knob.transform == "none"

    def test_knob_from_dict_with_missing_note(self):
        """from_dict must handle missing 'note' key."""
        # Targets mutant_51: note=data.get("note", "") vs None
        data = {
            "name": "lr",
            "kind": "continuous",
            "bounds": [0.001, 0.1],
        }

        knob = Knob.from_dict(data)
        assert knob.note == "", "Default note must be empty string, not None"

    def test_knob_from_dict_with_missing_prior(self):
        """from_dict must handle missing 'prior' key."""
        data = {
            "name": "lr",
            "kind": "continuous",
            "bounds": [0.001, 0.1],
        }

        knob = Knob.from_dict(data)
        assert knob.prior is None, "Default prior must be None"

    def test_search_space_to_json_round_trip(self):
        """SearchSpace.to_json() -> from_dict() must preserve all fields."""
        # Targets multiple mutants in to_json serialization
        import json

        original = SearchSpace([
            Knob("lr", "continuous", (0.001, 0.1), transform="log"),
            Knob("opt", "categorical", ["adam", "sgd"]),
        ])

        json_str = original.to_json()
        data = json.loads(json_str)
        restored = SearchSpace.from_dict(data)

        assert len(restored.knobs) == 2
        assert restored.knobs[0].name == "lr"
        assert restored.knobs[0].transform == "log"
        assert restored.knobs[1].name == "opt"
        assert restored.knobs[1].bounds == ["adam", "sgd"]

    def test_search_space_get_knob_missing_raises(self):
        """SearchSpace.get_knob() must raise KeyError for missing knob."""
        # Targets mutant_2 in get_knob error handling
        space = SearchSpace([Knob("lr", "continuous", (0.001, 0.1))])

        with pytest.raises(KeyError, match="not found"):
            space.get_knob("nonexistent")


class TestLegacySearcherDefaults:
    """Tests for legacy searcher default parameters that survived."""

    def test_sobol_searcher_default_seed(self):
        """SobolSearcher must use seed=0 by default."""
        from hponas.legacy_searchers import SobolSearcher
        from hponas.space import SearchSpace, Knob

        # Create space with the new API
        space = SearchSpace([
            Knob(name="x", kind="continuous", bounds=(0.0, 1.0))
        ])

        # Call without seed argument
        searcher1 = SobolSearcher(space)
        searcher2 = SobolSearcher(space)

        # Both should produce same first proposal (deterministic with seed=0)
        config1 = searcher1.propose(1)[0]
        config2 = searcher2.propose(1)[0]

        # Values should be identical (both using seed=0)
        assert config1["x"] == config2["x"]


class TestLocalExecutorModeValidation:
    """Tests for LocalExecutor mode validation that survived."""

    def test_execute_rejects_async_mode(self):
        """execute() must reject when mode='async'."""
        from hponas.executors.local_executor import LocalExecutor
        from hponas.types import Trial, Config

        executor = LocalExecutor(mode="async")
        trial = Trial(trial_id="t1", config=Config(values={"x": 0.5}))

        with pytest.raises(ValueError, match="async"):
            executor.execute(trial=trial, objective_fn=lambda cfg: cfg["x"])

    def test_execute_accepts_sync_mode(self):
        """execute() must work when mode='sync'."""
        from hponas.executors.local_executor import LocalExecutor
        from hponas.types import Trial, Config

        executor = LocalExecutor(mode="sync")
        trial = Trial(trial_id="t1", config=Config(values={"x": 0.5}))
        result = executor.execute(
            trial=trial,
            objective_fn=lambda cfg: cfg["x"] * 2
        )

        # Result has trial_id and objective_value fields
        assert result.trial_id == "t1"
        assert result.objective_value == 1.0
