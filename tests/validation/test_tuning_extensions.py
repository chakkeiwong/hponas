"""Independent analytic and adversarial controls for finite tuning workloads."""
from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
import json
import math

import numpy as np
import pytest
from scipy.integrate import quad

from validation import tuning_reference as reference
from workloads import tuning_models as models
from workloads import gaussian_hmc as hmc
from workloads.harmonic_hamiltonian import fit_hamiltonian


def test_all_quadratic_trajectories_and_resume_match_exact_spectral_answer():
    outcomes = []
    for i in range(1, 26):
        eta = Q(i, 40)
        final = models.quadratic(float(eta), 8)
        for row in final["trace"]:
            n = row["iteration"]
            a, b = Q(1, 10)*(1-eta)**n, (1-3*eta)**n
            expected = [Q(3, 5)*a-Q(4, 5)*b, Q(4, 5)*a+Q(3, 5)*b]
            np.testing.assert_allclose(row["state"], list(map(float, expected)), rtol=1e-10, atol=1e-12)
            assert row["value"] == pytest.approx(float(a*a+b*b), rel=1e-10, abs=1e-12)
        checkpoint, work = None, 0
        for fidelity in [1, 2, 4, 8]:
            row = models.quadratic(float(eta), fidelity, checkpoint)
            work += row["incremental_steps"]
            checkpoint = json.loads(json.dumps(row["checkpoint"]))
        assert checkpoint == final["checkpoint"] and work == 8
        assert sum(models.quadratic(float(eta), n)["incremental_steps"] for n in [1, 2, 4, 8]) == 15
        outcomes.append((final["value"], eta))
    assert min(outcomes)[1] == Q(9, 20)
    assert models.quadratic(.25, 1)["value"] < models.quadratic(.45, 1)["value"]
    assert models.quadratic(.25, 8)["value"] > models.quadratic(.45, 8)["value"]


def test_all_128_relu_fits_match_rational_normal_equations_and_integrals():
    answers = reference.spline()
    assert len(answers["architectures"]) == 128
    for exact in answers["architectures"]:
        observed = models.spline([int(8*Q(k)) for k in exact["knots"]])
        expected = [float(Q(w)) for w in exact["weights"]]
        np.testing.assert_allclose(observed["coefficients"], expected, rtol=1e-10, atol=1e-12)
        assert observed["integrated_error"] == pytest.approx(float(Q(exact["integrated_error"])), abs=1e-12)
        assert observed["fitted_output_count"] == exact["width"]+2
    assert [Q(p["error"]) for p in answers["frontier"][:4]] == [Q(5, 768), Q(1, 768), Q(7, 8448), 0]


@pytest.mark.parametrize("c", [Q(-99, 100), Q(-1, 2), Q(0), Q(1, 2), Q(99, 100)])
def test_gaussian_flow_has_known_moments_and_two_feature_tuning_score(c):
    out = models.gaussian_flow(float(c))
    np.testing.assert_allclose(out["next_moments"], [0, 1, 0, 3], atol=1e-12)
    mean, square = (1+c)/(1-c), (1+c*c)/(1-c*c)
    np.testing.assert_allclose(out["iact"], [float(mean), float(square)], rtol=1e-10)
    assert out["worst_iact"] == pytest.approx(float(max(mean, square)), rel=1e-10)
    assert max(mean, square) >= 1 and ((max(mean, square) == 1) == (c == 0))


def mm(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(2)) for j in range(2)] for i in range(2)]


def rational_matrix(e, steps, w):
    one = Q(1)
    single = [[one-e*e*w*w/2, e], [-e*w*w*(one-e*e*w*w/4), one-e*e*w*w/2]]
    result = [[one, Q(0)], [Q(0), one]]
    for _ in range(steps):
        result = mm(result, single)
    return result


def test_leapfrog_and_metropolis_against_rational_matrix_reference():
    for e, w, n in product([Q(1, 4), Q(1, 2), Q(1)], [Q(1, 2), Q(1), Q(2)], [1, 2, 3, 4, 8]):
        matrix = rational_matrix(e, n, w)
        np.testing.assert_allclose(hmc.proposal_matrix(float(e), n, float(w)), np.array(matrix, dtype=float), atol=1e-12)
        assert matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0] == 1
        for q, p in product([Q(-1), Q(0), Q(2)], repeat=2):
            qq, pp = matrix[0][0]*q+matrix[0][1]*p, matrix[1][0]*q+matrix[1][1]*p
            delta = (w*w*(qq*qq-q*q)+pp*pp-p*p)/2
            for uniform in [.25, .5, .75]:
                row = hmc.metropolis(float(q), float(p), float(e), n, float(w), uniform)
                assert row["q"] == pytest.approx(float(qq), abs=1e-12)
                assert row["p"] == pytest.approx(float(pp), abs=1e-12)
                assert row["delta_energy"] == pytest.approx(float(delta), abs=1e-12)
                assert row["accepted"] == (math.log(uniform) < min(0., -float(delta)))


@pytest.mark.parametrize("e,n,w", [(Q(1, 4), 1, Q(1)), (Q(1, 2), 4, Q(1)), (Q(1), 3, Q(1)), (Q(3, 4), 2, Q(2))])
def test_stationary_acceptance_matches_independent_angular_integral(e, n, w):
    a = rational_matrix(e, n, w)
    k = np.array([[float(a[0][0]), float(w*a[0][1])], [float(a[1][0]/w), float(a[1][1])]])
    def integrand(t):
        vector = k @ np.array([math.cos(t), math.sin(t)])
        return min(1., 1./float(vector @ vector))
    # Independent polar integration integrates the radial Gaussian exactly.
    value, error = quad(integrand, 0., 2*math.pi, epsabs=2e-8, points=np.linspace(0., 2*math.pi, 33), limit=250)
    assert error < 2e-7
    assert hmc.stationary_mean_acceptance(float(e), n, float(w)) == pytest.approx(value/(2*math.pi), abs=1e-7)


def test_perfect_acceptance_is_not_posterior_exploration():
    assert rational_matrix(Q(1), 3, Q(1)) == [[-1, 0], [0, -1]]
    q = 2.
    for p in [-2., 1., 0., 2.]*4:
        row = hmc.metropolis(q, p, 1., 3, 1., .5)
        assert row["accepted"] and row["acceptance_probability"] == 1.
        q = row["next_q"]
        assert q*q == 4.  # Target second moment is 1.
    chains = np.tile(np.array([2., -2.]), (4, 32))[:, :, None]
    diag = hmc.chain_diagnostics(chains)
    assert not hmc.correctness_veto(diag, 0)["eligible_for_calibration"]


def test_sampler_json_resume_counts_warmup_and_incremental_gradients():
    options = dict(step_size=.5, steps=3, frequency=1., seed=12, warmup=8)
    full = hmc.sample_gaussian(**options, draws=32)
    part = hmc.sample_gaussian(**options, draws=8)
    resumed = hmc.sample_gaussian(**options, draws=32, checkpoint=json.loads(json.dumps(part["checkpoint"])))
    assert resumed["checkpoint"] == full["checkpoint"]
    assert resumed["chains"] == full["chains"]
    assert full["gradient_evaluations"] == (32+8)*4*2*3
    assert resumed["incremental_gradient_evaluations"] + part["gradient_evaluations"] == full["gradient_evaluations"]
    assert full["identity"]["method"] == "leapfrog_metropolis_full_momentum_refresh"
    assert full["veto"]["scientific_acceptance"] is False


@pytest.mark.parametrize("damage", [lambda c: c.update(completed_draws=-1),
                                    lambda c: c.update(gradient_evaluations=0),
                                    lambda c: c["positions"].__setitem__(0, 900.)])
def test_sampler_rehashed_invalid_recovery_is_refused(damage):
    options = dict(step_size=.5, steps=2, draws=8, seed=12)
    checkpoint = hmc.sample_gaussian(**options)["checkpoint"]
    bad = deepcopy(checkpoint)
    damage(bad)
    bad["binding"] = hmc._binding({k: v for k, v in bad.items() if k != "binding"})
    with pytest.raises(ValueError):
        hmc.sample_gaussian(**options, checkpoint=bad)


def test_absolute_veto_precedes_speed_and_has_no_scientific_pass():
    healthy = {"rhat": 1., "bulk_ess": 500., "tail_ess": 450.}
    assert hmc.correctness_veto(healthy, 0)["eligible_for_calibration"]
    assert not hmc.correctness_veto(healthy, 1)["eligible_for_calibration"]
    for key, value in [("rhat", 1.02), ("bulk_ess", 399), ("tail_ess", 399), ("rhat", float("nan"))]:
        assert not hmc.correctness_veto({**healthy, key: value}, 0)["eligible_for_calibration"]
    assert not hmc.correctness_veto(healthy, 0)["scientific_acceptance"]


def test_sampler_controls_distinguish_chain_disagreement_from_shared_bias():
    rng = np.random.RandomState(125)
    independent = rng.normal(size=(4, 2048, 2))
    healthy = hmc.chain_diagnostics(independent)
    assert hmc.correctness_veto(healthy, 0)["eligible_for_calibration"]
    # Chains trapped in distinct mixture components must fail the veto.
    disagreement = independent.copy()
    disagreement[:2, :, 0] -= 5
    disagreement[2:, :, 0] += 5
    diagnostics = hmc.chain_diagnostics(disagreement)
    assert diagnostics["marginals"][0]["rhat"] > 1.01
    assert not hmc.correctness_veto(diagnostics, 0)["eligible_for_calibration"]
    # A shared location bias can pass mixing diagnostics; only independent
    # reference agreement/calibration could accept that posterior scientifically.
    biased = hmc.chain_diagnostics(independent + 10)
    verdict = hmc.correctness_veto(biased, 0)
    assert verdict["eligible_for_calibration"] and not verdict["scientific_acceptance"]


def test_legacy_sampler_retains_warmup_divergences_and_actual_method(monkeypatch):
    from workloads import sampler_neutra as legacy
    monkeypatch.setattr(legacy, "hmc_step", lambda z, *args: (z, True))
    result = legacy.sampler_neutra(dict(step_size=.5, n_leapfrog=2, n_chains=2, target="funnel"), fidelity=.1)
    assert result["method"] == "ordinary_hmc"
    assert result["warmup_divergences"] == 200 and result["retained_divergences"] == 200
    assert result["gradient_evaluations"] == 1200
    assert result["divergences"] == 1.
    assert not result["veto"]["eligible_for_calibration"]
    with pytest.raises(ValueError, match="supported: funnel"):
        legacy.sampler_neutra(dict(step_size=.5, n_leapfrog=2, n_chains=2, target="rosenbrock"))


@pytest.mark.parametrize("frequency", [.5, 1., 2.])
def test_complete_hamiltonian_recovers_analytic_flow_on_distinct_initial_states(frequency):
    result = fit_hamiltonian(("q2", "qp", "p2"), frequency=frequency)
    np.testing.assert_allclose(result["coefficients"], [frequency**2, 0., 1.], atol=1e-12)
    assert result["prediction_error"] < 1e-24
    assert result["true_energy_drift"] < 1e-12
    assert not set(result["training_initials"]).intersection(result["heldout_initials"])
    for initial, path in zip(result["heldout_initials"], result["learned_paths"]):
        for t, (q, p) in zip([0., *result["heldout_times"]], path):
            # Independent complex harmonic solution, not the workload generator.
            z = complex(initial[0], initial[1]/frequency)*np.exp(-1j*frequency*t)
            np.testing.assert_allclose([q, p], [z.real, frequency*z.imag], atol=1e-12)


def test_small_energy_drift_alone_cannot_reward_near_zero_dynamics():
    optimum = fit_hamiltonian(("q2", "p2"))
    nearly_constant = fit_hamiltonian(("q2", "p2"), ridge=1e12)
    assert nearly_constant["prediction_error"] > .1
    assert nearly_constant["true_energy_drift"] < 1e-10
    assert optimum["prediction_error"] < 1e-24


@pytest.mark.parametrize("call", [
    lambda: models.quadratic(0., 8), lambda: models.quadratic(2/3, 8),
    lambda: models.quadratic(.2, True), lambda: models.spline([2, 2]),
    lambda: models.spline([0]), lambda: models.gaussian_flow(1),
    lambda: hmc.leapfrog(0, 0, 1, 0), lambda: hmc.metropolis(0, 0, 1, 1, 1, 0),
    lambda: hmc.sample_gaussian(step_size=.5, steps=2, draws=3),
    lambda: hmc.sample_gaussian(step_size=.5, steps=2, initial_positions=[1.]),
    lambda: fit_hamiltonian(("wrong",)), lambda: fit_hamiltonian(ridge=-1),
])
def test_invalid_tuning_coordinates_refuse_before_execution(call):
    with pytest.raises(ValueError):
        call()
