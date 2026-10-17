"""Finite support and an adverse real Study, without empirical recovery claims.

All original legacy-sampler assertions, including passes, remain runnable under
docs/program/evidence/2026-10-08/integrated-repair-01/legacy-prior-diagnostics.
Pinned policy, distribution and checkpoint conformance have separate tests.
"""
from fractions import Fraction

from hponas import (
    CategoricalPriorBandSearcher, Knob, LocalExecutor, PriorBandScheduler,
    SearchSpace, Study,
)


def test_positive_support_does_not_guarantee_a_good_finite_recommendation():
    searcher = CategoricalPriorBandSearcher(
        SearchSpace([Knob("x", "categorical", [0, 1])]),
        {"x": 0}, rungs=[1], eta=2, confidence="high", seed=0,
    )
    # The prior still assigns exactly 1/7 to the true optimum x=1.
    assert searcher.law.prior_masses() == (Fraction(6, 7), Fraction(1, 7))
    result = Study(
        searcher, LocalExecutor(), lambda config: (config["x"] - 1) ** 2,
        budget=1, maximize=False,
        scheduler=PriorBandScheduler(rungs=[1], eta=2, default_at_target=True),
    ).run()
    # The protocol's first default evaluation has known regret 1, despite
    # positive sampling support everywhere. This is an adverse outcome.
    assert result.n_trials == 1
    assert result.history[0].objective_value == result.best_value == 1
    assert searcher.policy.resources() == result.total_cost
