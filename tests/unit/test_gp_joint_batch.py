"""Independent Gaussian-max oracle and durable joint proposal counterexamples."""
from copy import deepcopy
from itertools import combinations
import json
import math

import pytest
import torch
from scipy.special import ndtr
from botorch.models.model import Model
from botorch.posteriors.gpytorch import GPyTorchPosterior
from botorch.acquisition.logei import qLogExpectedImprovement
from botorch.sampling.normal import SobolQMCNormalSampler
from gpytorch.distributions import MultivariateNormal

from hponas import GPSearcher, Knob, SearchSpace, Config, Result, Study, LocalExecutor
from hponas.searchers.base import PendingSuggestionError
import hponas.searchers.gp_searcher as implementation


class CorrelatedPosterior(Model):
    """Three real Gaussian coordinates; A/B nearly redundant, C independent."""
    means = torch.tensor([3., 3.2, 2.], dtype=torch.double)
    covariance = torch.tensor([[1., .9999, 0.], [.9999, 1., 0.], [0., 0., 4.]], dtype=torch.double)

    @property
    def num_outputs(self): return 1

    @property
    def batch_shape(self): return torch.Size()

    def posterior(self, X, output_indices=None, observation_noise=False, posterior_transform=None):
        index = (2*X[..., 0]).round().long()
        mean = self.means[index]
        covariance = self.covariance[index.unsqueeze(-1), index.unsqueeze(-2)]
        return GPyTorchPosterior(MultivariateNormal(mean, covariance_matrix=covariance))


def acquisition(pending=None):
    # With best=-100, Gaussian negative tails are negligible at float64.
    # The formula below independently gives E[max(A,B)] + 100.
    return qLogExpectedImprovement(CorrelatedPosterior(), best_f=-100.,
        sampler=SobolQMCNormalSampler(torch.Size([4096]), seed=17),
        X_pending=pending, tau_max=1e-4)


def exact_pair(i, j):
    mu = [3., 3.2, 2.]
    variance = [1., 1., 4.]
    covariance = .9999 if {i,j} == {0,1} else 0.
    sd = math.sqrt(variance[i]+variance[j]-2*covariance)
    d = (mu[i]-mu[j])/sd
    return 100. + mu[i]*ndtr(d) + mu[j]*ndtr(-d) + sd*math.exp(-d*d/2)/math.sqrt(2*math.pi)


def test_correlated_gaussian_pair_is_not_repeated_best_singleton():
    choices = torch.tensor([[0.], [.5], [1.]], dtype=torch.double)
    singleton = acquisition()(choices[:,None,:])
    assert singleton.argsort(descending=True).tolist()[:2] == [1,0]
    oracle = {pair: exact_pair(*pair) for pair in combinations(range(3),2)}
    assert max(oracle, key=oracle.get) == (1,2)
    candidates, value = GPSearcher._joint_finite(acquisition(), choices, 2)
    assert candidates[:,0].tolist() == [.5,1.]
    # Numerical Monte Carlo comparison against the independent Gaussian formula;
    # this tolerance is numerical, not an empirical HPO success threshold.
    assert float(value.exp()) == pytest.approx(oracle[(1,2)], abs=.01)


def test_pending_integration_changes_rank_and_matches_enumerated_joint_sets():
    choices = torch.tensor([[0.], [1.]], dtype=torch.double)
    assert int(acquisition()(choices[:,None,:]).argmax()) == 0
    pending = torch.tensor([[.5]], dtype=torch.double)
    scores = acquisition(pending)(choices[:,None,:])
    assert int(scores.argmax()) == 1
    for i, coordinate in enumerate((0,2)):
        assert float(scores[i].exp()) == pytest.approx(exact_pair(coordinate,1),abs=.01)
    # Explicitly concatenating the same pending point must give the same draws
    # and acquisition values, with identical sampler seed and point ordering.
    batches = torch.cat([choices[:,None,:], pending.expand(2,1,1)],dim=1)
    torch.testing.assert_close(scores, acquisition()(batches), rtol=0., atol=0.)


def test_finite_enumeration_uses_q_point_sets_and_enforces_prospective_bound():
    calls=[]
    def score(points):
        calls.append(points.shape)
        return -(points[...,0].mean(dim=-1)-1.5).abs()
    choices=torch.arange(4,dtype=torch.double)[:,None]
    selected,value=GPSearcher._joint_finite(score,choices,2)
    oracle=max(combinations(range(4),2),key=lambda p:-abs(sum(p)/2-1.5))
    assert selected[:,0].tolist()==list(oracle) and float(value)==0.
    assert calls==[torch.Size([6,2,1])]
    with pytest.raises(ValueError,match='4096'):
        GPSearcher._joint_finite(lambda x: pytest.fail('unbounded acquisition dispatched'),torch.arange(100)[:,None],3)


def fitted():
    searcher=GPSearcher(SearchSpace([Knob('x','ordinal',(0,2))]),seed=12,initial_random_samples=2)
    for i,x in enumerate((0,2)):
        searcher.trials[str(i)]=Config({'x':x})
        searcher.observe(Result(str(i),float(x)))
    return searcher


def test_pending_locations_enter_real_acquisition_and_restore(monkeypatch):
    searcher=fitted()
    searcher.trials['pending']=Config({'x':1})
    seen=[]
    original=implementation.qLogExpectedImprovement
    def capture(*args,**kwargs):
        seen.append(kwargs['X_pending'].tolist())
        return original(*args,**kwargs)
    monkeypatch.setattr(implementation,'qLogExpectedImprovement',capture)
    restored=GPSearcher(searcher.search_space)
    restored.set_state(json.loads(json.dumps(searcher.get_state())))
    assert searcher.suggest_batch(2)==restored.suggest_batch(2)
    assert seen==[[[.5]],[[.5]]]
    assert all(c.values != {'x':1} for c in searcher.suggest_batch(2))


def test_invalid_pending_checkpoint_and_failed_batch_preserve_state():
    source=fitted()
    bad=deepcopy(source.get_state()); bad['pending_trial_ids']=['missing']
    before=deepcopy(source.get_state())
    with pytest.raises(ValueError,match='pending locations'): source.set_state(bad)
    assert source.get_state()==before
    for count in (0,9,True,1.5):
        with pytest.raises(ValueError,match='batch size'): source.suggest_batch(count)
        assert source.get_state()==before
    for x in range(3): source.trials['pending'+str(x)]=Config({'x':x})
    before=deepcopy(source.get_state())
    with pytest.raises(PendingSuggestionError): source.suggest_batch(2)
    assert source.get_state()==before


def test_continuous_batch_uses_one_joint_optimizer_call(monkeypatch):
    source=GPSearcher(SearchSpace([Knob('x','continuous',(0.,1.))]),seed=1,initial_random_samples=2)
    for i,x in enumerate((.1,.9)):
        source.trials[str(i)]=Config({'x':x}); source.observe(Result(str(i),x))
    calls=[]
    def optimize(acquisition, *, q, **kwargs):
        calls.append(q)
        return torch.tensor([[.2],[.7]],dtype=torch.double),torch.tensor(0.)
    monkeypatch.setattr(implementation,'optimize_acqf',optimize)
    assert [c['x'] for c in source.suggest_batch(2)]==[.2,.7]
    assert calls==[2]


@pytest.mark.parametrize('score',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_acquisition_refused_without_advancing_rng_or_trace(monkeypatch,score):
    source=fitted()
    before=deepcopy(source.get_state())
    monkeypatch.setattr(implementation,'optimize_acqf_discrete',lambda *a,**k:
        (torch.tensor([[.5]],dtype=torch.double),torch.tensor(score)))
    with pytest.raises(ValueError,match='GP acquisition value'): source.suggest()
    assert source.get_state()==before


@pytest.mark.parametrize('domain_factory', [
    lambda: SearchSpace([Knob('x','ordinal',(0,99))]),
    lambda: SearchSpace([Knob('x','continuous',(0.,1.)),Knob('family','categorical',['a','b'])]),
])
def test_unqualified_joint_domain_refused_before_initial_design(domain_factory):
    source=GPSearcher(domain_factory(),seed=1)
    before=deepcopy(source.get_state())
    with pytest.raises(ValueError): source.suggest_batch(2)
    assert source.get_state()==before
    with pytest.raises(ValueError):
        Study(source,LocalExecutor(),lambda c:pytest.fail('unqualified domain dispatched'),max_concurrent=2, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')


def test_warm_wrapper_preserves_queue_without_claiming_joint_support():
    from hponas.warm_start import WarmStartSearcher
    from hponas.searchers_gp import GPqLogEISearcher
    base=GPqLogEISearcher(SearchSpace([Knob('x','continuous',(0.,1.))]))
    warm=WarmStartSearcher(base,[{'x':.2}])
    assert warm.support.joint_batch is False
    assert warm.capabilities['supports_batch'] is False


@pytest.mark.parametrize('field,value',[('mode','unknown'),('requested',True),('configs',[]),('log_acquisition',1.)])
def test_proposal_trace_corruption_is_refused_before_restore(field,value):
    source=GPSearcher(SearchSpace([Knob('x','ordinal',(0,5))]),seed=21)
    source.suggest_batch(2)
    before=deepcopy(source.get_state())
    corrupted=deepcopy(before); corrupted['proposal_batches'][0][field]=value
    with pytest.raises(ValueError): source.set_state(corrupted)
    assert source.get_state()==before


@pytest.mark.parametrize('crash_at',[1,2,4])
def test_public_study_pending_batch_resume_matches_uninterrupted(tmp_path,crash_at):
    domain=SearchSpace([Knob('x','ordinal',(0,5))])
    def make(fn):
        return Study(GPSearcher(domain,seed=21,initial_random_samples=2),LocalExecutor(),fn,
            budget=6,maximize=False,max_concurrent=2,study_name='joint',checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    expected=make(lambda c:(c['x']-2)**2).run()
    calls=[]
    def crash(config,trial_id):
        calls.append(trial_id)
        if len(calls)==crash_at: raise KeyboardInterrupt
        return (config['x']-2)**2
    interrupted=make(crash)
    with pytest.raises(KeyboardInterrupt): interrupted.run()
    committed=set(interrupted.results)
    retried=[]
    def resume(config,trial_id):
        retried.append(trial_id)
        return (config['x']-2)**2
    restored=make(resume); restored.load_checkpoint(tmp_path/'joint_checkpoint.json')
    actual=restored.run()
    assert not committed.intersection(retried)
    assert [r.objective_value for r in actual.history]==[r.objective_value for r in expected.history]
    assert len([e for e in restored._events if e['kind']=='suggest_batch'])==3
    assert len(restored.searcher.proposal_batches)==3
    assert restored.searcher.pending_locations()==[]
