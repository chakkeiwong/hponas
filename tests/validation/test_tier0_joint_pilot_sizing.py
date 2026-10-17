"""Joint-event proof boundaries and adversarial retained pilot vectors."""

from fractions import Fraction
import math

import pytest
from scipy.stats import binom

from validation.tier0_bounded_mean import bounded_mean_evidence
from validation.tier0_design import load_design
from validation.tier0_joint_pilot_sizing import THRESHOLD, exact_event_e, good_probability_lower, required_good_vectors
from validation.tier0_phase_contracts import SIZING_POLICY
from validation.tier0_pilot_sizing import ideal_pilot_screen, size_pilot_vectors


def test_derived_event_threshold_is_exact_and_not_an_acceptance_margin():
    assert THRESHOLD == Fraction(84, 125)
    assert exact_event_e(18, 2) >= 40
    assert exact_event_e(18, 2, THRESHOLD - Fraction(1, 1000)) < 40
    assert all(value == 0 for entry in load_design()["margins"].values() for value in entry.values())


def test_joint_event_guarantees_every_component_and_loss_veto_together():
    for count in range(5, 21):
        good = required_good_vectors(count)
        if good is not None:
            assert count - good <= count // 10
            assert bounded_mean_evidence([float(THRESHOLD)] * good + [-1.] * (count - good))["p_value"] <= .025
            assert exact_event_e(good, count - good) >= 40
            if good > count - count // 10:
                assert exact_event_e(good - 1, count - good + 1) < 40
    assert required_good_vectors(20) == 18
    assert required_good_vectors(10) is None


def test_exact_confidence_coverage_on_binary_boundary_laws():
    for n in (5, 20, 45, 46):
        bounds = [good_probability_lower(g, n) for g in range(n + 1)]
        for p in (.2, .5, .8, .92, .95, .99):
            error = sum(float(binom.pmf(g, n, p)) for g, bound in enumerate(bounds) if bound > p)
            assert error <= .025 + 1e-12
    assert good_probability_lower(46, 46) == pytest.approx(.025 ** (1 / 46))


def test_ideal_46_vectors_can_size_but_45_cannot():
    grid = load_design()["budget_grid"]
    assert ideal_pilot_screen(45, grid)["verdict"] == "INFEASIBLE_UNDER_RULE"
    report = ideal_pilot_screen(46, grid)
    assert report["verdict"] == "SIZED"
    assert all(row["chosen_n"] == 20 for row in report["entries"].values())
    assert not report["certifies_acceptance"]


@pytest.mark.parametrize("fault", ["one_component", "loss", "moderate"])
def test_every_joint_component_and_retained_failure_matters(fault):
    rows = {"V04-T0": [[1., .99] * 4 for _ in range(46)], "V05": [[1.] for _ in range(46)]}
    lost = {entry: [False] * 46 for entry in rows}
    if fault == "one_component":
        rows["V04-T0"][0][0] = math.nextafter(float(THRESHOLD), 0.)
    elif fault == "loss":
        lost["V04-T0"][0] = True
    else:
        rows["V04-T0"] = [[.5] * 8 for _ in range(46)]
    report = size_pilot_vectors(rows, lost, load_design()["budget_grid"], policy=SIZING_POLICY)
    assert report["entries"]["V04-T0"]["chosen_n"] is None
    assert report["entries"]["V05"]["chosen_n"] == 20
    assert report["entries"]["V04-T0"]["pilot_vectors"] == 46


def test_coarse_anytime_grid_cannot_manufacture_jointly_good_vectors():
    report = ideal_pilot_screen(1000, [0, .5, 1])
    assert report["entries"]["V04-T0"]["good_vectors"] == 0
    assert report["verdict"] == "INFEASIBLE_UNDER_RULE"
