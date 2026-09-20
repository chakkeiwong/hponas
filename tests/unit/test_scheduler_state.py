"""
Unit Tests: Scheduler State Serialization

Tests that state_dict() and load_state_dict() correctly deep copy mutable state.
Authority: Mutation testing V03 - kills copy vs deepcopy mutations.
"""

import pytest
from hponas.schedulers import ASHAScheduler, ASHAConfig


class TestASHASchedulerStateSerialization:
    """Test ASHA scheduler state serialization correctness."""

    def test_state_dict_deep_copies_rungs(self):
        """state_dict must deep copy rungs list (mutation must not affect original)."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        original_rungs = scheduler.rungs.copy()

        state = scheduler.state_dict()
        # Mutate the state dict's rungs
        state["rungs"].append(999.0)
        state["rungs"][0] = -1.0

        # Original must be unchanged
        assert scheduler.rungs == original_rungs
        assert 999.0 not in scheduler.rungs
        assert scheduler.rungs[0] == 1.0

    def test_state_dict_deep_copies_trial_state(self):
        """state_dict must deep copy _trial_state dict (mutations must not affect original)."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Populate trial state
        scheduler._trial_state = {
            "trial_1": (0, 1.0, 0.5, "paused"),
            "trial_2": (1, 3.0, 0.3, "active"),
        }

        state = scheduler.state_dict()

        # Mutate the state dict's trial_state
        state["trial_state"]["trial_1"] = (999, 999.0, 999.0, "stopped")
        state["trial_state"]["trial_3"] = (0, 1.0, 0.8, "paused")

        # Original must be unchanged
        assert scheduler._trial_state["trial_1"] == (0, 1.0, 0.5, "paused")
        assert scheduler._trial_state["trial_2"] == (1, 3.0, 0.3, "active")
        assert "trial_3" not in scheduler._trial_state

    def test_state_dict_deep_copies_rung_populations(self):
        """state_dict must deep copy _rung_populations (mutations must not affect original)."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Populate rung populations
        scheduler._rung_populations[0] = [("trial_1", 0.5), ("trial_2", 0.6)]
        scheduler._rung_populations[1] = [("trial_3", 0.3)]

        state = scheduler.state_dict()

        # Mutate the state dict's rung_populations
        state["rung_populations"][0].append(("trial_999", 999.0))
        state["rung_populations"][1] = []
        state["rung_populations"][999] = [("fake", 1.0)]

        # Original must be unchanged
        assert len(scheduler._rung_populations[0]) == 2
        assert scheduler._rung_populations[0][0] == ("trial_1", 0.5)
        assert len(scheduler._rung_populations[1]) == 1
        assert 999 not in scheduler._rung_populations

    def test_state_dict_deep_copies_fidelity_history(self):
        """state_dict must deep copy _fidelity_history (mutations must not affect original)."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Populate fidelity history
        scheduler._fidelity_history = {
            "trial_1": [1.0, 3.0],
            "trial_2": [1.0],
        }

        state = scheduler.state_dict()

        # Mutate the state dict's fidelity_history
        state["fidelity_history"]["trial_1"].append(999.0)
        state["fidelity_history"]["trial_2"] = [999.0]
        state["fidelity_history"]["trial_999"] = [1.0]

        # Original must be unchanged
        assert scheduler._fidelity_history["trial_1"] == [1.0, 3.0]
        assert scheduler._fidelity_history["trial_2"] == [1.0]
        assert "trial_999" not in scheduler._fidelity_history

    def test_load_state_dict_restores_complete_state(self):
        """load_state_dict must restore complete scheduler state."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)

        # Scheduler 1: build up state
        s1 = ASHAScheduler(config)
        s1._trial_state = {"t1": (0, 1.0, 0.5, "paused")}
        s1._rung_populations[0] = [("t1", 0.5)]
        s1._fidelity_history = {"t1": [1.0]}

        state = s1.state_dict()

        # Scheduler 2: load state
        s2 = ASHAScheduler(config)
        s2.load_state_dict(state)

        # State should match
        assert s2.rungs == s1.rungs
        assert s2._trial_state == s1._trial_state
        assert s2._rung_populations == s1._rung_populations
        assert s2._fidelity_history == s1._fidelity_history
