"""Model assumptions, task-level units and refusal of invalidated acceptance."""

import numpy as np
import pytest
from scipy.stats import ttest_1samp

from validation.stats import Cluster
from validation.tier0_inference import (
    preview_task_mean_t, require_acceptance_inference, task_mean_t_statistics,
)
from validation.tier0_sizing import size_joint_entry


def clusters():
    return [Cluster(str(i), np.asarray([mean - .2, mean, mean + .2]))
            for i, mean in enumerate((.1, .2, .4, .8))]


def test_task_level_result_matches_independent_scipy_reference():
    data = clusters()
    result = preview_task_mean_t(data, margin=.05)
    reference = ttest_1samp([c.mean for c in data], popmean=.05, alternative='greater')
    assert result['p_value'] == pytest.approx(reference.pvalue)
    assert result['statistic'] == pytest.approx(reference.statistic)
    assert result['lower_bound'] == pytest.approx(reference.confidence_interval(.975).low)
    assert result['df'] == len(data) - 1
    assert result['verdict'] == 'INCONCLUSIVE'
    assert result['certifies_acceptance'] is False


def test_repeating_within_task_blocks_does_not_create_degrees_of_freedom():
    data = clusters()
    repeated = [Cluster(c.task, np.tile(c.differences, 20)) for c in data]
    before, after = [preview_task_mean_t(d) for d in (data, repeated)]
    for name in ('df', 'n_tasks', 'point', 'p_value', 'lower_bound', 'standard_error'):
        assert after[name] == pytest.approx(before[name])
    assert after['blocks_per_task'] == 60


def test_affine_change_of_units_preserves_the_decision_and_transforms_the_bound():
    data = clusters()
    before = preview_task_mean_t(data, margin=.05)
    after = preview_task_mean_t([Cluster(c.task, 10 * c.differences + 2) for c in data], margin=2.5)
    assert after['p_value'] == pytest.approx(before['p_value'])
    assert after['lower_bound'] == pytest.approx(10 * before['lower_bound'] + 2)


def test_vectorized_stress_core_matches_single_dataset_preview():
    data = clusters()
    means = np.array([c.mean for c in data])
    batched = task_mean_t_statistics(np.stack([means, means + .7]))
    single = preview_task_mean_t(data)
    assert batched['p_value'][0] == pytest.approx(single['p_value'])
    assert batched['p_value'][1] < batched['p_value'][0]
    assert batched['lower_bound'][1] == pytest.approx(batched['lower_bound'][0] + .7)


@pytest.mark.parametrize('data', [
    [Cluster('a', np.ones(3))],
    [Cluster('a', np.ones(3)), Cluster('a', np.zeros(3))],
    [Cluster('a', np.ones(3)), Cluster('b', np.zeros(4))],
    [Cluster('a', np.ones(3)), Cluster('b', np.ones(3))],
    [Cluster('a', np.array([1., np.nan])), Cluster('b', np.zeros(2))],
    [Cluster('a', np.ones((2, 2))), Cluster('b', np.zeros(2))],
    [Cluster('a', np.array([1.])), Cluster('b', np.array([2.]))],
])
def test_unsupported_or_degenerate_studies_cannot_supply_inference(data):
    with pytest.raises(ValueError):
        preview_task_mean_t(data)


@pytest.mark.parametrize('options', [{'alpha': 0}, {'alpha': True}, {'alpha': float('nan')},
                                   {'margin': float('inf')}, {'margin': True}])
def test_invalid_hypotheses_are_refused(options):
    with pytest.raises(ValueError):
        preview_task_mean_t(clusters(), **options)


@pytest.mark.parametrize('analysis', [{}, {'method': 'paired_cluster_percentile'},
                                     {'method': 'gaussian_task_mean_t_preview'},
                                     {'method': 'user_supplied_certified'}])
def test_a_method_label_cannot_enable_unvalidated_acceptance(analysis):
    with pytest.raises(ValueError, match='STAT-03'):
        require_acceptance_inference(analysis)


def test_full_invalidated_sizing_is_refused_before_any_model_or_simulation(monkeypatch):
    monkeypatch.setattr('validation.tier0_sizing.pilot_model',
                        lambda *unused: pytest.fail('Full invalidated sizing must not run'))
    with pytest.raises(ValueError, match='invalidated'):
        size_joint_entry({}, [1.], [0.])


def test_reduced_legacy_diagnostic_can_never_be_a_sizing_receipt():
    sample = np.array([[0.], [.1], [.2], [.3], [.4]])
    result = size_joint_entry({'a': sample, 'b': sample + .1}, [10.], [0.],
                              candidates=[5], replicates=4, draws=99)
    assert result['candidate_chosen_n'] == 5
    assert result['chosen_n'] is None
    assert result['verdict'] == 'INCONCLUSIVE'
    assert result['usable_as_registered_sizing_receipt'] is False
