"""Independent population reconstruction, including coherent corruption."""
from copy import deepcopy

import numpy as np
import pytest

from validation.population_contract import contract
from validation.population_producers import execute_slot
from validation.population_reference import digest, objective, verify_slot


@pytest.fixture(scope='module')
def population_cases(tmp_path_factory):
    directory = tmp_path_factory.mktemp('population-evidence')
    return [(spec, execute_slot(spec, directory/spec['id'])) for spec in contract()['slots']]


def test_all_fixed_slots_have_independent_mathematical_reconstruction(population_cases):
    reports = [verify_slot(spec, raw) for spec, raw in population_cases]
    assert all(row['status'] == 'PASS' for row in reports)
    assert sum(row['updates_lower'] for row in reports) == 31
    assert sum(row['updates_upper'] for row in reports) == 32


def test_reference_bellman_gradient_matches_independent_central_difference(population_cases):
    spec, raw = population_cases[0]
    row = raw['rows'][0]
    outputs = np.array(row['outputs'])
    _, gradient = objective(raw['objective'], outputs, row['teacher_outputs'], 0)
    difference = np.zeros_like(outputs)
    for index in np.ndindex(outputs.shape):
        plus, minus = outputs.copy(), outputs.copy()
        plus[index] += 1e-5; minus[index] -= 1e-5
        a = objective(raw['objective'], plus, row['teacher_outputs'], 0)[0]['loss']
        b = objective(raw['objective'], minus, row['teacher_outputs'], 0)[0]['loss']
        difference[index] = (a-b)/2e-5
    np.testing.assert_allclose(gradient, difference, atol=1e-10, rtol=0)


@pytest.mark.parametrize('fault', ['gradient', 'kernel', 'pending_mean', 'bandit', 'tensors', 'trace', 'accounting', 'halving', 'lineage'])
def test_rehashed_corrupt_evidence_cannot_pass_independent_reference(population_cases, fault):
    index = {'gradient': 0, 'kernel': 1, 'pending_mean': 1, 'bandit': 2,
             'tensors': 3, 'trace': 3, 'accounting': 4, 'halving': 9, 'lineage': 3}[fault]
    spec, original = population_cases[index]
    raw = deepcopy(original)
    if fault == 'gradient':
        raw['rows'][0]['gradient'][0][0] += 0.01
    elif fault in {'kernel', 'pending_mean'}:
        if fault == 'kernel':
            raw['rows'][0]['kernel'][0][0] += 0.01
        else:
            raw['rows'][0]['pending_mean'][0] += 0.01
    elif fault == 'bandit':
        raw['bandit']['payload']['weights'][0] += 0.01
        raw['bandit']['sha256'] = digest(raw['bandit']['payload'])
    elif fault == 'halving':
        envelope = raw['files']['transfer-0/generation.json']
        envelope['payload']['rungs'][0]['scores']['0'] += 0.01
        envelope['sha256'] = digest(envelope['payload'])
    else:
        envelope = raw['files']['population.json']
        state = envelope['payload']
        event = state['events']['transfer']
        if fault == 'tensors':
            event['candidate']['tensors']['0.bias'][0] += 0.01
            event['result_sha256'] = digest(event['candidate'])
            state['members']['1'] = deepcopy(event['candidate'])
            state['lineage'][0]['result_sha256'] = event['result_sha256']
        elif fault == 'trace':
            event['trace'][0]['return'] += 0.01
        elif fault == 'accounting':
            event['inflight'] = False
        else:
            state['lineage'] = []
        envelope['sha256'] = digest(state)
    with pytest.raises(ValueError):
        verify_slot(spec, raw)
