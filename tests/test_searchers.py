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

    The spike searcher handles continuous axes only, and must say so.
    """
    caps = SobolSearcher(_two_axis_space(), seed=0).capabilities
    assert caps["knob_kinds"] == ["continuous"]
    assert caps["conditionals"] is False
    assert caps["multi_objective"] is False
    assert caps["prior"] is False
    assert caps["max_dim"] >= 2


def test_ordinal_and_categorical_axes_ignored_in_spike():
    """
    Spike limitation, asserted rather than assumed: non-continuous axes are dropped.

    Tier 0 replaces this with integer Sobol columns for ordinals and a categorical
    treatment; this test is expected to change then, which is the point of pinning it now.
    """
    space = _two_axis_space()
    space.add_knob(Knob(name="width", kind="ordinal", bounds=(32, 512)))
    space.add_knob(
        Knob(name="activation", kind="categorical", bounds=["relu", "tanh"])
    )

    config = SobolSearcher(space, seed=0).propose(1)[0]

    assert set(config) == {"x", "y"}
    assert "width" not in config
    assert "activation" not in config


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
    Refusing early is cheaper than diagnosing a silently degenerate study (Ch 15).

    A space the spike searcher cannot model must fail at construction, not at proposal time.
    """
    space = SearchSpace()
    space.add_knob(Knob(name="width", kind="ordinal", bounds=(32, 512)))

    with pytest.raises(ValueError, match="no continuous knobs"):
        SobolSearcher(space, seed=0)
