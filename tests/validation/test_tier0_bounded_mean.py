"""Independent finite-support proofs/checks for the batch mean candidate."""

import itertools
import math

import numpy as np
import pytest

from validation.tier0_bounded_mean import bounded_mean_evidence, bounded_mean_lower_bound, preview_bounded_family
from validation.tier0_inference import require_acceptance_inference


def test_closed_form_positive_sample_and_adverse_boundary():
    data = [.1] * 60
    # Integral_0^1 (1 + .1*lambda)^60 d lambda, evaluated independently.
    expected = (1.1**61 - 1) / (6.1)
    result = bounded_mean_evidence(data)
    assert result["log_e_value"] == pytest.approx(math.log(expected))
    assert result["p_value"] == pytest.approx(1 / expected)
    assert result["p_value"] < .025
    assert result["mixture"] == "uniform_0_1"
    assert bounded_mean_evidence([-1], fractions=(1,))["zero_e_value"]
    assert bounded_mean_evidence([-1], fractions=(1,))["p_value"] == 1
    assert bounded_mean_evidence([0] * 5)["p_value"] == 1
    assert bounded_mean_evidence([-1] * 20)["log_e_value"] == pytest.approx(-math.log(21))


def test_exact_expectation_under_heterogeneous_global_mean_null():
    # Some independent units have positive means, others negative. Per-task
    # nonpositivity and identical distributions are not required by AM-GM.
    for probabilities in ((.9, .7, .3, .1), (.99, .01, .25, .25), (.5,) * 4):
        expected_e = 0.0
        for row in itertools.product((-1, 1), repeat=4):
            probability = math.prod(p if x == 1 else 1-p for x, p in zip(row, probabilities))
            log_e = bounded_mean_evidence(row)["log_e_value"]
            expected_e += probability * (math.exp(log_e) if log_e is not None else 0)
        assert expected_e <= 1 + 1e-12


@pytest.mark.parametrize("gain", [.01, .1, .5, 1.0])
def test_exact_composite_boundary_error_with_skew_and_rare_losses(gain):
    # The null is X in {-1, gain}, P(X=gain)=1/(1+gain).
    # Enumerating success counts is exact and requires no bootstrap/Monte Carlo.
    n, p = 60, 1 / (1 + gain)
    errors = {alpha: 0.0 for alpha in (.025, .05)}
    for wins in range(n + 1):
        probability = math.comb(n, wins) * p**wins * (1-p)**(n-wins)
        test = bounded_mean_evidence([gain]*wins + [-1]*(n-wins))
        for alpha in errors:
            errors[alpha] += probability * (test["p_value"] <= alpha)
    assert all(error <= alpha + 1e-12 for alpha, error in errors.items())


def test_eight_component_iut_veto_and_missing_family_member():
    v04 = np.full((60, 8), .2)
    v05 = np.full((60, 1), .2)
    good = preview_bounded_family({"V04-T0": v04, "V05": v05})
    assert all(e["candidate_clears"] for e in good["entries"].values())
    assert not good["certifies_acceptance"]
    assert all(e["verdict"] == "INCONCLUSIVE" for e in good["entries"].values())
    v04[:, -1] = 0
    veto = preview_bounded_family({"V04-T0": v04, "V05": v05})
    assert not veto["entries"]["V04-T0"]["candidate_clears"]
    isolated = preview_bounded_family({"V05": v05})["entries"]["V05"]
    assert isolated["family"]["adjusted_alpha"] == .025
    with pytest.raises(ValueError, match="Every registered component"):
        preview_bounded_family({"V04-T0": v04[:, :7]})


def test_partial_null_family_error_by_exact_boundary_enumeration():
    n, gain = 20, .5
    p, fwer = 1 / (1 + gain), 0.0
    for wins in range(n + 1):
        # V05 and seven V04 components have large positive effects. The last
        # V04 component is null, so falsely clearing V04 is the family error.
        v04 = np.ones((n, 8))
        v04[:, -1] = [gain]*wins + [-1]*(n-wins)
        result = preview_bounded_family({"V04-T0": v04, "V05": np.ones((n, 1))})
        if result["entries"]["V04-T0"]["candidate_clears"]:
            fwer += math.comb(n, wins) * p**wins * (1-p)**(n-wins)
    assert fwer <= .05


def test_correlated_copies_are_not_independent_evidence():
    # One fair +/-1 coin copied 20 times violates the contract: expected E > 1.
    # Keep this counterexample so merely adding task labels cannot justify n.
    plus = bounded_mean_evidence([1] * 20)
    minus = bounded_mean_evidence([-1] * 20)
    assert .5 * (math.exp(plus["log_e_value"]) + math.exp(minus["log_e_value"])) > 1


def test_confidence_bound_inverts_the_batch_mean_test():
    data = [.1] * 60
    lower = bounded_mean_lower_bound(data)
    assert 0 < lower < .1
    assert bounded_mean_evidence(data, null_mean=lower)["p_value"] <= .025 * (1 + 1e-12)
    assert bounded_mean_evidence(data, null_mean=lower + .0001)["p_value"] > .025
    assert bounded_mean_lower_bound([-1] * 5) == -1
    assert bounded_mean_lower_bound(data, alpha=.01) < lower


def test_nonzero_mean_interval_has_exact_boundary_coverage():
    n, probability, misses = 20, .75, 0.0
    mean = 2 * probability - 1
    for wins in range(n + 1):
        lower = bounded_mean_lower_bound([1]*wins + [-1]*(n-wins))
        if lower > mean:
            misses += math.comb(n, wins) * probability**wins * (1-probability)**(n-wins)
    assert misses <= .025


def test_reviewed_mathematics_does_not_certify_unfinished_task_assumptions():
    with pytest.raises(ValueError, match="no validated acceptance replacement"):
        require_acceptance_inference({"method": "fixed_count_bounded_mean_mixture_e_v1"})


@pytest.mark.parametrize("values,fractions", [
    ([], (.5,)), ([math.nan], (.5,)), ([math.inf], (.5,)), ([1.01], (.5,)),
    ([-1.01], (.5,)), ([True], (.5,)), ([".1"], (.5,)),
    ([[.1]], (.5,)), ([.1], ()), ([.1], (1.1,)), ([.1], (.5, .5)),
])
def test_ineligible_inputs_are_not_clipped_or_coerced(values, fractions):
    with pytest.raises(ValueError):
        bounded_mean_evidence(values, fractions=fractions)
