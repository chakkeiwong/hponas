"""Exact workload answers, independent derivatives and adversarial controls."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest
import torch

from validation import workload_disposition_reference as reference
from workloads.finance_portfolio import evaluate
from workloads.learned_transport import TanhTransport, latent_energy, leapfrog, train


@pytest.mark.parametrize('preference', [0, 1, 2, 4, 8, 12])
@pytest.mark.parametrize('rate', [0.02, 0.05, 0.1, 0.15])
def test_finance_actual_updates_against_rational_convex_reference(preference, rate):
    config = {'learning_rate': rate, 'return_preference': preference}
    full = evaluate(config, 8)
    assert reference.finance(full)['status'] == 'PASS'
    checkpoint, work = None, 0
    for target in [1, 2, 4, 8]:
        result = evaluate(config, target, checkpoint)
        reference.finance(result)
        work += result['incremental_updates']
        checkpoint = json.loads(json.dumps(result['checkpoint']))
    assert checkpoint == full['checkpoint']
    assert work == 8
    assert set(map(tuple, full['task']['training_rows'])).isdisjoint(map(tuple, full['task']['evaluation_rows']))
    if rate == 0.1:
        assert float(reference.finance(full)['exact_regret']) == 0


def test_finance_known_efficient_frontier_is_not_every_feasible_portfolio():
    # d variance/d x = 10x-8 and d return/d x = -1.
    # Above x=4/5 both risk and return are worse; on [0,4/5] they trade off.
    points = [(x/20, 5*(x/20)**2-8*x/20+4, 2-x/20) for x in range(21)]
    efficient = [x for x, risk, ret in points
                 if not any(rr <= risk and mu >= ret and (rr < risk or mu > ret) for _, rr, mu in points)]
    assert efficient == [x/20 for x in range(17)]


@pytest.mark.parametrize('target', [-2, 0.5, 2])
@pytest.mark.parametrize('rate', [0.5, 1, 2])
def test_actual_neural_transport_training_matches_closed_form_and_resume(target, rate):
    full = train(target_amplitude=target, learning_rate=rate, iterations=8)
    assert reference.transport(full)['status'] == 'PASS'
    partial = train(target_amplitude=target, learning_rate=rate, iterations=3)
    resumed = train(target_amplitude=target, learning_rate=rate, iterations=8,
                    checkpoint=json.loads(json.dumps(partial['checkpoint'])))
    reference.transport(resumed)
    assert resumed['checkpoint'] == full['checkpoint']
    assert partial['incremental_updates']+resumed['incremental_updates'] == 8
    assert abs(full['amplitude']-target) < abs(target)
    assert not full['calibration_or_mixing_accepted']


@pytest.mark.parametrize('amplitude', [-1, 0, 1, 2])
def test_transport_inverse_jacobian_and_target_chain_rule(amplitude):
    transform = TanhTransport(amplitude)
    points = torch.tensor([[-2, 1], [0, -1], [1.5, 0.25]], dtype=torch.float64)
    np.testing.assert_allclose(transform.inverse(transform(points)).detach(), points, atol=1e-14)
    for point in points:
        jacobian = torch.autograd.functional.jacobian(lambda x: transform(x[None])[0], point)
        assert float(torch.linalg.det(jacobian)) == pytest.approx(1, abs=1e-14)
    points.requires_grad_(True)
    gradient, = torch.autograd.grad(latent_energy(points, transform, 1).sum(), points)
    expected = [reference.transported_gradient(p, amplitude, 1) for p in points.detach().tolist()]
    np.testing.assert_allclose(gradient, expected, atol=1e-13)
    if amplitude == 1:
        np.testing.assert_allclose(gradient, points.detach(), atol=1e-14)
    assert not math.isclose(reference.transported_gradient([1, 1], -1, 1)[0], 1)


@pytest.mark.parametrize('amplitude', [0, 0.75, 1])
def test_transformed_leapfrog_matches_independent_gradient_and_reversibility(amplitude):
    options = dict(amplitude=amplitude, target_amplitude=1, step_size=0.125, steps=4)
    q, p = [0.7, -1.25], [-0.3, 0.5]
    result = leapfrog(q, p, **options)
    expected_q, expected_p = reference.transport_transition(q, p, **options)
    np.testing.assert_allclose(result['position'], expected_q, atol=1e-13)
    np.testing.assert_allclose(result['momentum'], expected_p, atol=1e-13)
    back = leapfrog(result['position'], (-expected_p).tolist(), **options)
    np.testing.assert_allclose(back['position'], q, atol=1e-13)
    np.testing.assert_allclose(back['momentum'], -np.asarray(p), atol=1e-13)
    assert result['gradient_evaluations'] == 8


@pytest.mark.parametrize('model', ['finance', 'transport'])
def test_checkpoint_and_raw_numerical_corruption_is_refused(model):
    if model == 'finance':
        run = lambda **kw: evaluate({'learning_rate': 0.05, 'return_preference': 2}, **kw)
        output, field, verify = run(iterations=4), 'weight', reference.finance
        metric = 'variance'
    else:
        run = lambda **kw: train(target_amplitude=1, learning_rate=1, **kw)
        output, field, verify = run(iterations=4), 'amplitude', reference.transport
        metric = 'loss'
    bad = deepcopy(output['checkpoint'])
    bad[field] += 0.1
    with pytest.raises(ValueError, match='trajectory'):
        run(iterations=8, checkpoint=bad)
    output[metric] += 0.1
    with pytest.raises(ValueError):
        verify(output)


def test_finance_public_vector_study_and_repaired_examples(tmp_path):
    from examples.finance_tuning import run
    from examples.hamiltonian_mo_example import run as hamiltonian
    from examples.sampler_neutra_example import run as sampler
    result = run(tmp_path)
    assert result['n_trials'] == 8
    assert result['metrics']['total_work'] == 64
    assert not result['real_market_evidence']
    physics = hamiltonian()
    assert len(physics['rows']) == 4
    assert physics['rows'][1]['prediction_error'] < 1e-24
    assert physics['rows'][-1]['prediction_error'] > 0.1
    transport = sampler()
    reference.transport(transport['training'])
    assert transport['transition']['gradient_evaluations'] == 8


@pytest.mark.parametrize('call', [
    lambda: evaluate({'learning_rate': 0.2, 'return_preference': 1}),
    lambda: evaluate({'learning_rate': 0.1, 'return_preference': float('nan')}),
    lambda: evaluate({'learning_rate': 0.1, 'return_preference': 1}, True),
    lambda: evaluate({'learning_rate': 0.1}), lambda: train(learning_rate=3),
    lambda: train(iterations=True), lambda: train(target_amplitude=5),
    lambda: TanhTransport(float('inf')), lambda: TanhTransport(1)([[1]]),
    lambda: leapfrog([0, 0], [0, 0], amplitude=0, target_amplitude=1, step_size=0.1, steps=0),
])
def test_workload_envelope_is_refused(call):
    with pytest.raises(ValueError):
        call()
