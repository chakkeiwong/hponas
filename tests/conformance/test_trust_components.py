"""Independent controller traces and mixed-kernel geometry conformance."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from hponas import Knob,SearchSpace
import hponas.trust_controller as maintained
from hponas.trust_controller import Controller,Options
from hponas.trust_space import HammingKernel,MixedKernel,TrustSpace,config_key


ROOT=Path(__file__).resolve().parents[2]


def test_retained_independent_rational_controller_oracle(monkeypatch):
    base=ROOT/'docs/program/evidence/2026-10-06/trust-controller-candidate-01'
    monkeypatch.setitem(sys.modules,'controller',maintained)
    spec=importlib.util.spec_from_file_location('retained_controller_oracle',base/'verify_controller.py')
    reference=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    result={'checks':[]}
    reference.check(json.loads((base/'plan.json').read_text()),result)
    assert result['enumeration']['transitions']==52488
    assert len(result['checks'])==34


def test_relative_improvement_counters_match_original_turbo_source():
    base=ROOT/'docs/program/evidence/2026-10-07/trust-implementation-01/reference'
    manifest=json.loads((base/'manifest.json').read_text())
    text=(base/'turbo_1.py').read_text()
    assert hashlib.sha256(text.encode()).hexdigest()==manifest['files']['turbo_1.py']
    cls=next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef))
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_adjust_length')
    namespace={'np':np,'math':math}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'pinned-adjust-length','exec'),namespace)
    options=Options(1,.5,.125,2.,3,2,relative_improvement=.001)
    for word in product(['small','large','worse'],repeat=6):
        model=Controller(options)
        model.initialize('initial',[.5],100.)
        original=SimpleNamespace(_fX=np.array([100.]),length=.5,length_max=2.,succcount=0,failcount=0,succtol=3,failtol=2)
        for i,symbol in enumerate(word):
            best=float(original._fX.min())
            outcome=best+{'small':-.0001*abs(best),'large':-.01*abs(best),'worse':1.}[symbol]
            model.propose(str(i),[.5],[1.])
            model.observe(str(i),outcome)
            namespace['_adjust_length'](original,np.array([outcome]))
            original._fX=np.append(original._fX,outcome)
            state=model.snapshot()
            assert (state['length'],state['successes'],state['failures'])==(original.length,original.succcount,original.failcount)
            assert state['best']==min(original._fX)
            if state['status']=='needs_restart':
                model.initialize('restart-'+str(i),[.5],100.)
                original._fX=np.array([100.]); original.length=.5; original.succcount=original.failcount=0


def test_failed_trial_counts_work_without_inventing_an_objective_and_recovers():
    options=Options(1,.5,.125,2.,3,1)
    model=Controller(options)
    model.initialize('initial',[.5],1.)
    model.propose('failed',[.6],[1.])
    before=model.state_dict()
    with pytest.raises(ValueError): model.fail('foreign')
    assert model.state_dict()==before
    model.fail('failed')
    assert model.snapshot()['best']==1 and model.snapshot()['length']==.25
    assert Controller.from_state(model.state_dict(),options).state_dict()==model.state_dict()


def test_product_kernel_matches_closed_formula_and_categorical_relabeling():
    kernel=MixedKernel(2,2).double()
    kernel.numeric.lengthscale=torch.tensor([.5,2.],dtype=torch.double)
    kernel.categorical.lengthscale=torch.tensor([.7,1.2],dtype=torch.double)
    x=torch.tensor([[.1,.2,1,2],[.5,.6,2,2],[.3,.8,1,0]],dtype=torch.double)
    actual=kernel(x,x).to_dense().detach().numpy()
    expected=np.empty((3,3))
    for i in range(3):
        for j in range(3):
            r=math.sqrt(((float(x[i,0]-x[j,0]))/.5)**2+((float(x[i,1]-x[j,1]))/2)**2)
            h=(int(x[i,2]!=x[j,2]))/.7+(int(x[i,3]!=x[j,3]))/1.2
            expected[i,j]=(1+math.sqrt(5)*r+5*r*r/3)*math.exp(-math.sqrt(5)*r-h)
    np.testing.assert_allclose(actual,expected,rtol=1e-13,atol=1e-15)
    renamed=x.clone()
    renamed[:,2]=17-3*x[:,2]
    renamed[:,3]=5*x[:,3]+11
    torch.testing.assert_close(kernel(renamed,renamed).to_dense(),kernel(x,x).to_dense(),rtol=0,atol=0)
    assert np.linalg.eigvalsh(actual).min()>0
    torch.testing.assert_close(kernel(x,x,diag=True),torch.ones(3,dtype=torch.double))


def mixed_space():
    return TrustSpace(SearchSpace([Knob('family','categorical',['a','b']),Knob('width','integer',(1,3)),
        Knob('rate_a','continuous',(.01,1.),transform='log',condition=('family','a')),
        Knob('rate_b','continuous',(.01,.99),transform='logit',condition=('family','b'))]))


def test_conditional_embedding_has_no_inactive_value_and_positive_covariance():
    space=mixed_space()
    configs=[{'family':'a','width':i,'rate_a':v} for i in [1,2,3] for v in [.01,.1,1.]]
    configs += [{'family':'b','width':i,'rate_b':v} for i in [1,2,3] for v in [.1,.5,.9]]
    features=torch.tensor([space.features(c) for c in configs],dtype=torch.double)
    kernel=MixedKernel(space.n_numeric,len(space.categorical)).double()
    assert torch.linalg.eigvalsh(kernel(features,features).to_dense()).min()>-1e-12
    a,b=space.features(configs[0]),space.features(configs[-1])
    assert a[3:5]==[0.,0.] and b[1:3]==[0.,0.]
    with pytest.raises(ValueError): space.features({**configs[0],'rate_b':.5})


def test_mixed_candidates_obey_their_typed_region_and_activate_legal_children():
    space=mixed_space()
    center={'family':'a','width':2,'rate_a':.1}
    candidates,region,finite=space.candidates(center,.2,[1.]*4,np.random.default_rng(0),count=64,exclude=[center])
    assert not finite and len(candidates)==64
    assert len({config_key(c) for c in candidates})==64
    assert {c['family'] for c in candidates}=={'a','b'}
    assert all(space.contains(center,c,region) for c in candidates)
    assert all(('rate_a' in c)==(c['family']=='a') and ('rate_b' in c)==(c['family']=='b') for c in candidates)
    for c in candidates:
        space.validate(c)
        assert c['width']==2
    again=space.candidates(center,.2,[1.]*4,np.random.default_rng(0),count=64,exclude=[center])
    assert again==(candidates,region,finite)


def test_finite_neighborhood_is_exhaustive_and_huge_domains_are_not_materialized(monkeypatch):
    space=TrustSpace(SearchSpace([Knob('c','categorical',['a','b']),Knob('n','integer',(1,3))]))
    center={'c':'a','n':2}
    choices,region,finite=space.candidates(center,.2,[1.,1.],np.random.default_rng(0),exclude=[center])
    assert finite and choices==[{'c':'b','n':2}]
    empty,_,finite=space.candidates(center,.2,[1.,1.],np.random.default_rng(0),exclude=[center,*choices])
    assert finite and empty==[]
    huge=TrustSpace(SearchSpace([Knob('n','integer',(1,10**12))]))
    class ForbiddenRange:
        def __init__(self,*args): pass
        def __iter__(self): raise AssertionError('Forbidden giant-domain enumeration')
        def __len__(self): raise AssertionError('Forbidden giant-domain length')
    monkeypatch.setattr('hponas.trust_space.range',ForbiddenRange,raising=False)
    assert huge.finite_configs() is None


def test_continuous_geometry_matches_primary_controller_and_ordinal_order():
    space=TrustSpace(SearchSpace([Knob('x','continuous',(0.,1.)),Knob('y','continuous',(0.,1.))]))
    center={'x':.25,'y':.75}
    controller=Controller(Options(2,.5,.125,2.,3,2))
    controller.initialize('a',[.25,.75],0.)
    box=controller.bounds([1.,4.])
    region=space.region(center,.5,[1.,4.])
    assert region['numeric_bounds']=={'x':[box['lower'][0],box['upper'][0]],'y':[box['lower'][1],box['upper'][1]]}
    ordinal=TrustSpace(SearchSpace([Knob('n','integer',(1,5))]))
    assert ordinal.features({'n':3})==[.5]
