"""
Property tests for scheduler async correctness (V02 validation).

Validation coverage:
- V02: Scheduler logic correct under asynchrony
- Out-of-order events, duplicates, late arrivals, stragglers

Test strategy:
- Generate random event sequences
- Check invariants hold regardless of ordering
- Verify no silent corruption under async stress

Property-based testing uses hypothesis to generate test cases.
"""

import pytest
from hypothesis import given, strategies as st

from hponas.schedulers import ASHAScheduler, PASHAScheduler, ASHAConfig, PASHAConfig


# Strategy: generate trial events (trial_id, fidelity, value)
@st.composite
def trial_events(draw, n_trials=st.integers(3, 10), n_rungs=st.integers(2, 4)):
    """Generate random trial event sequences."""
    num_trials = draw(n_trials)
    num_rungs = draw(n_rungs)

    # Generate rungs
    rungs = [1.0]
    for _ in range(num_rungs - 1):
        rungs.append(rungs[-1] * 3)

    # Generate events
    events = []
    for i in range(num_trials):
        trial_id = f"trial_{i}"
        rung_idx = draw(st.integers(0, num_rungs - 1))
        fidelity = rungs[rung_idx]
        value = draw(st.floats(0.0, 1.0))
        events.append((trial_id, fidelity, value))

    return events, rungs


@given(trial_events())
def test_asha_invariant_no_promotion_without_pause(data):
    """Property: ASHA never promotes a trial that wasn't paused."""
    events, rungs = data

    config = ASHAConfig(eta=3, r_min=rungs[0], r_max=rungs[-1])
    scheduler = ASHAScheduler(config)

    paused_trials = set()

    for trial_id, fidelity, value in events:
        decision = scheduler.report(trial_id, fidelity, value)
        if decision == "pause":
            paused_trials.add(trial_id)

    # Promote
    promotions = scheduler.promote()
    promoted_ids = {trial_id for trial_id, _ in promotions}

    # Invariant: every promoted trial was paused
    assert promoted_ids.issubset(paused_trials), \
        f"Promoted trials {promoted_ids - paused_trials} were never paused"


@given(trial_events())
def test_asha_invariant_monotonic_fidelity(data):
    """Property: ASHA never promotes to lower fidelity."""
    events, rungs = data

    config = ASHAConfig(eta=3, r_min=rungs[0], r_max=rungs[-1])
    scheduler = ASHAScheduler(config)

    # Report all events
    for trial_id, fidelity, value in events:
        scheduler.report(trial_id, fidelity, value)

    # Save state before promote() modifies it
    state_before = {tid: state for tid, state in scheduler._trial_state.items()}

    # Check promotions
    promotions = scheduler.promote()

    for trial_id, next_fidelity in promotions:
        # Get current fidelity from saved state
        if trial_id in state_before:
            current_rung, current_fidelity, _, _ = state_before[trial_id]

            # Invariant: promoted fidelity > current fidelity
            assert next_fidelity > current_fidelity, \
                f"Trial {trial_id} promoted from {current_fidelity} to {next_fidelity} (non-monotonic)"


@given(st.lists(st.integers(0, 100), min_size=3, max_size=20))
def test_asha_out_of_order_commutative(indices):
    """Property: ASHA ranking is order-independent (commutative)."""
    config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)

    # Create two schedulers
    scheduler_A = ASHAScheduler(config)
    scheduler_B = ASHAScheduler(config)

    # Same trials, different arrival order
    trials = [(f"trial_{i}", 1.0, i * 0.1) for i in range(len(indices))]

    # Scheduler A: sequential order
    for trial_id, fidelity, value in trials:
        scheduler_A.report(trial_id, fidelity, value)

    # Scheduler B: permuted order (use indices as permutation, wrapping with modulo)
    # To avoid duplicates, we use indices to define an ordering, not to select trials
    order = sorted(range(len(trials)), key=lambda i: indices[i])
    permuted = [trials[i] for i in order]
    for trial_id, fidelity, value in permuted:
        scheduler_B.report(trial_id, fidelity, value)

    # Rankings should be identical
    pop_A = sorted(scheduler_A._rung_populations[0], key=lambda x: x[1])
    pop_B = sorted(scheduler_B._rung_populations[0], key=lambda x: x[1])

    # Extract trial IDs in rank order
    rank_A = [tid for tid, _ in pop_A]
    rank_B = [tid for tid, _ in pop_B]

    assert rank_A == rank_B, "Rankings differ under permutation"


@given(st.integers(1, 20))
def test_asha_duplicate_idempotent(n_duplicates):
    """Property: Duplicate reports don't corrupt state."""
    config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
    scheduler = ASHAScheduler(config)

    trial_id = "trial_dup"
    fidelity = 1.0
    value = 0.5

    # Report same trial multiple times
    decisions = []
    for _ in range(n_duplicates):
        decision = scheduler.report(trial_id, fidelity, value)
        decisions.append(decision)

    # All decisions should be valid
    assert all(d in ["continue", "stop", "pause"] for d in decisions)

    # State should be consistent (trial exists exactly once in state dict)
    assert trial_id in scheduler._trial_state

    # Population should track the trial (list of tuples now)
    trial_ids_in_pop = [tid for tid, _ in scheduler._rung_populations[0]]
    assert trial_id in trial_ids_in_pop


@given(st.integers(5, 20), st.floats(0.0, 1.0))
def test_pasha_budget_never_exceeded(n_trials, budget):
    """Property: PASHA never exceeds promotion budget."""
    config = PASHAConfig(eta=3, r_min=1.0, r_max=27.0, promotion_budget=budget)
    scheduler = PASHAScheduler(config)

    # Report trials
    for i in range(n_trials):
        scheduler.report(f"trial_{i}", fidelity=1.0, value=i * 0.1)

    # Promote
    initial_budget = scheduler._budget_spent
    promotions = scheduler.promote()
    final_budget = scheduler._budget_spent

    # Invariant: budget never exceeded
    assert final_budget <= config.promotion_budget, \
        f"Budget exceeded: {final_budget} > {config.promotion_budget}"

    # Invariant: budget only increases
    assert final_budget >= initial_budget, \
        f"Budget decreased: {final_budget} < {initial_budget}"


@given(st.lists(st.tuples(st.text(min_size=1, max_size=10), st.floats(0.0, 1.0)), min_size=1, max_size=10))
def test_asha_straggler_stability(events):
    """Property: Late arrivals don't break scheduler state."""
    config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
    scheduler = ASHAScheduler(config)

    # Process events in order
    for trial_id, value in events:
        try:
            decision = scheduler.report(trial_id, fidelity=1.0, value=value)
            assert decision in ["continue", "stop", "pause"]
        except Exception as e:
            pytest.fail(f"Scheduler crashed on event ({trial_id}, {value}): {e}")

    # Scheduler should still be callable
    try:
        promotions = scheduler.promote()
        assert isinstance(promotions, list)
    except Exception as e:
        pytest.fail(f"Scheduler crashed on promote(): {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
