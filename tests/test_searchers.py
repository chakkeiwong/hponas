"""
Test SobolSearcher: proposal determinism, log-transform handling, capability declaration.

Survey reference: Ch 3 (Sobol and log sampling), Ch 15 sec:searcher-interface.
R1 spike exit criterion: same seed produces same proposals; capabilities declared honestly.
"""

import numpy as np
import pytest

from hponas.searchers import SobolSearcher
from hponas.space import Knob, SearchSpace


def _two_axis_space() -> SearchSpace:
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))
    return space


def test_propose_returns_requested_count():
    """Batch proposals are the normal case, not the extension (Ch 15)."""
    searcher = SobolSearcher(_two_axis_space(), seed=0)
    configs = searcher.propose(8)
    assert len(configs) == 8
    assert all(set(c) == {"x", "y"} for c in configs)


def test_proposals_within_bounds():
    """Every proposed value lies inside its knob's declared bounds."""
    searcher = SobolSearcher(_two_axis_space(), seed=3)
    for config in searcher.propose(32):
        assert -5.0 <= config["x"] <= 10.0
        assert 0.0 <= config["y"] <= 15.0


def test_proposal_determinism_same_seed():
    """Same seed produces identical proposals: the spike's determinism criterion."""
    a = SobolSearcher(_two_axis_space(), seed=42).propose(16)
    b = SobolSearcher(_two_axis_space(), seed=42).propose(16)
    assert a == b


def test_proposal_differs_across_seeds():
    """Different seeds explore differently, or the scramble is not doing its job."""
    a = SobolSearcher(_two_axis_space(), seed=1).propose(16)
    b = SobolSearcher(_two_axis_space(), seed=2).propose(16)
    assert a != b


def test_sequence_advances_between_calls():
    """Successive propose() calls continue the sequence rather than restarting it."""
    searcher = SobolSearcher(_two_axis_space(), seed=7)
    first = searcher.propose(4)
    second = searcher.propose(4)
    assert first != second


def test_log_transform_spans_decades():
    """
    Log-uniform sampling spends its budget per decade, not per unit (Ch 3).

    The survey's argument for log sampling is that a uniform draw wastes 90 percent of
    its samples in the top decade; this checks the transform actually reaches the bottom one.
    """
    space = SearchSpace()
    space.add_knob(
        Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2), transform="log")
    )
    values = [c["lr"] for c in SobolSearcher(space, seed=0).propose(64)]

    assert all(1e-5 <= v <= 1e-2 for v in values)
    # A uniform draw would almost never land below 1e-4; a log draw routinely does.
    assert any(v < 1e-4 for v in values)
    assert any(v > 1e-3 for v in values)


def test_log_transform_median_is_geometric():
    """Log sampling puts its median near the geometric mean, not the arithmetic one."""
    space = SearchSpace()
    space.add_knob(
        Knob(name="lr", kind="continuous", bounds=(1e-6, 1e-2), transform="log")
    )
    values = np.array([c["lr"] for c in SobolSearcher(space, seed=11).propose(256)])

    geometric_mean = np.sqrt(1e-6 * 1e-2)  # 1e-4
    arithmetic_mean = (1e-6 + 1e-2) / 2
    median = float(np.median(values))

    assert abs(np.log10(median) - np.log10(geometric_mean)) < 0.3
    assert median < arithmetic_mean


def test_observe_is_accepted_and_ignored():
    """Sobol is model-free: observe() must be callable and must change nothing (Ch 3)."""
    searcher = SobolSearcher(_two_axis_space(), seed=5)
    baseline = SobolSearcher(_two_axis_space(), seed=5)

    searcher.observe({"config": {"x": 0.0, "y": 0.0}, "value": 0.0})

    assert searcher.propose(4) == baseline.propose(4)


def test_capabilities_declared_honestly():
    """
    The capability flag exists because the Ch 10 audit found mismatches shipping silently.

    Tier 0: Sobol handles continuous, ordinal, and categorical axes.
    """
    caps = SobolSearcher(_two_axis_space(), seed=0).capabilities
    assert caps["knob_kinds"] == ["continuous", "ordinal", "categorical"]
    assert caps["conditionals"] is False
    assert caps["multi_objective"] is False
    assert caps["prior"] is False
    assert caps["max_dim"] >= 2


def test_ordinal_and_categorical_axes_ignored_in_spike():
    """
    Tier 0: Sobol now handles ordinal and categorical axes.

    Ordinals use integer Sobol columns, categoricals use mapped Sobol values.
    """
    space = _two_axis_space()
    space.add_knob(Knob(name="width", kind="ordinal", bounds=(32, 512)))
    space.add_knob(
        Knob(name="activation", kind="categorical", bounds=["relu", "tanh"])
    )

    config = SobolSearcher(space, seed=0).propose(1)[0]

    # Tier 0: all knobs are sampled
    assert set(config) == {"x", "y", "width", "activation"}

    # Check types
    assert isinstance(config["x"], float)
    assert isinstance(config["y"], float)
    assert isinstance(config["width"], int)
    assert config["activation"] in ["relu", "tanh"]


def test_conditional_axes_excluded_from_spike_proposals():
    """Conditional knobs are skipped: the spike declares conditionals unsupported."""
    space = _two_axis_space()
    space.add_knob(Knob(name="anneal", kind="categorical", bounds=[True, False]))
    space.add_knob(
        Knob(
            name="lr_final",
            kind="continuous",
            bounds=(1e-6, 1e-3),
            condition=("anneal", True),
        )
    )

    config = SobolSearcher(space, seed=0).propose(1)[0]
    assert "lr_final" not in config


def test_space_without_continuous_axes_is_refused():
    """
    Tier 0: Sobol now accepts ordinal-only and categorical-only spaces.

    The spike limitation of requiring at least one continuous axis is lifted.
    """
    space = SearchSpace()
    space.add_knob(Knob(name="width", kind="ordinal", bounds=(32, 512)))

    # Should not raise
    searcher = SobolSearcher(space, seed=0)
    config = searcher.propose(1)[0]

    assert "width" in config
    assert isinstance(config["width"], int)
    assert 32 <= config["width"] <= 512


def test_state_dict_round_trip_continues_sequence():
    """
    Crash recovery contract: state_dict + load_state_dict restores sequence position.

    A searcher rebuilt from state continues the QMC sequence instead of restarting it.
    """
    space = _two_axis_space()

    a = SobolSearcher(space, seed=42)
    first_3 = a.propose(3)
    state = a.state_dict()
    next_3_from_a = a.propose(3)

    # Rebuild from state
    b = SobolSearcher(space, seed=42)
    b.load_state_dict(state)
    next_3_from_b = b.propose(3)

    # b should continue where a left off (after first_3), not restart
    assert next_3_from_b == next_3_from_a
    # Sanity: b didn't just reemit first_3
    assert next_3_from_b != first_3


def test_state_dict_survives_json_round_trip():
    """State dict is JSON-serializable (crash recovery persists to disk)."""
    import json

    space = _two_axis_space()
    a = SobolSearcher(space, seed=99)
    a.propose(5)

    state = a.state_dict()
    json_str = json.dumps(state)
    recovered = json.loads(json_str)

    b = SobolSearcher(space, seed=99)
    b.load_state_dict(recovered)

    # Same sequence continuation
    assert a.propose(4) == b.propose(4)


def test_state_dict_refuses_mismatched_space():
    """load_state_dict validates space compatibility before restoring."""
    space_a = _two_axis_space()
    space_b = SearchSpace()
    space_b.add_knob(Knob(name="a", kind="continuous", bounds=(0.0, 1.0)))
    space_b.add_knob(Knob(name="b", kind="continuous", bounds=(0.0, 1.0)))

    s_a = SobolSearcher(space_a, seed=1)
    s_a.propose(2)
    state = s_a.state_dict()

    s_b = SobolSearcher(space_b, seed=1)
    with pytest.raises(ValueError, match="state does not match space"):
        s_b.load_state_dict(state)


def test_state_dict_refuses_wrong_searcher_kind():
    """State from one searcher kind cannot be loaded into another (type safety)."""
    space = _two_axis_space()
    s = SobolSearcher(space, seed=1)
    s.propose(2)

    state = s.state_dict()
    state["kind"] = "tpe"  # Fake a different searcher's state

    s2 = SobolSearcher(space, seed=1)
    with pytest.raises(ValueError, match="cannot load state of kind"):
        s2.load_state_dict(state)
