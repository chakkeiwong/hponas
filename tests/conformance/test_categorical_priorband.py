"""Distribution and orchestration conformance for a finite PriorBand envelope."""
import ast
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction as F
import hashlib
from itertools import product
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from hponas import CategoricalPriorBandSearcher, Knob, SearchSpace, PriorBandScheduler
from hponas.categorical_prior import CategoricalPrior
from tests.conformance.test_prior_reference import vendor, policy  # noqa: F401


@pytest.fixture(scope='module')
def categorical_vendor():
    base = Path(__file__).resolve().parents[1]/'fixtures/neps_priorband_3f7475b'
    manifest = json.loads((base/'categorical-manifest.json').read_text())
    for file, digest in manifest['files'].items():
        assert hashlib.sha256((base/file).read_bytes()).hexdigest() == digest
    namespace = {'Parameter': object, 'np': np}
    tree = ast.parse((base/'categorical.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CategoricalParameter')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {'_compute_user_prior_probabilities', 'compute_prior'}]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'pinned-categorical', 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('confidence', ['low','medium','high'])
def test_categorical_prior_product_matches_pinned_source(categorical_vendor, confidence):
    space = SearchSpace([Knob('a','categorical',[0,1,2]),Knob('b','categorical',['u','v'])])
    law = CategoricalPrior(space, {'a':1,'b':'v'}, confidence=confidence)
    expected=[]
    for cell in law.cells:
        joint=1
        for knob in space.knobs:
            hp=categorical_vendor['CategoricalParameter']()
            hp.choices, hp.num_choices = knob.bounds, len(knob.bounds)
            hp.default, hp.value = law.default[knob.name], cell[knob.name]
            hp.default_confidence_score={'low':2,'medium':4,'high':6}[confidence]
            joint *= hp.compute_prior()
        expected.append(joint)
    assert list(map(float,law.prior_masses())) == pytest.approx(expected, abs=1e-15)
    assert sum(law.prior_masses()) == 1


class NeedChoice(Exception):
    def __init__(self, n):
        self.n=n


class RandomTape:
    def __init__(self, values):
        self.values=iter(values)
    def take(self, n):
        value=next(self.values,None)
        if value is None:
            raise NeedChoice(n)
        return value
    def uniform(self):
        # 1/4 and 3/4 reproduce exact Bernoulli(1/2) decisions in local_mutation.
        return .25+.5*self.take(2)


class FakeHP:
    is_fidelity=False
    def __init__(self, choices, value):
        self.choices, self.value=choices,value
    def mutate(self, **kwargs):
        choices=[x for x in self.choices if x!=self.value]
        # The retained categorical method shuffles choices, skips every copy of
        # self, and selects the first remaining label. Symmetry makes it uniform.
        return FakeHP(self.choices, choices[CURRENT_TAPE.take(len(choices))])


class FakeSpace:
    def __init__(self, values):
        self.hps={name:FakeHP(choices,value) for name,(choices,value) in values.items()}
    def keys(self):
        return self.hps.keys()
    def get(self, name):
        return self.hps[name]
    def is_equal_value(self, other, **kwargs):
        return all(hp.value==other.hps[name].value for name,hp in self.hps.items())


@pytest.mark.parametrize('attempts', [1,2,3])
def test_actual_retained_local_mutation_branches_equal_closed_form(attempts):
    global CURRENT_TAPE
    base=Path(__file__).resolve().parents[1]/'fixtures/neps_priorband_3f7475b'
    function=next(n for n in ast.parse((base/'utils.py').read_text()).body
                  if isinstance(n,ast.FunctionDef) and n.name=='local_mutation')
    namespace={'deepcopy':deepcopy,'SearchSpace':FakeSpace,'CategoricalParameter':FakeHP}
    namespace['FloatParameter']=namespace['IntegerParameter']=type('Unused',(),{})
    namespace['np']=SimpleNamespace(random=None)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])), 'pinned-local-mutation','exec'),namespace)
    original=FakeSpace({'a':([0,1],0),'b':([0,1,2],1)})
    stack=[((),F(1))]
    masses=defaultdict(F)
    while stack:
        tape,weight=stack.pop()
        CURRENT_TAPE=RandomTape(tape)
        namespace['np'].random=CURRENT_TAPE
        try:
            result=namespace['local_mutation'](original,patience=attempts)
        except NeedChoice as choice:
            stack.extend((tape+(value,),weight/choice.n) for value in range(choice.n))
        else:
            masses[tuple(hp.value for hp in result.hps.values())] += weight
    space=SearchSpace([Knob('a','categorical',[0,1]),Knob('b','categorical',[0,1,2])])
    law=CategoricalPrior(space,{'a':0,'b':1},mutation_attempts=attempts)
    assert law.mutation_masses(law.default)==tuple(masses[(cell['a'],cell['b'])] for cell in law.cells)
    assert masses[(0,1)]==F(1,4)**attempts


def test_reference_categorical_neighbour_choice_symmetry():
    # All permutations of the duplicated-current list induce equal counts for
    # the first non-current label. This is independent of the draw routine.
    from itertools import permutations
    for k in [2,3]:
        bag=list(range(k))+[0]*k
        counts=defaultdict(int)
        for order in permutations(bag):
            counts[next(x for x in order if x!=0)]+=1
        assert len(set(counts.values()))==1
    space=SearchSpace([Knob('a','categorical',[0,1]),Knob('b','categorical',[0,1])])
    law=CategoricalPrior(space,{'a':0,'b':0})
    p=law.mutation_masses(law.default)
    assert p[0]==F(1,4)**50 and sum(p)==1
    assert p[1]==p[2]==p[3]==(1-p[0])/3


def test_actual_priorband_portfolio_equals_reference_given_same_observations(vendor):
    space=SearchSpace([Knob('a','categorical',[0,1,2])])
    sampler=CategoricalPriorBandSearcher(space,{'a':0},rungs=[1,3,9])
    from hponas import Config
    rows=[]
    for i,(rung,loss,cell) in enumerate([(2,3,0),(2,1,1),(1,2,2),(1,0,0),(1,4,1)]):
        tid=str(i)
        sampler.trials[tid]=Config({'a':cell})
        sampler.policy.observe(tid,rung=3**rung,value=loss,work=3**rung)
        rows.append((rung,loss,cell))
    inc=sampler.trials[sampler.policy.incumbent()].values
    prior,inc_prior=sampler.law.prior_masses(),sampler.law.prior_masses(inc)
    reference=policy(vendor,[(r,l,(float(prior[c]),float(inc_prior[c]))) for r,l,c in rows])
    reference.inc_style='dynamic'
    for rung in range(3):
        expected=reference.set_sampling_weights_and_inc(rung)['weights']
        actual=sampler._mixture(rung,sampler.policy)
        assert {k:float(F(v)) for k,v in actual['mixture'].items()}==pytest.approx(expected,abs=1e-15)
        from hponas.prior_sampling import guarded_probabilities
        masses=guarded_probabilities([1]*3,list(map(F,actual['weights'])),F(actual['alpha']))
        mutation=sampler.law.mutation_masses(inc)
        expected_masses=[expected['random']/3+expected['prior']*float(p)+expected['inc']*float(m)
                         for p,m in zip(prior,mutation)]
        assert list(map(float,masses))==pytest.approx(expected_masses,abs=1e-15)


@pytest.mark.parametrize('bad', [lambda: SearchSpace([Knob('a','continuous',(0.,1.))]),
                               lambda: SearchSpace([Knob('a','categorical',[0,1]),Knob('b','categorical',[0,1],condition=('a',1))])],
                         ids=['bad0', 'bad1'])
def test_unsupported_reference_envelopes_refuse_instead_of_approximating(bad):
    bad = bad()
    with pytest.raises(ValueError,match='unconditional categorical'):
        CategoricalPriorBandSearcher(bad,{'a':0},rungs=[1,3,9])
