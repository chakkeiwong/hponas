"""Mathematical optima, adverse regimes and independent raw-output checks."""
from copy import deepcopy
from fractions import Fraction as F
import math

import numpy as np
import pytest

from workloads.stylized import case_specs, evaluate, get_case, validate_config
from validation.stylized_reference import optimum, reference_value, verify_observation
from validation.stylized_campaign import probes


@pytest.mark.parametrize("case", case_specs(), ids=lambda c: c["id"])
def test_model_outputs_at_optimum_boundaries_and_interior(case):
    for config in probes(case):
        checked = verify_observation(case, config, evaluate(case["id"], config))
        assert checked["regret"] >= -checked["numerical_allowance"]
    solution = optimum(case)
    checked = verify_observation(case, solution["config"], evaluate(case["id"], solution["config"]))
    assert abs(checked["regret"]) <= checked["numerical_allowance"]


def test_exact_ridge_global_regret_identity():
    # Algebraic identity, evaluated with rational arithmetic at disparate scales.
    for variance in [F(1, 2), F(2), F(8), F(16)]:
        n, noise = 8, F(2)
        best = noise/variance
        for penalty in [F(1, 1000), F(1, 4), F(1), F(4), F(100)]:
            risk = (variance*penalty**2 + n*noise)/(n+penalty)**2
            regret = n*variance*(penalty-best)**2/((n+penalty)**2*(n+best))
            assert risk-noise/(n+best) == regret >= 0
    assert optimum(get_case("ridge-a"))["value"] == float(F(125, 198))


def test_filter_global_regret_and_actual_noise_recursion():
    q, r, best, gain = F(1), F(6), F(2), F(1, 3)
    for k in [F(1, 100), F(1, 4), gain, F(3, 4), F(99, 100)]:
        variance = ((1-k)**2*q+k*k*r)/(k*(2-k))
        assert variance-best == (best+q+r)*(k-gain)**2/(k*(2-k))
    # Independent cubature of a finite noise path tests the state/filter model.
    steps = 4
    points = np.vstack([np.eye(2*steps), -np.eye(2*steps)])*math.sqrt(2*steps)
    state = np.zeros(len(points))
    estimate = state.copy()
    covariance = 0.
    for t in range(steps):
        state += points[:, 2*t]
        estimate = (1-float(gain))*estimate+float(gain)*(state+math.sqrt(6)*points[:, 2*t+1])
        covariance = (1-float(gain))**2*(covariance+1)+float(gain)**2*6
        assert np.mean((state-estimate)**2) == pytest.approx(covariance, abs=1e-14)
    assert covariance < 2  # Finite-horizon covariance is not the stationary optimum.


def test_quadratic_unstable_rate_and_bottleneck_tradeoff():
    case = get_case("quadratic-a")
    assert optimum(case)["value"] == float(F(65536, 390625))
    assert reference_value(case, {"eta": 1/3}) > 1
    assert [evaluate("bottleneck-a", {"width": h})["value"] for h in range(1, 5)] == pytest.approx(
        [5.75, 2.25, 1.75, 2.])
    assert optimum(get_case("bottleneck-b"))["config"] == {"width": 2}


@pytest.mark.parametrize("case", case_specs(), ids=lambda c: c["id"])
def test_oracle_rejects_corrupted_objective_work_and_payload(case):
    config = optimum(case)["config"]
    original = evaluate(case["id"], config)
    for key, value in [("value", original["value"]+.1), ("value", float("nan")),
                       ("work_units", 0), ("work_units", True)]:
        corrupted = deepcopy(original)
        corrupted[key] = value
        with pytest.raises(ValueError):
            verify_observation(case, config, corrupted)
    corrupted = deepcopy(original)
    field = next(iter(corrupted["payload"]))
    corrupted["payload"][field] = [float("nan")]
    with pytest.raises(ValueError):
        verify_observation(case, config, corrupted)


@pytest.mark.parametrize("config", [{"gain": 0}, {"gain": float("nan")}, {"gain": True},
                                  {"gain": .3, "noise": .1}, {}])
def test_reject_invalid_tuning_shortcuts(config):
    with pytest.raises(ValueError):
        validate_config(get_case("filter-a"), config)


def test_reject_fractional_width_and_nan_size_receipt():
    with pytest.raises(ValueError):
        evaluate("bottleneck-a", {"width": 2.5})
    observation = evaluate("bottleneck-a", {"width": 3})
    observation["payload"]["prediction_error"] = float("nan")
    with pytest.raises(ValueError):
        verify_observation(get_case("bottleneck-a"), {"width": 3}, observation)
