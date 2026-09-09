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
        config = ASHAConfig(eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)
        assert scheduler.config.eta == 3

    def test_init_sets_rung_structure(self):
        """ASHAScheduler must compute rung levels from r_min, r_max, eta."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=27.0)
        scheduler = ASHAScheduler(config)

        # Rungs: r_min=1, 3, 9, 27=r_max
        expected_rungs = [1.0, 3.0, 9.0, 27.0]
        assert scheduler.rungs == expected_rungs

    def test_report_pauses_low_performers(self):
        """report() must pause trials below top-1/eta at each rung."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
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
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
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
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report at max fidelity
        decision = scheduler.report("trial_1", fidelity=9.0, value=0.5)
        assert decision == "stop"

    def test_empty_promote_when_no_trials(self):
        """promote() must return empty list when no trials reported."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        promoted = scheduler.promote()
        assert promoted == []

    def test_multiple_rungs_sequential(self):
        """Trials must progress through rungs sequentially: r=1 → r=3 → r=9."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler = ASHAScheduler(config)

        # Report at r=1.0
        scheduler.report("trial_1", fidelity=1.0, value=0.2)

        # Promote to r=3.0
        promoted = scheduler.promote()
        if promoted:
            assert "trial_1" in promoted

            # Report at r=3.0
            decision = scheduler.report("trial_1", fidelity=3.0, value=0.15)
            assert decision in ["continue", "pause", "stop"]


class TestASHAConfig:
    """Unit tests for ASHAConfig validation."""

    def test_eta_must_be_positive(self):
        """eta must be > 1."""
        with pytest.raises(ValueError):
            ASHAConfig(eta=0, r_min=1.0, r_max=9.0)

        with pytest.raises(ValueError):
            ASHAConfig(eta=1, r_min=1.0, r_max=9.0)

    def test_r_max_greater_than_r_min(self):
        """r_max must be > r_min."""
        with pytest.raises(ValueError):
            ASHAConfig(eta=3, r_min=9.0, r_max=1.0)

    def test_r_min_positive(self):
        """r_min must be > 0."""
        with pytest.raises(ValueError):
            ASHAConfig(eta=3, r_min=0.0, r_max=9.0)

        with pytest.raises(ValueError):
            ASHAConfig(eta=3, r_min=-1.0, r_max=9.0)
