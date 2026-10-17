"""Independent posterior integration, Gaussian orthants and acquisition gradients."""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp, roots_hermitenorm
from scipy.stats import norm
import torch

from hponas.cost_inference import GaussianCensoredCost, log_survival, log_survival_mean_gradient
from hponas.cost_likelihood import likelihood

BASE = Path(__file__).resolve().parents[2]/'docs/program/evidence/2026-10-06/censored-cost-candidate-01'


def integrated_scalar(mean, variance, events):
    def log_density(x):
        result = norm.logpdf(x, mean, math.sqrt(variance))
        for event in events:
            y, sigma = math.log(event['elapsed']), math.sqrt(event['noise_variance'])
            result += (norm.logsf(y, x, sigma) if event['kind'] == 'timeout' else norm.logpdf(y, x, sigma)-y)
        return result
    opt = minimize_scalar(lambda x: -log_density(x))
    shift = log_density(opt.x)
    moments = [quad(lambda x: math.exp(log_density(x)-shift+power*x), -math.inf, math.inf,
                    epsabs=1e-11, epsrel=1e-11)[0] for power in [0, 1, 2]]
    return np.log(np.array(moments[1:])/moments[0])


def test_exact_expression_repairs_retained_laplace_mean_bias():
    frozen = json.loads((BASE/'plan.json').read_text())
    for case in frozen['one_latent_cases']:
        mean, variance, events = case['mean'], case['variance'], case['events']
        model = GaussianCensoredCost([mean], [[variance]], [[1.]]*len(events), events)
        result = model.predict([mean], [[variance]], [[variance]])
        reference = integrated_scalar(mean, variance, events)
        np.testing.assert_allclose([result['log_expected_cost'][0], result['log_second_moment'][0]],
                                   reference, rtol=1e-10, atol=1e-10)
        assert not result['posterior_gaussian_approximation']
        clone = GaussianCensoredCost.from_state(json.loads(json.dumps(model.state_dict(), allow_nan=False)))
        np.testing.assert_array_equal(clone.predict([mean], [[variance]], [[variance]])['log_expected_cost'],
                                      result['log_expected_cost'])


@pytest.mark.parametrize('count', [3, 5, 8])
def test_more_than_two_censors_match_independent_posterior_integration(count):
    events = [{'kind': 'timeout', 'elapsed': math.exp(.15*(i-count/2)), 'noise_variance': 1.+i/5}
              for i in range(count)]
    model = GaussianCensoredCost([.2], [[.7]], [[1.]]*count, events)
    actual = model.predict([.2], [[.7]], [[.7]])
    reference = integrated_scalar(.2, .7, events)
    np.testing.assert_allclose([actual['log_expected_cost'][0], actual['log_second_moment'][0]],
                               reference, rtol=1e-5, atol=1e-5)
    assert actual['censor_count'] == count and not actual['numerical_error_estimates_are_rigorous_bounds']
    assert max(v[0] for v in actual['quadrature_relative_error_estimates']) <= 4e-6


def test_correlated_gaussian_orthants_match_exact_arcsine_laws():
    for rho in [-.8, -.2, 0., .4, .8]:
        probability = log_survival([0., 0.], [[1., rho], [rho, 1.]], [0., 0.])
        assert math.exp(probability['log_probability']) == pytest.approx(.25+math.asin(rho)/(2*math.pi), abs=1e-10)
    cov = np.array([[1., .3, -.2], [.3, 1., .1], [-.2, .1, 1.]])
    exact = .125+sum(math.asin(cov[i, j]) for i, j in [(0, 1), (0, 2), (1, 2)])/(4*math.pi)
    result = log_survival(np.zeros(3), cov, np.zeros(3))
    assert math.exp(result['log_probability']) == pytest.approx(exact, abs=2e-7)
    independent = log_survival(np.zeros(5), np.eye(5), np.zeros(5))
    assert math.exp(independent['log_probability']) == pytest.approx(2**-5, abs=1e-14)


def test_multivariate_latent_prediction_matches_independent_hermite_integration():
    mean = np.array([.2, -.3]); covariance = np.array([[1., .4], [.4, 1.5]])
    design = np.array([[1., 0.], [0., 1.], [1., .5], [.5, 1.]])
    events = [{'kind': 'complete', 'elapsed': 1.5, 'noise_variance': .5},
              {'kind': 'timeout', 'elapsed': 2., 'noise_variance': .5},
              {'kind': 'timeout', 'elapsed': 4., 'noise_variance': .75},
              {'kind': 'timeout', 'elapsed': 2.5, 'noise_variance': 1.}]
    model = GaussianCensoredCost(mean, covariance, design, events)
    actual = model.predict(mean, covariance, covariance)
    references = []
    for order in [64, 128]:
        nodes, weights = roots_hermitenorm(order)
        a, b = np.meshgrid(nodes, nodes, indexing='ij')
        points = mean[:, None]+np.linalg.cholesky(covariance)@np.stack([a.ravel(), b.ravel()])
        log_weights = (np.log(weights)[:, None]+np.log(weights)[None, :]).ravel()-math.log(2*math.pi)
        for eta, event in zip(design@points, events):
            location, sigma = math.log(event['elapsed']), math.sqrt(event['noise_variance'])
            log_weights += (norm.logsf(location, eta, sigma) if event['kind'] == 'timeout'
                            else norm.logpdf(location, eta, sigma)-location)
        references.append([logsumexp(log_weights[None, :]+power*points, axis=1)-logsumexp(log_weights)
                           for power in [1, 2]])
    np.testing.assert_allclose(references[0], references[1], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose([actual['log_expected_cost'], actual['log_second_moment']],
                               references[1], rtol=2e-6, atol=2e-6)


def test_analytic_censor_mean_gradient_matches_central_difference():
    mean = np.array([.2, -.3]); cov = np.array([[1., .4], [.4, 1.5]]); lower = np.array([.1, .3])
    actual = log_survival_mean_gradient(mean, cov, lower, tolerance=1e-11)
    finite_difference = []
    for j in range(2):
        delta = np.eye(2)[j]*1e-5
        finite_difference.append((log_survival(mean+delta, cov, lower, 1e-11)['log_probability']
                                  -log_survival(mean-delta, cov, lower, 1e-11)['log_probability'])/2e-5)
    np.testing.assert_allclose(actual, finite_difference, rtol=1e-7, atol=1e-9)


def test_expected_cost_torch_path_has_correct_gradients_and_unit_scaling():
    events = [{'kind': 'complete', 'elapsed': 1.5, 'noise_variance': .5},
              {'kind': 'timeout', 'elapsed': 2., 'noise_variance': .4}]
    model = GaussianCensoredCost([0., .2], [[1., .3], [.3, 1.]], np.eye(2), events)
    x = torch.tensor(.4, dtype=torch.double, requires_grad=True)
    def predict(variable):
        return model.predict_torch(variable.reshape(1), torch.ones((1, 1), dtype=torch.double),
            torch.stack([.2+variable/4, .1+variable/3]).reshape(2, 1), noise_variance=.1)['log_expected_cost'][0]
    actual = predict(x)
    derivative, = torch.autograd.grad(actual, x)
    fd = (predict(x.detach()+1e-5)-predict(x.detach()-1e-5))/2e-5
    torch.testing.assert_close(derivative, fd, rtol=1e-7, atol=1e-8)
    exact = model.predict([.4], [[1.]], [[.3], [.1+.4/3]], noise_variance=.1)
    assert float(actual.detach()) == pytest.approx(exact['log_expected_cost'][0], abs=1e-12)
    shift = math.log(60.)
    rescaled = GaussianCensoredCost(np.array([0., .2])+shift, [[1., .3], [.3, 1.]], np.eye(2),
                                    [{**row, 'elapsed': row['elapsed']*60} for row in events])
    b = rescaled.predict([.4+shift], [[1.]], [[.3], [.1+.4/3]], noise_variance=.1)
    np.testing.assert_allclose(b['log_expected_cost']-exact['log_expected_cost'], [shift], atol=1e-12)
    np.testing.assert_allclose(b['log_second_moment']-exact['log_second_moment'], [2*shift], atol=1e-12)
    np.testing.assert_allclose(b['cost_cv_squared'], exact['cost_cv_squared'], atol=1e-11)


def test_complete_and_censored_likelihood_derivatives_and_invalid_mechanisms():
    events = [{'kind': 'complete', 'elapsed': 2., 'noise_variance': .25},
              {'kind': 'timeout', 'elapsed': 3., 'noise_variance': .4}]
    eta = np.array([.1, .3])
    actual, gradient, precision = likelihood(eta, events)
    reference = norm.logpdf(math.log(2), .1, .5)-math.log(2)+norm.logsf(math.log(3), .3, math.sqrt(.4))
    assert actual == pytest.approx(reference, abs=1e-12)
    for j in range(2):
        delta = np.eye(2)[j]*1e-5
        a, ga, _ = likelihood(eta+delta, events)
        b, gb, _ = likelihood(eta-delta, events)
        assert gradient[j] == pytest.approx((a-b)/2e-5, rel=1e-7)
        assert precision[j] == pytest.approx(-(ga[j]-gb[j])/2e-5, rel=1e-7)
    bad = deepcopy(events); bad[1]['kind'] = 'quality_stop'
    with pytest.raises(ValueError): GaussianCensoredCost([0.], [[1.]], [[1.], [1.]], bad)
    with pytest.raises(ValueError): log_survival(np.zeros(33), np.eye(33), np.zeros(33))
