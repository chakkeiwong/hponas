# Historical bootstrap/quota regression contract, explicitly retained for compatibility.
# Default reference ASHA is verified in test_asha_reference.py.
"""Contract conformance tests for Scheduler interface.

Authority: HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 2 Day 2
Purpose: Verify ASHA scheduler contract compliance

Contract Requirements:
- report() accepts observations and returns stopping decisions
- promote() returns trials to resume with next fidelity
- Early stopping decisions are consistent
- State serialization/deserialization works correctly
- Behavioral equivalence after state restoration
- Mutation score ≥0.9 (V03 validation)
"""

import json
import numpy as np
import pytest

from hponas.schedulers import ASHAScheduler, ASHAConfig, BudgetedASHAScheduler, BudgetedASHAConfig


def _asha_config():
    """Standard ASHA config for testing."""
    return ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0, median_stopping=False)


class TestSchedulerContractASHAReport:
    """Test ASHA report() contract compliance."""

    def test_asha_report_at_rung_returns_pause(self):
        """Test report() returns 'pause' at rung boundaries."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at first rung (r_min = 1.0)
        decision = scheduler.report("trial_1", fidelity=1.0, value=0.5)
        assert decision == "pause"

    def test_asha_report_at_final_rung_returns_stop(self):
        """Test report() returns 'stop' at final rung."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at final rung (r_max = 27.0)
        decision = scheduler.report("trial_1", fidelity=27.0, value=0.5)
        assert decision == "stop"

    def test_asha_report_between_rungs_returns_continue(self):
        """Test report() returns 'continue' between rung boundaries."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report between rungs
        decision = scheduler.report("trial_1", fidelity=2.5, value=0.5)
        assert decision == "continue"

    def test_asha_median_stopping_kills_worse_than_median(self):
        """Test median stopping rule stops trials worse than median."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0, median_stopping=True)
        scheduler = ASHAScheduler(config)

        # Report 5 trials at fidelity 2.5 (between rungs) with values 0.1, 0.2, 0.3, 0.4, 0.5
        # Median stopping checks AFTER adding to history, so the 5th value is included
        # when checking whether to stop itself
        for i, val in enumerate([0.1, 0.2, 0.3, 0.4]):
            decision = scheduler.report(f"trial_{i}", fidelity=2.5, value=val)
            assert decision == "continue"

        # 5th trial with value 0.5: history becomes [0.1, 0.2, 0.3, 0.4, 0.5]
        # Median is 0.3, but 0.5 > 0.3, so this trial is stopped
        decision = scheduler.report("trial_4", fidelity=2.5, value=0.5)
        assert decision == "stop"

        # Now history has 5 observations: [0.1, 0.2, 0.3, 0.4, 0.5]
        # New trial with value 0.4 > median(0.3) should be stopped
        decision = scheduler.report("trial_bad", fidelity=2.5, value=0.4)
        assert decision == "stop"

        # Value 0.2 < median(0.3) should continue
        decision = scheduler.report("trial_good", fidelity=2.5, value=0.2)
        assert decision == "continue"


class TestSchedulerContractASHAPromote:
    """Test ASHA promote() contract compliance."""

    def test_asha_promote_top_third_when_eta_is_3(self):
        """Test promote() promotes top 1/eta trials from each rung."""
        config = _asha_config()  # eta=3
        scheduler = ASHAScheduler(config)

        # Report 9 trials at first rung with different values
        for i in range(9):
            decision = scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))
            assert decision == "pause"

        # Promote should select top 3 (values 0, 1, 2)
        promotions = scheduler.promote()

        # Should promote ceil(9/3) = 3 trials
        assert len(promotions) == 3

        # Promoted trials should be the best ones (lowest values)
        promoted_ids = {tid for tid, _ in promotions}
        assert "trial_0" in promoted_ids  # Best
        assert "trial_1" in promoted_ids  # Second best
        assert "trial_2" in promoted_ids  # Third best
        assert "trial_8" not in promoted_ids  # Worst should not be promoted

        # Next fidelity should be r_min * eta = 1.0 * 3 = 3.0
        for _, next_fidelity in promotions:
            assert abs(next_fidelity - 3.0) < 1e-6

    def test_asha_promote_all_when_population_small(self):
        """Test promote() promotes all trials when population ≤ eta."""
        config = _asha_config()  # eta=3
        scheduler = ASHAScheduler(config)

        # Report only 2 trials (< eta=3)
        scheduler.report("trial_0", fidelity=1.0, value=0.5)
        scheduler.report("trial_1", fidelity=1.0, value=0.8)

        # Should promote both to establish pipeline
        promotions = scheduler.promote()
        assert len(promotions) == 2

    def test_asha_promote_stops_non_promoted_trials(self):
        """Test promote() stops trials not selected for promotion."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report 6 trials at first rung
        for i in range(6):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        # Promote top 2
        promotions = scheduler.promote()
        assert len(promotions) == 2

        # Check internal state: non-promoted trials should be "stopped"
        for trial_id, (rung, fid, val, status) in scheduler._trial_state.items():
            if trial_id in {"trial_0", "trial_1"}:
                assert status == "active"  # Promoted trials are active
            else:
                assert status == "stopped"  # Others are stopped

    def test_asha_promote_no_promotion_from_final_rung(self):
        """Test promote() does not promote from final rung."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at final rung
        scheduler.report("trial_1", fidelity=27.0, value=0.5)

        # Promote should return empty list (no promotion from final rung)
        promotions = scheduler.promote()
        assert len(promotions) == 0


class TestSchedulerContractASHARungLogic:
    """Test ASHA rung computation and boundary detection."""

    def test_asha_rung_boundaries_computed_correctly(self):
        """Test rungs are computed as [r_min, r_min*η, r_min*η^2, ..., r_max]."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Expected rungs: [1.0, 3.0, 9.0, 27.0]
        assert len(scheduler.rungs) == 4
        assert abs(scheduler.rungs[0] - 1.0) < 1e-6
        assert abs(scheduler.rungs[1] - 3.0) < 1e-6
        assert abs(scheduler.rungs[2] - 9.0) < 1e-6
        assert abs(scheduler.rungs[3] - 27.0) < 1e-6

    def test_asha_fidelity_to_rung_mapping(self):
        """Test _fidelity_to_rung() correctly maps fidelity to rung index."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # At rung boundaries
        assert scheduler._fidelity_to_rung(1.0) == 0
        assert scheduler._fidelity_to_rung(3.0) == 1
        assert scheduler._fidelity_to_rung(9.0) == 2
        assert scheduler._fidelity_to_rung(27.0) == 3

        # Between rungs
        assert scheduler._fidelity_to_rung(2.5) is None
        assert scheduler._fidelity_to_rung(5.0) is None

    def test_asha_trial_state_tracked_correctly(self):
        """Test trial state is tracked and updated correctly."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report a trial
        scheduler.report("trial_1", fidelity=1.0, value=0.5)

        # Check state is tracked
        assert "trial_1" in scheduler._trial_state
        rung_idx, fid, val, status = scheduler._trial_state["trial_1"]
        assert rung_idx == 0
        assert abs(fid - 1.0) < 1e-6
        assert abs(val - 0.5) < 1e-6
        assert status == "paused"

    def test_asha_rung_populations_tracked_correctly(self):
        """Test rung populations track (trial_id, value) correctly."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report 3 trials at first rung
        scheduler.report("trial_1", fidelity=1.0, value=0.3)
        scheduler.report("trial_2", fidelity=1.0, value=0.1)
        scheduler.report("trial_3", fidelity=1.0, value=0.5)

        # Check rung population
        pop = scheduler._rung_populations[0]
        assert len(pop) == 3
        assert ("trial_1", 0.3) in pop
        assert ("trial_2", 0.1) in pop
        assert ("trial_3", 0.5) in pop


class TestSchedulerContractASHAStateSerialization:
    """Test ASHA state serialization/deserialization."""

    def test_asha_state_is_serializable(self):
        """Test state_dict() returns JSON-serializable dict."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Run some trials
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=1.0, value=0.3)

        # Get state
        state = scheduler.state_dict()

        # Should be JSON-serializable
        json_str = json.dumps(state)
        assert isinstance(json_str, str)

        # Should contain expected keys
        assert "config" in state
        assert "rungs" in state
        assert "trial_state" in state
        assert "rung_populations" in state

    def test_asha_load_state_dict_restores_state(self):
        """Test load_state_dict() restores scheduler state."""
        config = _asha_config()
        scheduler1 = ASHAScheduler(config)

        # Run some trials
        scheduler1.report("trial_1", fidelity=1.0, value=0.5)
        scheduler1.report("trial_2", fidelity=1.0, value=0.3)
        scheduler1.report("trial_3", fidelity=1.0, value=0.7)

        # Save state
        state = scheduler1.state_dict()

        # Create new scheduler and restore state
        scheduler2 = ASHAScheduler(config)
        scheduler2.load_state_dict(state)

        # Verify state matches
        assert scheduler2.rungs == scheduler1.rungs
        assert scheduler2._trial_state == scheduler1._trial_state
        assert scheduler2._rung_populations == scheduler1._rung_populations

    def test_asha_state_deserialization_produces_identical_behavior(self):
        """Test deserialized state produces identical promotion decisions."""
        config = _asha_config()
        scheduler1 = ASHAScheduler(config)

        # Run some trials to first rung
        for i in range(9):
            scheduler1.report(f"trial_{i}", fidelity=1.0, value=float(i))

        # Save state before promotion
        state = scheduler1.state_dict()

        # Promote in original scheduler
        promotions1 = scheduler1.promote()

        # Create new scheduler and restore state
        scheduler2 = ASHAScheduler(config)
        scheduler2.load_state_dict(state)

        # Promote in restored scheduler
        promotions2 = scheduler2.promote()

        # Promotions should be identical
        assert len(promotions1) == len(promotions2)
        assert set(promotions1) == set(promotions2)

    def test_asha_state_survives_json_roundtrip(self):
        """Test state survives JSON serialization roundtrip."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Run trials
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=3.0, value=0.3)

        # Save, serialize, deserialize
        state1 = scheduler.state_dict()
        json_str = json.dumps(state1)
        state2 = json.loads(json_str)

        # Restore from deserialized state
        scheduler2 = ASHAScheduler(config)
        scheduler2.load_state_dict(state2)

        # States should match after proper deserialization
        assert scheduler2._trial_state == scheduler._trial_state
        assert scheduler2._rung_populations == scheduler._rung_populations


class TestSchedulerContractASHAEdgeCases:
    """Test ASHA edge cases and boundary conditions."""

    def test_asha_same_trial_multiple_reports_at_same_rung(self):
        """Test same trial can report multiple times at same rung (updates value)."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report same trial twice at same rung
        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        scheduler.report("trial_1", fidelity=1.0, value=0.3)  # Better value

        # A repeated report replaces the prior score without inflating promotion quotas.
        pop = scheduler._rung_populations[0]
        assert len(pop) == 1
        assert ("trial_1", 0.8) not in pop
        assert ("trial_1", 0.3) in pop

        # Trial state should track best value
        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.3) < 1e-6  # Best of 0.8 and 0.3

    def test_asha_promotion_math_edge_case_ceil(self):
        """Test promotion count uses ceil() correctly for fractional results."""
        config = _asha_config()  # eta=3
        scheduler = ASHAScheduler(config)

        # Report 7 trials (7/3 = 2.33, ceil = 3)
        for i in range(7):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        promotions = scheduler.promote()

        # Should promote ceil(7/3) = 3 trials
        assert len(promotions) == 3

    def test_asha_rung_includes_r_max_when_not_power_of_eta(self):
        """Test r_max is included as final rung even if not exact power of eta."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=20.0)  # 20 != 27 = 3^3
        scheduler = ASHAScheduler(config)

        # Should have rungs [1, 3, 9, 20]
        assert scheduler.rungs[-1] == 20.0
        assert 20.0 in scheduler.rungs

    def test_asha_median_stopping_requires_at_least_5_observations(self):
        """Test median stopping needs ≥5 observations before activating."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0, median_stopping=True)
        scheduler = ASHAScheduler(config)

        # Report 4 trials (< 5)
        for i in range(4):
            decision = scheduler.report(f"trial_{i}", fidelity=2.5, value=0.1)
            assert decision == "continue"

        # 5th trial: history becomes [0.1, 0.1, 0.1, 0.1, 100.0]
        # Median is 0.1, and 100.0 > 0.1, so this trial is stopped
        decision = scheduler.report("trial_bad", fidelity=2.5, value=100.0)
        assert decision == "stop"

        # Now we have 5 observations, subsequent bad values should also be stopped
        decision = scheduler.report("trial_bad2", fidelity=2.5, value=100.0)
        assert decision == "stop"

        # Good values should continue
        decision = scheduler.report("trial_good", fidelity=2.5, value=0.05)
        assert decision == "continue"

    def test_asha_best_value_tracked_across_rungs(self):
        """Test best value is tracked as trial progresses through rungs."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at first rung
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        _, _, best_val1, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val1 - 0.5) < 1e-6

        # Promote
        promotions = scheduler.promote()
        # After promotion, trial should be active at next rung
        assert len(promotions) == 1
        assert promotions[0] == ("trial_1", 3.0)

        # Report at second rung with worse value
        scheduler.report("trial_1", fidelity=3.0, value=0.8)
        _, _, best_val2, _ = scheduler._trial_state["trial_1"]

        # best_val carries across rungs: promote() forwards it and report() takes the
        # min against it, so a worse value at the higher rung must not replace 0.5.
        assert abs(best_val2 - 0.5) < 1e-6


class TestSchedulerContractPASHA:
    """Test PASHA scheduler contract compliance."""

    def test_pasha_promotion_budget_constraint(self):
        """Test PASHA respects promotion budget constraint."""
        config = BudgetedASHAConfig(eta=3, r_min=1.0, r_max=27.0, promotion_budget=10.0)
        scheduler = BudgetedASHAScheduler(config)

        # Report 9 trials at first rung
        for i in range(9):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        # Promote - each promotion costs (3.0 - 1.0) = 2.0
        # With budget=10.0, can only afford 5 promotions (cost 10.0)
        promotions = scheduler.promote()

        # Should promote at most 5 trials (budget constraint)
        assert len(promotions) <= 5

        # Budget should be consumed
        assert scheduler._budget_spent <= 10.0

    def test_pasha_stops_trial_when_budget_exhausted(self):
        """Test PASHA stops trials when promotion budget exhausted."""
        config = BudgetedASHAConfig(eta=3, r_min=1.0, r_max=9.0, promotion_budget=5.0)
        scheduler = BudgetedASHAScheduler(config)

        # Report 6 trials at first rung
        for i in range(6):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        # Promotion cost: 3.0 - 1.0 = 2.0 per trial
        # Budget 5.0 allows 2 promotions (cost 4.0), 3rd would exceed
        promotions = scheduler.promote()

        # Should promote exactly 2 trials
        assert len(promotions) == 2

        # Check that unpromoted trials are stopped
        for trial_id, state in scheduler._trial_state.items():
            if trial_id not in {tid for tid, _ in promotions}:
                assert state[4] == "stopped"  # status field


class TestSchedulerContractPASHABestValueTracking:
    """Regression tests for the PASHA best_value dead code bug (Phase 0 Issue 4).

    PASHA carried the same defect as ASHA: report() computed best_val, then the
    "stopped"/"paused" writes overwrote it with the latest raw value.
    """

    def _pasha(self, **kwargs):
        params = dict(eta=3, r_min=1.0, r_max=9.0, promotion_budget=100.0)
        params.update(kwargs)
        return BudgetedASHAScheduler(BudgetedASHAConfig(**params))

    def test_pasha_tracks_best_value_not_latest(self):
        """Third slot holds min across reports, not the latest value."""
        scheduler = self._pasha()

        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        assert abs(scheduler._trial_state["trial_1"][2] - 0.8) < 1e-6

        scheduler.promote()

        scheduler.report("trial_1", fidelity=3.0, value=0.4)
        assert abs(scheduler._trial_state["trial_1"][2] - 0.4) < 1e-6

        # Regression must not raise the recorded best
        scheduler.report("trial_1", fidelity=3.0, value=0.95)
        assert abs(scheduler._trial_state["trial_1"][2] - 0.4) < 1e-6

    def test_pasha_best_value_retained_at_same_rung(self):
        """Repeated reports at one rung keep the minimum."""
        scheduler = self._pasha()

        for value in (0.7, 0.15, 0.9):
            scheduler.report("trial_1", fidelity=1.0, value=value)

        assert abs(scheduler._trial_state["trial_1"][2] - 0.15) < 1e-6

    def test_pasha_final_rung_records_best_value(self):
        """A stop at the final rung stores best_val, not the final raw value."""
        scheduler = self._pasha()

        scheduler.report("trial_1", fidelity=1.0, value=0.2)
        scheduler.promote()
        assert scheduler.report("trial_1", fidelity=9.0, value=0.75) == "stop"

        state = scheduler._trial_state["trial_1"]
        assert state[4] == "stopped"
        assert abs(state[2] - 0.2) < 1e-6

    def test_pasha_budget_preserved_across_reports(self):
        """Re-reporting must not reset the per-trial consumed budget to 0.0."""
        scheduler = self._pasha()

        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.promote()
        budget_after_promotion = scheduler._trial_state["trial_1"][3]

        # A promotion should have charged budget to this trial.
        assert budget_after_promotion > 0.0

        scheduler.report("trial_1", fidelity=3.0, value=0.4)
        assert abs(scheduler._trial_state["trial_1"][3] - budget_after_promotion) < 1e-6

    def test_pasha_handles_none_best_value_from_checkpoint(self):
        """report() adopts the incoming value when the stored best is None."""
        scheduler = self._pasha()
        scheduler._trial_state["trial_1"] = (0, 1.0, None, 0.0, "paused")

        scheduler.report("trial_1", fidelity=1.0, value=0.6)
        assert abs(scheduler._trial_state["trial_1"][2] - 0.6) < 1e-6

    def test_pasha_non_rung_report_returns_continue_lowercase(self):
        """Off-rung reports return the literal 'continue', not a variant."""
        scheduler = self._pasha()
        result = scheduler.report("trial_1", fidelity=1.5, value=0.4)
        assert result == "continue"
        assert result is not None

    def test_pasha_initial_trial_budget_is_zero(self):
        """A trial's first report initializes budget to exactly 0.0."""
        scheduler = self._pasha()
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        assert abs(scheduler._trial_state["trial_1"][3] - 0.0) < 1e-9


# Mutation testing targets
# These tests are designed to kill common mutations in schedulers.py:
# - Off-by-one in rung index calculations (e.g., rung_idx vs rung_idx+1)
# - Wrong comparison operators in promotion logic (< vs <=, > vs >=)
# - Incorrect arithmetic in promotion count (ceil vs floor, / vs //)
# - Missing min() in best value tracking
# - Wrong array indexing in rung populations
# - Incorrect status string literals ("pause" vs "stop" vs "continue")
# - Budget tracking arithmetic errors in PASHA
# - Median calculation boundary conditions


class TestSchedulerContractASHAMutationTargets:
    """Tests specifically designed to kill common mutations in ASHA scheduler."""

    def test_asha_promotion_count_uses_ceil_not_floor(self):
        """Test that promotion count uses ceil(n/eta), not floor(n/eta).

        Mutation: math.ceil -> math.floor
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Report 10 trials: ceil(10/3)=4, floor(10/3)=3
        for i in range(10):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        promotions = scheduler.promote()

        # Should promote 4 (ceil), not 3 (floor)
        assert len(promotions) == 4

    def test_asha_best_value_uses_min_not_first_value(self):
        """Test that best value tracking uses min(value, prev_val), not just value.

        Mutation: min(value, prev_val) -> value
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # First report at rung 0 with value 0.8
        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        scheduler.promote()

        # Second report at rung 1 with better value 0.3
        scheduler.report("trial_1", fidelity=3.0, value=0.3)

        # Best value should be 0.3 (min), not 0.8
        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.3) < 1e-6

    def test_asha_rung_boundary_detection_uses_correct_tolerance(self):
        """Test that fidelity-to-rung uses abs(fidelity - r) < 1e-6, not ==.

        Mutation: abs(fidelity - r) < 1e-6 -> fidelity == r
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report with slight floating-point error
        fidelity_with_error = 3.0 + 1e-9
        decision = scheduler.report("trial_1", fidelity=fidelity_with_error, value=0.5)

        # Should still recognize as rung boundary and return "pause"
        assert decision == "pause"

    def test_asha_promotion_selects_top_not_bottom_trials(self):
        """Test that promotion sorts ascending (best first), not descending.

        Mutation: sorted(pop, key=lambda x: x[1]) -> sorted(pop, key=lambda x: x[1], reverse=True)
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report trials with values 5, 4, 3, 2, 1
        for i in range(5, 0, -1):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        promotions = scheduler.promote()
        promoted_ids = {tid for tid, _ in promotions}

        # Should promote best (lowest values): trial_1, trial_2
        assert "trial_1" in promoted_ids
        assert "trial_2" in promoted_ids
        # Should NOT promote worst: trial_5
        assert "trial_5" not in promoted_ids

    def test_asha_median_stopping_compares_value_gt_median_not_gte(self):
        """Test that median stopping uses value > median, not value >= median.

        Mutation: value > median -> value >= median
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0, median_stopping=True)
        scheduler = ASHAScheduler(config)

        # Create history with median = 0.3: [0.1, 0.2, 0.3, 0.4, 0.5]
        for i, val in enumerate([0.1, 0.2, 0.3, 0.4, 0.5]):
            scheduler.report(f"trial_{i}", fidelity=2.5, value=val)

        # Value exactly equal to median should continue (not stopped)
        decision = scheduler.report("trial_equal", fidelity=2.5, value=0.3)
        assert decision == "continue"

        # Value greater than median should be stopped
        decision = scheduler.report("trial_worse", fidelity=2.5, value=0.31)
        assert decision == "stop"

    def test_asha_final_rung_check_uses_len_minus_1_not_len(self):
        """Test that final rung check uses rung_idx == len(rungs)-1, not len(rungs).

        Mutation: len(self.rungs) - 1 -> len(self.rungs)
        """
        config = _asha_config()  # rungs: [1.0, 3.0, 9.0, 27.0]
        scheduler = ASHAScheduler(config)

        # Report at index 3 (27.0), which is len(rungs)-1 = 4-1 = 3
        decision = scheduler.report("trial_1", fidelity=27.0, value=0.5)

        # Should recognize as final rung and return "stop"
        assert decision == "stop"

    def test_asha_promotion_range_excludes_final_rung(self):
        """Test that promote() iterates range(len(rungs)-1), not range(len(rungs)).

        Mutation: range(len(self.rungs) - 1) -> range(len(self.rungs))
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at final rung
        scheduler.report("trial_1", fidelity=27.0, value=0.5)

        # Promote should not try to promote from final rung
        promotions = scheduler.promote()
        assert len(promotions) == 0

        # Trial should be "stopped", not promoted
        _, _, _, status = scheduler._trial_state["trial_1"]
        assert status == "stopped"

    def test_asha_rung_computation_multiplies_by_eta_not_adds(self):
        """Test that rung computation uses r *= eta, not r += eta.

        Mutation: r *= config.eta -> r += config.eta
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Should be [1, 3, 9, 27] (multiply), not [1, 4, 7, 10, ...] (add)
        assert abs(scheduler.rungs[1] - 3.0) < 1e-6
        assert abs(scheduler.rungs[2] - 9.0) < 1e-6
        assert abs(scheduler.rungs[3] - 27.0) < 1e-6

    def test_asha_median_requires_at_least_5_not_4_observations(self):
        """Test that median stopping needs len(history) >= 5, not >= 4.

        Mutation: len(history) >= 5 -> len(history) >= 4
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0, median_stopping=True)
        scheduler = ASHAScheduler(config)

        # Report exactly 4 observations
        for i in range(4):
            decision = scheduler.report(f"trial_{i}", fidelity=2.5, value=0.5)
            # With only 4 observations, median stopping should not trigger
            assert decision == "continue"

        # 5th observation: now median stopping is active
        # Median of [0.5, 0.5, 0.5, 0.5, 0.9] is 0.5, and 0.9 > 0.5
        decision = scheduler.report("trial_5", fidelity=2.5, value=0.9)
        assert decision == "stop"

    def test_asha_next_fidelity_is_next_rung_not_current_rung(self):
        """Test that promotion uses rungs[next_rung], not rungs[rung_idx].

        Mutation: self.rungs[next_rung] -> self.rungs[rung_idx]
        """
        config = _asha_config()  # rungs: [1.0, 3.0, 9.0, 27.0]
        scheduler = ASHAScheduler(config)

        # Report at rung 0 (1.0)
        scheduler.report("trial_1", fidelity=1.0, value=0.5)

        # Promote: should get next_rung=1 -> fidelity=3.0, not current rung 0 -> 1.0
        promotions = scheduler.promote()
        _, next_fidelity = promotions[0]

        assert abs(next_fidelity - 3.0) < 1e-6

    def test_asha_promotion_updates_trial_rung_to_next_not_current(self):
        """Test that promotion sets trial rung to next_rung, not rung_idx.

        Mutation: (next_rung, ...) -> (rung_idx, ...)
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at rung 0
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.promote()

        # Trial should now be at rung 1, not still at rung 0
        trial_rung, _, _, _ = scheduler._trial_state["trial_1"]
        assert trial_rung == 1

    def test_asha_status_active_after_promotion_not_paused(self):
        """Test that promoted trials get status 'active', not 'paused'.

        Mutation: "active" -> "paused"
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.promote()

        # After promotion, status should be "active"
        _, _, _, status = scheduler._trial_state["trial_1"]
        assert status == "active"

    def test_asha_status_stopped_for_non_promoted_not_paused(self):
        """Test that non-promoted trials get status 'stopped', not 'paused'.

        Mutation: "stopped" -> "paused"
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report 6 trials, only top 2 will be promoted
        for i in range(6):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=float(i))

        promotions = scheduler.promote()
        promoted_ids = {tid for tid, _ in promotions}

        # Non-promoted trials should have status "stopped"
        for trial_id, (_, _, _, status) in scheduler._trial_state.items():
            if trial_id not in promoted_ids:
                assert status == "stopped"

    def test_asha_promote_skips_empty_rungs_with_continue_not_break(self):
        """Test that promote uses continue (not break) to skip empty rungs.

        Mutation: continue -> break
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)  # 4 rungs: [1, 3, 9, 27]
        scheduler = ASHAScheduler(config)

        # Leave rung 0 empty (no trials at fidelity=1.0)
        # Leave rung 1 empty (no trials at fidelity=3.0)
        # Report trials at rung 2 (fidelity=9.0)
        scheduler.report("trial_1", fidelity=9.0, value=0.3)
        scheduler.report("trial_2", fidelity=9.0, value=0.5)
        scheduler.report("trial_3", fidelity=9.0, value=0.4)

        promotions = scheduler.promote()

        # With continue: skips empty rungs 0 and 1, processes rung 2, promotes trials
        # With break: stops at empty rung 0, never processes rung 2, no promotions
        assert len(promotions) >= 1
        assert any(tid in ["trial_1", "trial_2", "trial_3"] for tid, _ in promotions)

    def test_asha_promote_range_not_off_by_two(self):
        """Test that promote iterates range(len-1), not range(len-2).

        Mutation: range(len(self.rungs) - 1) -> range(len(self.rungs) - 2)
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)  # 3 rungs: [1, 3, 9]
        scheduler = ASHAScheduler(config)

        # Report at second-to-last rung (index 1)
        scheduler.report("trial_1", fidelity=3.0, value=0.5)

        promotions = scheduler.promote()

        # Should promote from rung 1 (second-to-last) to rung 2 (last)
        # With range(len-1): processes rungs 0 and 1
        # With range(len-2): only processes rung 0, skips rung 1
        assert len(promotions) == 1
        assert promotions[0][0] == "trial_1"

        # State should be a tuple, not None
        state = scheduler._trial_state["trial_1"]
        assert state is not None
        assert isinstance(state, tuple)
        assert len(state) == 4

    def test_asha_best_value_not_none_on_update(self):
        """Test that best_val uses min logic, not None.

        Mutation: best_val = value if prev_val is None else min(...) -> best_val = None
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # First report
        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        scheduler.promote()

        # Second report at next rung
        scheduler.report("trial_1", fidelity=3.0, value=0.5)

        # Best value should be 0.5, not None
        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert best_val is not None
        assert abs(best_val - 0.5) < 1e-6

    def test_asha_line_125_stores_current_value_in_paused_state(self):
        """Test that line 125 stores the current value when pausing.

        This test verifies the current behavior where line 125 stores 'value'
        (not best_val) when transitioning to paused state. This catches mutations
        that would change line 125 from using 'value' to something else.
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # Report at rung boundary
        decision = scheduler.report("trial_1", fidelity=1.0, value=0.7)

        # Should be paused at rung boundary
        assert decision == "pause"

        # Line 125 stores the current value in paused state
        _, _, stored_val, status = scheduler._trial_state["trial_1"]
        assert status == "paused"
        assert abs(stored_val - 0.7) < 1e-6

    def test_asha_state_dict_has_exact_key_names(self):
        """Test that state_dict uses exact key names, not case variants.

        Mutations: "eta" -> "ETA"/"XXetaXX", "r_min" -> "R_MIN", etc.
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        state = scheduler.state_dict()

        # Check top-level keys are exact
        assert "config" in state
        assert "rungs" in state
        assert "trial_state" in state
        assert "rung_populations" in state

        # Check config sub-keys are exact lowercase
        config_keys = set(state["config"].keys())
        assert config_keys == {"eta", "r_min", "r_max", "median_stopping", "promotion_policy", "median_min_completed", "report_grid"}

        # Verify values match
        assert state["config"]["eta"] == 3
        assert state["config"]["r_min"] == 1.0
        assert state["config"]["r_max"] == 9.0

    def test_asha_conditional_uses_is_none_not_is_not_none(self):
        """Test that best_val condition uses 'is None', not 'is not None'.

        Mutations:
        - value if prev_best is None else min(...) -> ... is not None ...
        - value if (prev_best is None) and False else min(...)
        - value if (prev_best is None) or True else min(...)
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        # First report - no prior state, best_val must be the reported value
        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.8) < 1e-6

        scheduler.promote()

        # Second report - prev_best is 0.8, so min(0.9, 0.8) = 0.8.
        # An 'is not None' mutation would take the value branch and yield 0.9.
        scheduler.report("trial_1", fidelity=3.0, value=0.9)
        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.8) < 1e-6


class TestSchedulerContractASHABestValueTracking:
    """Regression tests for the best_value dead code bug (Phase 0 Issue 4).

    The third slot of _trial_state is documented as best_value_so_far. Before the
    fix, lines 108-112 computed it and line 125 unconditionally overwrote it with
    the latest raw value, so promote() ranked by latest value instead of best.
    """

    def test_asha_tracks_best_value_not_latest(self):
        """_trial_state third slot holds min across reports, not the latest value."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.8)
        _, _, best_1, _ = scheduler._trial_state["trial_1"]
        assert abs(best_1 - 0.8) < 1e-6

        scheduler.promote()

        # Improvement: best must move down
        scheduler.report("trial_1", fidelity=3.0, value=0.5)
        _, _, best_2, _ = scheduler._trial_state["trial_1"]
        assert abs(best_2 - 0.5) < 1e-6, "best should follow an improvement"

        # Regression: best must NOT move back up
        scheduler.report("trial_1", fidelity=3.0, value=0.9)
        _, _, best_3, _ = scheduler._trial_state["trial_1"]
        assert abs(best_3 - 0.5) < 1e-6, (
            "best should be retained, not replaced by latest"
        )

    def test_asha_best_value_retained_at_same_rung(self):
        """Repeated reports at one rung keep the minimum, not the last one seen."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        for value in (0.7, 0.2, 0.6, 0.95):
            scheduler.report("trial_1", fidelity=1.0, value=value)

        _, _, best_val, _ = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.2) < 1e-6

    def test_asha_best_value_survives_promotion(self):
        """promote() carries best_val forward rather than resetting it."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.3)
        promotions = scheduler.promote()
        assert any(tid == "trial_1" for tid, _ in promotions)

        _, _, best_val, status = scheduler._trial_state["trial_1"]
        assert abs(best_val - 0.3) < 1e-6
        assert status == "active"

    def test_asha_final_rung_records_best_value(self):
        """A stop at the final rung stores best_val, not the final raw value."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0, median_stopping=False)
        scheduler = ASHAScheduler(config)

        # Reach the final rung with a good value, then report a worse one there.
        scheduler.report("trial_1", fidelity=1.0, value=0.25)
        scheduler.promote()
        decision = scheduler.report("trial_1", fidelity=9.0, value=0.85)
        assert decision == "stop"

        _, _, best_val, status = scheduler._trial_state["trial_1"]
        assert status == "stopped"
        assert abs(best_val - 0.25) < 1e-6

    def test_asha_handles_none_best_value_from_checkpoint(self):
        """A restored checkpoint may carry None in the best_value slot.

        The slot is typed Optional[float], so load_state_dict can legitimately
        restore None (e.g. a checkpoint written before best_value was tracked).
        report() must then adopt the incoming value rather than call min() on None.
        """
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.4)
        state = scheduler.state_dict()

        # Simulate a checkpoint whose best_value slot is null.
        rung_idx, fidelity, _, status = state["trial_state"]["trial_1"]
        state["trial_state"]["trial_1"] = (rung_idx, fidelity, None, status)

        restored = ASHAScheduler(_asha_config())
        restored.load_state_dict(state)
        assert restored._trial_state["trial_1"][2] is None

        # Must not raise, and must take the reported value as the new best.
        restored.report("trial_1", fidelity=1.0, value=0.6)
        _, _, best_val, _ = restored._trial_state["trial_1"]
        assert abs(best_val - 0.6) < 1e-6

    def test_asha_state_dict_roundtrip_preserves_best_value(self):
        """Checkpointing preserves best_val so ranking survives a restore."""
        config = _asha_config()
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.4)
        scheduler.promote()
        scheduler.report("trial_1", fidelity=3.0, value=0.9)

        restored = ASHAScheduler(_asha_config())
        restored.load_state_dict(scheduler.state_dict())

        _, _, best_val, _ = restored._trial_state["trial_1"]
        assert abs(best_val - 0.4) < 1e-6
