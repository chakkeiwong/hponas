"""Independent hypervolume counterexample and maintained vector batch recovery."""
import itertools
import json
import math

import pytest

from hponas import Config, Knob, SearchSpace, Result, MultiObjectiveBayesSearcher
from hponas.searchers.base import PendingSuggestionError


def objectives():
    return [dict(name='a',direction='max',lower=0.,upper=10.),
            dict(name='b',direction='max',lower=0.,upper=10.)]


def searcher(method='qlognehvi'):
    return MultiObjectiveBayesSearcher(SearchSpace([Knob('x','ordinal',(0,2))]),
        objectives=objectives(), seed=7, method=method, n_initial=2,
        candidate_count=3, mc_samples=8, fit_maxiter=4)


def observe(s, tid, x):
    s.trials[tid]=Config({'x':x})
    row=s.multi_objective_spec.observation(objectives={'a':float(x+1),'b':float(3-x)},constraints={},work=1)
    s.observe(Result(tid,0.,1.,1.,{'multi_objective':row}))


def test_public_joint_choice_beats_the_best_single_point_then_greedy(monkeypatch):
    import torch
    from botorch.acquisition.multi_objective import logei
    # Single A has area 6.25; B/C each 5. AB/AC have 8.75, BC has 9.
    # Thus starting with the best individual point cannot recover the best pair.
    points=[(2.5,2.5),(5.,1.),(1.,5.)]
    seen=[]
    class ExactHypervolume:
        def __call__(self,x):
            seen.append(x.shape[-2])
            scores=[]
            for batch in x:
                ids=[round(float(v)*2) for v in batch[:,0]]
                a,b=[points[i] for i in ids]
                area=a[0]*a[1]+b[0]*b[1]-min(a[0],b[0])*min(a[1],b[1])
                scores.append(math.log(area))
            return torch.tensor(scores,dtype=x.dtype)
    monkeypatch.setattr(logei,'qLogNoisyExpectedHypervolumeImprovement',lambda **kwargs:ExactHypervolume())
    s=searcher();observe(s,'a',0);observe(s,'b',1)
    batch=s.suggest_batch(2)
    assert sorted(c.values['x'] for c in batch)==[1,2]
    assert seen and set(seen)=={2}
    assert s.acquisition_trace[-1]['log_acquisition']==pytest.approx(math.log(9))
    assert s.acquisition_trace[-1]['joint_sets']==3


@pytest.mark.parametrize('method',['qlognehvi','chebyshev'])
def test_real_vendor_joint_score_matches_independent_enumeration_and_restores(method,monkeypatch):
    import torch
    from hponas.searchers.gp_searcher import GPSearcher
    original=GPSearcher._joint_finite
    checked=[]
    def capture(acquisition,choices,q):
        chosen,value=original(acquisition,choices,q)
        with torch.no_grad():
            independent=[(float(acquisition(choices[list(ids)].unsqueeze(0)).item()),ids)
                         for ids in itertools.combinations(range(len(choices)),q)]
        expected=max(independent,key=lambda pair:pair[0])
        assert value.item()==pytest.approx(expected[0],rel=1e-7,abs=1e-7)
        assert torch.equal(chosen,choices[list(expected[1])])
        checked.append(q)
        return chosen,value
    monkeypatch.setattr(GPSearcher,'_joint_finite',staticmethod(capture))
    s=searcher(method);observe(s,'a',0);observe(s,'b',2)
    checkpoint=json.loads(json.dumps(s.get_state()))
    first=s.suggest_batch(2)
    restored=searcher(method);restored.set_state(checkpoint)
    assert restored.suggest_batch(2)==first
    assert restored.acquisition_trace==s.acquisition_trace
    assert checked==[2,2]
    for i,c in enumerate(first):restored.trials['pending'+str(i)]=c
    remainder=restored.suggest_batch(2)
    assert len(remainder)==1
    assert all(c not in first for c in remainder)
    assert restored.acquisition_trace[-1]['pending_count']==2


def test_all_pending_waits_and_failure_does_not_advance_random_state(monkeypatch):
    s=searcher()
    for i in range(3):s.trials[str(i)]=Config({'x':i})
    before=json.dumps(s.get_state(),sort_keys=True)
    with pytest.raises(PendingSuggestionError):s.suggest_batch(2)
    assert json.dumps(s.get_state(),sort_keys=True)==before
    s=searcher();observe(s,'a',0);observe(s,'b',2)
    before=json.dumps(s.get_state(),sort_keys=True)
    from hponas.searchers.gp_searcher import GPSearcher
    def fail(*args):raise RuntimeError('acquisition failed')
    monkeypatch.setattr(GPSearcher,'_joint_finite',staticmethod(fail))
    with pytest.raises(RuntimeError,match='acquisition failed'):s.suggest_batch(2)
    assert json.dumps(s.get_state(),sort_keys=True)==before


@pytest.mark.parametrize('count',[0,9,True,1.5])
def test_invalid_batch_refused_without_state_change(count):
    s=searcher();before=json.dumps(s.get_state(),sort_keys=True)
    with pytest.raises(ValueError):s.suggest_batch(count)
    assert json.dumps(s.get_state(),sort_keys=True)==before
