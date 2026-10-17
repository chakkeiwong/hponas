"""Original numerical prior sources against direct laws and integer bin integrals."""
import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import truncnorm

from hponas import Knob, SearchSpace
from hponas.product_prior import ProductPrior
from tests.conformance.test_prior_reference import policy, vendor  # noqa: F401


@pytest.fixture(scope='module')
def numeric_vendor():
    base=Path(__file__).resolve().parents[1]/'fixtures/neps_priorband_3f7475b'
    manifest=json.loads((base/'numeric-manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
    class Parameter:
        def __init__(self, **kwargs):
            self.is_fidelity=kwargs.get('is_fidelity',False)
    namespace={'Parameter':Parameter}
    for name in ['numerical.py','float.py','integer.py']:
        tree=ast.parse((base/name).read_text())
        tree.body=[n for n in tree.body if not (isinstance(n,ast.ImportFrom) and n.level)]
        exec(compile(tree,str(base/name),'exec'),namespace)
    return namespace


@pytest.mark.parametrize('kind', ['continuous','ordinal'])
@pytest.mark.parametrize('transform', ['none','log'])
@pytest.mark.parametrize('confidence', ['low','medium','high'])
@pytest.mark.parametrize('center', [2,4,7])
def test_scores_and_sampling_quantiles_match_original(numeric_vendor,kind,transform,confidence,center,monkeypatch):
    law=ProductPrior(SearchSpace([Knob('x',kind,(2,7),transform=transform)]),{'x':center},confidence=confidence)
    cls=numeric_vendor['FloatParameter' if kind=='continuous' else 'IntegerParameter']
    hp=cls(2,7,log=transform=='log',default=center,default_confidence=confidence)
    for x in [2,3,4,5,6,7]:
        hp.value=x
        assert math.exp(law.log_score({'x':x}))==pytest.approx(hp.compute_prior(),rel=3e-14,abs=1e-15)
    float_hp=hp if kind=='continuous' else hp.float_hp
    dist,std=float_hp._get_truncnorm_prior_and_std()
    for p in [2**-30,.01,.25,.5,.95,1-2**-30]:
        float_hp._get_truncnorm_prior_and_std=lambda:(SimpleNamespace(rvs=lambda:dist.ppf(p)),std)
        hp.sample(user_priors=True)
        actual=law.quantile('x',p)
        assert actual==hp.value if kind=='ordinal' else actual==pytest.approx(hp.value,rel=2e-14)
        monkeypatch.setattr(np.random,'uniform',lambda low,high:low+(high-low)*p)
        hp.sample(user_priors=False)
        actual=law.quantile('x',p,mode='base')
        assert actual==hp.value if kind=='ordinal' else actual==pytest.approx(hp.value,rel=2e-14)


@pytest.mark.parametrize('transform', ['none','log'])
@pytest.mark.parametrize('mode', ['base','prior','mutation'])
@pytest.mark.parametrize('center', [1,3,5])
def test_integer_bin_probabilities_match_independent_quadrature(transform,mode,center):
    law=ProductPrior(SearchSpace([Knob('x','integer',(1,5),transform=transform)]),{'x':center})
    low,high=1-.499999,5+.499999
    transform_value=math.log if transform=='log' else float
    a,b=transform_value(low),transform_value(high)
    mu=transform_value(center)
    sigma=(b-a)*.25
    z=quad(lambda x:math.exp(-.5*((x-mu)/sigma)**2),a,b,epsabs=1e-13)[0]
    expected=[]
    for i in range(1,6):
        left,right=transform_value(max(low,i-.5)),transform_value(min(high,i+.5))
        if mode=='base':
            expected.append((right-left)/(b-a))
        else:
            expected.append(quad(lambda x:math.exp(-.5*((x-mu)/sigma)**2)/z,left,right,epsabs=1e-13)[0])
    masses=law.integer_masses('x',mode=mode)
    assert masses==pytest.approx(expected,abs=3e-15)
    assert sum(masses)==pytest.approx(1,abs=1e-15)


@pytest.mark.parametrize('kind', ['continuous','ordinal'])
@pytest.mark.parametrize('transform', ['none','log'])
def test_original_mutation_transform_including_integer_rounding(numeric_vendor,kind,transform,monkeypatch):
    law=ProductPrior(SearchSpace([Knob('x',kind,(1,5),transform=transform)]),{'x':2})
    cls=numeric_vendor['FloatParameter' if kind=='continuous' else 'IntegerParameter']
    hp=cls(1,5,log=transform=='log',default=2)
    hp.value=2
    proxy=hp if kind=='continuous' else hp.float_hp
    for p in [.01,.2,.4,.7,.99]:
        location=proxy._normalize_value(2)
        candidate=float(truncnorm(-location/.25,(1-location)/.25,loc=location,scale=.25).ppf(p))
        monkeypatch.setattr(np.random,'normal',lambda *args:candidate)
        expected=hp.mutate(std=.25).value
        assert law.quantile('x',p,mode='mutation')==pytest.approx(expected,abs=2e-15)


def test_integer_rounding_can_leave_a_selected_coordinate_unchanged(numeric_vendor,monkeypatch):
    hp=numeric_vendor['IntegerParameter'](1,5,default=3)
    hp.value=3
    # The underlying float changes from 3 to 3.1, then rounds back to 3.
    unit=hp.float_hp._normalize_value(3.1)
    monkeypatch.setattr(np.random,'normal',lambda *args:unit)
    assert hp.mutate(std=.25).value==3
    law=ProductPrior(SearchSpace([Knob('x','integer',(1,5))]),{'x':3})
    probability=law.integer_masses('x',mode='mutation')[2]
    assert 0<probability<1
    assert ((1+probability)/2)**50>Fraction(1,2)**50


def test_fifty_failed_mutation_attempts_retain_the_original_config():
    law=ProductPrior(SearchSpace([Knob('x','categorical',['a','b']),Knob('n','integer',(1,5))]),
                      {'x':'a','n':3},mutation_rate=0)
    rng=random.Random(0)
    before=deepcopy(rng.getstate())
    assert law.sample(rng,mode='mutation')==law.default
    assert rng.getstate()==before


@pytest.mark.parametrize('knobs,default', [
    (lambda: [Knob('a','categorical',['x','y']),Knob('b','continuous',(0.,1.),condition=('a','x'))],{'a':'x','b':.5}),
    (lambda: [Knob('x','continuous',(.1,.9),transform='logit')],{'x':.5}),
    (lambda: [Knob('x','categorical',[True,False])],{'x':True}),
], ids=['knobs0-default0', 'knobs1-default1', 'knobs2-default2'])
def test_reference_scope_refuses_undefined_products(knobs,default):
    # Construct valid coordinates during the test, before the expected refusal.
    space = SearchSpace(knobs())
    with pytest.raises(ValueError):
        ProductPrior(space,default)


def test_full_numerical_portfolio_matches_pinned_dynamic_policy(vendor,numeric_vendor):
    from hponas import Config,ProductPriorBandSearcher
    space=SearchSpace([Knob('x','continuous',(1.,9.),transform='log')])
    sampler=ProductPriorBandSearcher(space,{'x':2.},rungs=[1,3,9])
    observations=[(2,3,1.),(2,1,4.),(1,2,8.),(1,0,2.),(1,4,3.)]
    for i,(rung,loss,x) in enumerate(observations):
        sampler.trials[str(i)]=Config({'x':x})
        sampler.policy.observe(str(i),rung=3**rung,value=loss,work=3**rung)
    incumbent=sampler.trials[sampler.policy.incumbent()].values['x']
    priors=[numeric_vendor['FloatParameter'](1,9,log=True,default=center,default_confidence='medium')
            for center in [2.,incumbent]]
    rows=[]
    for rung,loss,x in observations:
        for hp in priors: hp.value=x
        rows.append((rung,loss,tuple(hp.compute_prior() for hp in priors)))
    reference=policy(vendor,rows)
    reference.inc_style='dynamic'
    for rung in range(3):
        sampler._rung_index=rung
        actual={key:float(Fraction(v)) for key,v in sampler._mixture()['mixture'].items()}
        assert actual==pytest.approx(reference.set_sampling_weights_and_inc(rung)['weights'],abs=1e-15)
