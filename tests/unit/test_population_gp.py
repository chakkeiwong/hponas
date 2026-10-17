"""Known covariance, conditioning and pending-point controls for population BO."""
from fractions import Fraction
import math

import numpy as np
import pytest

from hponas.population_gp import TemporalOptions, TemporalPopulationGP


def test_pb2_mix_equation_five_uses_both_temporal_components():
    model = TemporalPopulationGP([0], [1], TemporalOptions(decay=0.75, mixture=0.25))
    # Same numerical coordinate, matching category and time separation two:
    # temporal=1/4, hence (3/4)(1/4+1/4)+(1/4)(1/4)^2 = 25/64.
    x = [[0, 0, 1]]
    y = [[2, 0, 1], [2, 0, 0]]
    expected = [Fraction(25, 64), Fraction(3, 16)]
    assert model.kernel(x, y)[0].tolist() == pytest.approx([float(v) for v in expected], abs=1e-15)


def test_bg_kernel_has_single_temporal_factor_and_matern_numeric_part():
    o = TemporalOptions(family='bgpbt', decay=0.75, length=1, categorical_length=2)
    model = TemporalPopulationGP([0], [1], o)
    actual = model.kernel([[0, 0, 1]], [[2, 1, 1]])[0, 0]
    numeric = (1+math.sqrt(5)+5/3)*math.exp(-math.sqrt(5))
    category = math.exp(0.5)
    assert actual == pytest.approx((numeric+category+numeric*category)/8, abs=1e-15)


def test_pending_points_change_variance_not_mean_and_match_rational_inverse():
    model = TemporalPopulationGP([0], [], TemporalOptions(decay=0.75, noise=0.5))
    model.observe([[0, 0]], [1])
    mean, variance = model.predict([[2, 0]])
    assert mean[0] == pytest.approx(1/6)
    assert variance[0] == pytest.approx(23/24)
    later_mean, later_variance = model.predict([[2, 0]], pending=[[2, 0]])
    assert later_mean.tolist() == mean.tolist()
    # K=[[3/2,1/4],[1/4,3/2]], k=[1/4,1], det=35/16.
    det = Fraction(35, 16)
    q = (Fraction(3, 2)*Fraction(1, 4)**2 - 2*Fraction(1, 4)**2 + Fraction(3, 2))/det
    assert later_variance[0] == pytest.approx(float(1-q), abs=1e-15)
    assert later_variance[0] < variance[0]


@pytest.mark.parametrize('family', ['pb2_mix', 'bgpbt'])
@pytest.mark.parametrize('decay', [0.0, 0.1, 1.0])
def test_mixed_kernel_psd_symmetry_and_temporal_extremes(family, decay):
    points = [[t, x, category] for t in range(3) for x in [0, 0.5, 1] for category in [0, 1]]
    model = TemporalPopulationGP([0], [1], TemporalOptions(family=family, decay=decay))
    matrix = model.kernel(points, points)
    np.testing.assert_allclose(matrix, matrix.T, rtol=0, atol=1e-15)
    assert np.linalg.eigvalsh(matrix).min() > -1e-12
    if decay == 1:
        assert model.kernel([[0, 0, 0]], [[1, 0, 0]])[0, 0] == 0
    if decay == 0:
        assert model.kernel([[0, 0, 0]], [[10, 0, 0]])[0, 0] == model.kernel([[0, 0, 0]], [[0, 0, 0]])[0, 0]


def test_finite_batch_diversifies_without_fictitious_rewards():
    model = TemporalPopulationGP([0], [], TemporalOptions(length=0.1))
    candidates = [[1, 0], [1, 0.1], [1, 1]]
    assert model.suggest_finite(candidates, 3) == [0, 2, 1]
    assert not len(model.y)


def test_fit_is_bounded_and_records_terminal_optimizer_status():
    model = TemporalPopulationGP([0], [], TemporalOptions())
    model.observe([[0, 0], [0, 1], [1, 0], [1, 1]], [0, 1, 1, 0])
    receipt = model.fit(max_iterations=3)
    assert receipt['evaluations'] <= 1200
    assert receipt['final_nll'] <= receipt['initial_nll'] + 1e-10
    mean, variance = model.predict([[2, 0.5]])
    assert np.isfinite(mean).all() and np.isfinite(variance).all()


@pytest.mark.parametrize('fault', ['category', 'duplicate', 'negative_time', 'nonfinite', 'dimension', 'decay'])
def test_refuse_invalid_domain_contracts(fault):
    with pytest.raises(ValueError):
        if fault == 'decay':
            TemporalOptions(decay=1.1)
        elif fault == 'dimension':
            TemporalPopulationGP([0], [0])
        else:
            model = TemporalPopulationGP([], [0])
            if fault == 'category':
                model.kernel([[0, 0.5]], [[1, 1]])
            elif fault == 'duplicate':
                model.suggest_finite([[1, 0], [1, 0]], 2)
            elif fault == 'negative_time':
                model.observe([[-1, 0]], [1])
            elif fault == 'nonfinite':
                model.observe([[0, 0]], [float('nan')])
