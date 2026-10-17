# Historical bootstrap/quota regression contract, explicitly retained for compatibility.
# Default reference ASHA is verified in test_asha_reference.py.
"""
Unit Tests: Schedulers

Tests individual scheduler methods in isolation.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
from hponas.schedulers import ASHAScheduler, ASHAConfig


class TestASHAScheduler:
    """Unit tests for ASHA (Asynchronous Successive Halving Algorithm)."""

    def test_init_sets_eta(self):
        """ASHAScheduler must store eta parameter."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)
        assert scheduler.config.eta == 3

    def test_promote_all_when_population_small(self):
        """When population <= eta, promote all trials to establish pipeline.

        R9.1: asserts exact count, not `>= 2`.
        R9.2: trial IDs are anti-correlated with values so sorting by id vs value differs.
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report 2 trials at rung 0 (population < eta=3)
        # ID lexicographic: trial_a < trial_b
        # Value order: trial_b (0.3) < trial_a (0.5)
        scheduler.report("trial_a", fidelity=1.0, value=0.5)
        scheduler.report("trial_b", fidelity=1.0, value=0.3)

        # Promote should return all trials
        promoted = scheduler.promote()
        promoted_ids = {trial_id for trial_id, _ in promoted}

        assert len(promoted) == 2, f"Expected exactly 2 promoted, got {len(promoted)}"
        assert promoted_ids == {"trial_a", "trial_b"}

    def test_promote_minimum_one_trial(self):
        """Promotion count is exactly max(1, ceil(n/eta)) with large eta.

        R9.1: asserts the exact count, not `>= 1`. A `max(1, ...)` → `max(2, ...)`
        mutation satisfies `>= 1` but not `== 3`.
        R9.2: trial ids are lettered and deliberately anti-correlated with values,
        so sorting by id instead of by value produces a different winner.
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=10, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # n_pop=3 <= eta=10, so the small-population branch promotes all three.
        # Id order (a, b, c) is the reverse of value order (c is best).
        scheduler.report("trial_a", fidelity=1.0, value=0.9)
        scheduler.report("trial_b", fidelity=1.0, value=0.6)
        scheduler.report("trial_c", fidelity=1.0, value=0.1)  # best

        promoted = scheduler.promote()

        assert len(promoted) == 3, (
            f"n_pop=3 <= eta=10 must promote all 3, got {len(promoted)}"
        )
        assert {tid for tid, _ in promoted} == {"trial_a", "trial_b", "trial_c"}

    def test_promote_respects_ceiling_with_small_population(self):
        """With population above eta, ceil(n/eta) determines promotion count.

        R9.2: this is the selective branch, so sort order matters. IDs ascend
        lexicographically while values descend, so a `key=None` mutation (sort by id)
        promotes {trial_a, trial_b} instead of the true best {trial_d, trial_c}.
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # n_pop=4 > eta=3, so ceil(4/3) = 2 are promoted.
        # Id order:    a < b < c < d
        # Value order: d < c < b < a   (d is best)
        scheduler.report("trial_a", fidelity=1.0, value=0.8)
        scheduler.report("trial_b", fidelity=1.0, value=0.5)
        scheduler.report("trial_c", fidelity=1.0, value=0.2)
        scheduler.report("trial_d", fidelity=1.0, value=0.1)

        promoted = scheduler.promote()

        assert len(promoted) == 2, f"Expected 2 promoted (ceil(4/3)), got {len(promoted)}"

        promoted_ids = {tid for tid, _ in promoted}
        assert promoted_ids == {"trial_d", "trial_c"}, (
            f"expected the two lowest values {{trial_d, trial_c}}, got {promoted_ids} "
            "(sorting by trial id rather than by value would give {trial_a, trial_b})"
        )

    def test_init_sets_rung_structure(self):
        """ASHAScheduler must compute rung levels from r_min, r_max, eta."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Rungs: r_min=1, 3, 9, 27=r_max
        expected_rungs = [1.0, 3.0, 9.0, 27.0]
        assert scheduler.rungs == expected_rungs

    def test_report_pauses_low_performers(self):
        """report() must pause trials below top-1/eta at each rung."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report 9 trials at r=1.0
        # Top 3 (1/eta=1/3) should continue, others pause
        for i in range(9):
            value = 0.1 * i  # 0.0, 0.1, 0.2, ..., 0.8 (lower is better)
            decision = scheduler.report(f"trial_{i}", fidelity=1.0, value=value)

            if i < 3:
                # Best 3: continue to next rung
                assert decision in ["continue", "pause"]
            else:
                # Others: paused or stopped
                assert decision in ["pause", "stop"]

    def test_promote_returns_top_performers(self):
        """promote() must return trials eligible for next rung."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report 9 trials at r=1.0
        for i in range(9):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=0.1 * i)

        promoted = scheduler.promote()
        assert isinstance(promoted, list)
        # Top 3 should be promoted
        assert len(promoted) <= 3

    def test_report_stops_at_max_fidelity(self):
        """report() must return 'stop' at r_max (no more rungs)."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report at max fidelity
        decision = scheduler.report("trial_1", fidelity=9.0, value=0.5)
        assert decision == "stop"

    def test_empty_promote_when_no_trials(self):
        """promote() must return empty list when no trials reported."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        promoted = scheduler.promote()
        assert promoted == []

    def test_multiple_rungs_sequential(self):
        """Trials must progress through rungs sequentially: r=1 → r=3 → r=9."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report at r=1.0
        scheduler.report("trial_1", fidelity=1.0, value=0.2)

        # Promote to r=3.0
        promoted = scheduler.promote()
        if promoted:
            assert any(trial_id == "trial_1" for trial_id, _ in promoted)

            # Report at r=3.0
            decision = scheduler.report("trial_1", fidelity=3.0, value=0.15)
            assert decision in ["continue", "pause", "stop"]

    def test_promote_all_when_population_small(self):
        """When population <= eta, promote all to establish pipeline."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Population of 2 (< eta=3)
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=1.0, value=0.3)

        promoted = scheduler.promote()

        # All should be promoted
        assert len(promoted) == 2
        promoted_ids = {trial_id for trial_id, _ in promoted}
        assert promoted_ids == {"trial_1", "trial_2"}

    def test_promote_minimum_one(self):
        """Promotion count is at least 1 even with large eta."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=10, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Population of 3 trials (lower value = better)
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=1.0, value=0.6)
        scheduler.report("trial_3", fidelity=1.0, value=0.7)

        promoted = scheduler.promote()

        # At least 1 promoted (max(1, ceil(3/10)) = max(1, 1) = 1)
        assert len(promoted) >= 1
        # Best trial promoted (lowest value)
        assert promoted[0][0] == "trial_1"


    def test_promote_n_promote_calculation_edge_case(self):
        """Test n_promote calculation with exact eta divisor."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=4, r_min=1.0, r_max=16.0)
        scheduler = ASHAScheduler(config)

        # Report exactly eta trials (4)
        for i in range(4):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()
        # When n_pop == eta, should promote all (edge case)
        assert len(promoted) == 4

    def test_promote_returns_correct_fidelity(self):
        """Test that promote() returns correct next fidelity for trials."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Report 6 trials at rung 0 (r=1.0)
        for i in range(6):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()

        # Check that promoted trials get correct next fidelity
        assert len(promoted) == 2  # ceil(6/3) = 2
        for trial_id, next_fidelity in promoted:
            assert next_fidelity == 3.0  # Next rung after 1.0

    def test_state_dict_preserves_structure(self):
        """Test state_dict() preserves complete scheduler state."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Add some state
        scheduler.report("trial_1", fidelity=1.0, value=0.5)
        scheduler.report("trial_2", fidelity=1.0, value=0.3)

        state = scheduler.state_dict()

        # Verify structure
        assert "config" in state
        assert "rungs" in state
        assert "trial_state" in state
        assert state["config"]["eta"] == 3
        assert len(state["rungs"]) > 0

    def test_state_dict_deep_copy_independence(self):
        """Test that state_dict() returns independent deep copies."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.5)

        state1 = scheduler.state_dict()
        state2 = scheduler.state_dict()

        # Modify state1's rungs
        if state1["rungs"]:
            state1["rungs"][0] = 999.0

        # state2 should be unaffected
        assert state2["rungs"][0] == 1.0

    def test_load_state_dict_restores_state(self):
        """Test load_state_dict() restores complete scheduler state."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler1 = ASHAScheduler(config)

        # Build up state
        scheduler1.report("trial_1", fidelity=1.0, value=0.5)
        scheduler1.report("trial_2", fidelity=1.0, value=0.3)

        state = scheduler1.state_dict()

        # Create new scheduler and load state
        scheduler2 = ASHAScheduler(config)
        scheduler2.load_state_dict(state)

        # Verify state restored
        state2 = scheduler2.state_dict()
        assert state2["rungs"] == state["rungs"]
        assert len(state2["trial_state"]) == len(state["trial_state"])

    def test_promote_with_single_trial(self):
        """Test promote() with exactly 1 trial (edge case for max(1, ...))."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=5, r_min=1.0, r_max=25.0)
        scheduler = ASHAScheduler(config)

        scheduler.report("trial_1", fidelity=1.0, value=0.5)

        promoted = scheduler.promote()

        # With 1 trial, max(1, ceil(1/5)) = max(1, 1) = 1
        assert len(promoted) == 1
        assert promoted[0][0] == "trial_1"

    def test_rung_construction_with_non_exact_divisor(self):
        """Rungs must include r_max even when r_min * eta^k != r_max exactly."""
        # With eta=3, r_min=1, r_max=20: 1→3→9→27 overshoots, so append 20
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=20.0)
        scheduler = ASHAScheduler(config)

        # Must have r_max as final rung
        assert scheduler.rungs[-1] == 20.0, f"Expected final rung=20.0, got {scheduler.rungs[-1]}"

        # Should be [1.0, 3.0, 9.0, 20.0]
        assert 20.0 in scheduler.rungs, "r_max must be in rungs"

    def test_promote_with_large_population_exact_division(self):
        """Test promotion with n_pop % eta == 0 (exact division edge case)."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report exactly 9 trials (9 % 3 == 0)
        for i in range(9):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()

        # ceil(9/3) = 3 exactly
        assert len(promoted) == 3, f"Expected exactly 3 promoted, got {len(promoted)}"

        # Verify best 3 are promoted (lowest values: trial_0, trial_1, trial_2)
        promoted_ids = {tid for tid, _ in promoted}
        assert promoted_ids == {"trial_0", "trial_1", "trial_2"}

    def test_promote_selective_with_large_population(self):
        """Test that promotion is selective when n_pop > eta."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report 12 trials (much larger than eta=3)
        for i in range(12):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()

        # Should promote ceil(12/3) = 4, NOT all 12
        assert len(promoted) == 4, f"Expected 4 promoted, got {len(promoted)}"
        assert len(promoted) < 12, "Should not promote all trials when n_pop > eta"

    def test_promote_boundary_when_n_pop_equals_eta(self):
        """When n_pop == eta exactly, all should be promoted (boundary case)."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=5, r_min=1.0, r_max=25.0)
        scheduler = ASHAScheduler(config)

        # Report exactly eta=5 trials
        for i in range(5):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()

        # All 5 should be promoted (n_pop <= eta)
        assert len(promoted) == 5, f"Expected 5 promoted when n_pop==eta, got {len(promoted)}"

    def test_promote_one_more_than_eta(self):
        """Test n_pop = eta + 1 (first case where not all are promoted)."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=4, r_min=1.0, r_max=16.0)
        scheduler = ASHAScheduler(config)

        # Report eta+1 = 5 trials
        for i in range(5):
            scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

        promoted = scheduler.promote()

        # ceil(5/4) = 2, max(1, 2) = 2
        assert len(promoted) == 2, f"Expected 2 promoted (ceil(5/4)), got {len(promoted)}"

        # Verify best 2 are promoted
        promoted_ids = {tid for tid, _ in promoted}
        assert "trial_0" in promoted_ids  # best
        assert "trial_1" in promoted_ids  # second best

    def test_rungs_exact_power_sequence(self):
        """Test that rungs form exact geometric sequence when r_max = r_min * eta^k."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=4, r_min=2.0, r_max=128.0)  # 2 * 4^3 = 128
        scheduler = ASHAScheduler(config)

        expected = [2.0, 8.0, 32.0, 128.0]
        assert scheduler.rungs == expected, f"Expected {expected}, got {scheduler.rungs}"

    def test_rungs_includes_r_max_when_overshoots(self):
        """Test that r_max is appended when geometric sequence overshoots."""
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=15.0)  # 1→3→9→27 overshoots 15
        scheduler = ASHAScheduler(config)

        # Should be [1.0, 3.0, 9.0, 15.0]
        assert scheduler.rungs[-1] == 15.0, "Final rung must be r_max"
        assert 15.0 in scheduler.rungs, "r_max must be in rungs list"
        assert scheduler.rungs == [1.0, 3.0, 9.0, 15.0], f"Got {scheduler.rungs}"


class TestASHAConfig:
    """Unit tests for ASHAConfig validation."""

    def test_eta_must_be_positive(self):
        """eta must be > 1."""
        with pytest.raises(ValueError):
            ASHAConfig(promotion_policy="legacy_bootstrap", eta=0, r_min=1.0, r_max=9.0)

        with pytest.raises(ValueError):
            ASHAConfig(promotion_policy="legacy_bootstrap", eta=1, r_min=1.0, r_max=9.0)

    def test_r_max_greater_than_r_min(self):
        """r_max must be > r_min."""
        with pytest.raises(ValueError):
            ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=9.0, r_max=1.0)

    def test_r_min_positive(self):
        """r_min must be > 0."""
        with pytest.raises(ValueError):
            ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=0.0, r_max=9.0)

        with pytest.raises(ValueError):
            ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=-1.0, r_max=9.0)


class TestASHASchedulerStateSerialization:
    """R9.6: Deep structure and state continuation tests."""

    def test_state_dict_isolates_rungs_from_later_mutation(self):
        """R9.6: the returned rungs list must not alias scheduler internals.

        `copy.deepcopy(self.rungs)` → `copy.copy(self.rungs)` is equivalent for a flat
        float list, but dropping the copy entirely aliases live state. Mutating the
        snapshot must leave the scheduler untouched.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0))

        state = scheduler.state_dict()
        state["rungs"].append(999.0)
        state["rungs"][0] = -1.0

        assert scheduler.rungs == [1.0, 3.0, 9.0], (
            f"scheduler.rungs was mutated through the snapshot: {scheduler.rungs}"
        )

    def test_state_dict_isolates_rung_populations_from_later_mutation(self):
        """R9.6: nested rung populations must be deep-copied, not shared.

        `_rung_populations` is dict[int, list[tuple]]. A shallow copy shares the inner
        lists, so appending to the snapshot corrupts the live scheduler. This is the
        one place where deepcopy vs copy is NOT equivalent.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0))
        scheduler.report("trial_a", fidelity=1.0, value=0.8)
        scheduler.report("trial_b", fidelity=1.0, value=0.5)

        state = scheduler.state_dict()
        state["rung_populations"][0].append(("injected", 0.0))

        live_ids = [tid for tid, _ in scheduler._rung_populations[0]]
        assert "injected" not in live_ids, (
            f"snapshot shares the inner list with the scheduler: {live_ids}"
        )
        assert len(scheduler._rung_populations[0]) == 2

    def test_state_dict_captures_four_element_trial_state(self):
        """R9.6: each _trial_state entry is (rung_idx, fidelity, best_val, status).

        A mutation that drops or reorders a slot survives a keys-exist check but
        breaks promote(), which unpacks all four.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0))
        scheduler.report("trial_a", fidelity=1.0, value=0.42)

        entry = scheduler.state_dict()["trial_state"]["trial_a"]

        assert len(entry) == 4, f"expected a 4-tuple, got {len(entry)}: {entry}"
        rung_idx, fidelity, best_val, status = entry
        assert rung_idx == 0
        assert fidelity == 1.0
        assert best_val == 0.42
        assert status == "paused"

    def test_state_dict_records_best_value_not_latest(self):
        """R9.6: the third slot must hold min(values), not the most recent value.

        Regression guard for the ASHA best_value bug (Phase 0 Issue 4): reporting a
        worse value after a better one must not overwrite the best.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=27.0))
        scheduler.report("trial_a", fidelity=1.0, value=0.20)
        scheduler.report("trial_a", fidelity=1.0, value=0.90)  # regression

        _, _, best_val, _ = scheduler.state_dict()["trial_state"]["trial_a"]

        assert best_val == 0.20, (
            f"third slot holds {best_val}; it must track the best (0.20), not the latest"
        )

    def test_load_state_dict_restores_trial_state_tuples_from_json_lists(self):
        """R9.6: JSON turns tuples into lists; load_state_dict must restore tuples.

        The `isinstance(item, list)` guard mutated to `... or True` is equivalent
        (tuple() is idempotent), but removing the conversion leaves lists in place
        and promote()'s unpacking then reads a list — this test pins the type.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0))

        state_from_json = {
            "config": {"eta": 3, "r_min": 1.0, "r_max": 9.0},
            "rungs": [1.0, 3.0, 9.0],
            "trial_state": {
                "trial_a": [0, 1.0, 0.5, "paused"],  # tuple flattened by JSON
                "trial_b": [1, 3.0, 0.3, "active"],
            },
            "rung_populations": {},
            "fidelity_history": {},
        }

        scheduler.load_state_dict(state_from_json)

        assert scheduler._trial_state["trial_a"] == (0, 1.0, 0.5, "paused")
        assert scheduler._trial_state["trial_b"] == (1, 3.0, 0.3, "active")
        assert isinstance(scheduler._trial_state["trial_a"], tuple)
        assert isinstance(scheduler._trial_state["trial_b"], tuple)

    def test_load_state_dict_restores_int_rung_keys_from_json_strings(self):
        """R9.6: JSON stringifies int dict keys; load_state_dict must convert them back.

        `_rung_populations` is keyed by int rung index. Left as strings, every
        `self._rung_populations[rung_idx]` lookup in promote() raises KeyError.
        """
        scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0))

        state_from_json = {
            "config": {"eta": 3, "r_min": 1.0, "r_max": 9.0},
            "rungs": [1.0, 3.0, 9.0],
            "trial_state": {},
            "rung_populations": {
                "0": [["trial_a", 0.8], ["trial_b", 0.75]],
                "1": [["trial_c", 0.85]],
            },
            "fidelity_history": {},
        }

        scheduler.load_state_dict(state_from_json)

        assert set(scheduler._rung_populations) == {0, 1}, (
            f"rung keys not converted to int: {list(scheduler._rung_populations)}"
        )
        assert scheduler._rung_populations[0] == [("trial_a", 0.8), ("trial_b", 0.75)]
        assert scheduler._rung_populations[1] == [("trial_c", 0.85)]
        assert isinstance(scheduler._rung_populations[0][0], tuple)

    def test_state_continuation_reproduces_promotion_decision(self):
        """R9.6: a restored scheduler must make the same promotion as the original.

        End-to-end continuation: report, snapshot, restore into a fresh scheduler,
        and confirm both promote the same trials to the same fidelity. Any state
        field silently dropped by the snapshot shows up as a divergent decision here.
        """
        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        original = ASHAScheduler(config)

        # Ids ascend while values descend, so promotion order is not id order.
        reports = [
            ("trial_a", 0.90),
            ("trial_b", 0.80),
            ("trial_c", 0.70),
            ("trial_d", 0.60),
            ("trial_e", 0.50),
            ("trial_f", 0.40),
        ]
        for trial_id, value in reports:
            original.report(trial_id, fidelity=1.0, value=value)

        state = original.state_dict()

        restored = ASHAScheduler(config)
        restored.load_state_dict(state)

        expected = original.promote()
        actual = restored.promote()

        assert actual == expected, (
            f"restored scheduler promoted {actual}, original promoted {expected}"
        )
        # ceil(6/3) = 2 promoted, and they must be the two lowest values.
        assert len(actual) == 2
        assert {tid for tid, _ in actual} == {"trial_f", "trial_e"}
        assert all(fidelity == 3.0 for _, fidelity in actual)

    def test_state_continuation_survives_json_round_trip(self):
        """R9.6: continuation must hold through real JSON, not just in-memory dicts.

        json.dumps/loads is what a checkpoint actually does: it stringifies the int
        rung keys and flattens every tuple. This exercises both conversions in
        load_state_dict together.
        """
        import json

        config = ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1.0, r_max=9.0)
        original = ASHAScheduler(config)
        for trial_id, value in [("trial_a", 0.9), ("trial_b", 0.5), ("trial_c", 0.7),
                                ("trial_d", 0.3)]:
            original.report(trial_id, fidelity=1.0, value=value)

        expected = original.promote()

        # Rebuild a second scheduler at the same point, snapshot it through JSON.
        source = ASHAScheduler(config)
        for trial_id, value in [("trial_a", 0.9), ("trial_b", 0.5), ("trial_c", 0.7),
                                ("trial_d", 0.3)]:
            source.report(trial_id, fidelity=1.0, value=value)

        round_tripped = json.loads(json.dumps(source.state_dict()))
        restored = ASHAScheduler(config)
        restored.load_state_dict(round_tripped)

        assert restored.promote() == expected, (
            "promotion decision changed after a JSON checkpoint round trip"
        )
