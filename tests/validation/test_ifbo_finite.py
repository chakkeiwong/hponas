"""Adverse evidence, consumed allocation and success-gate refusal tests."""
from copy import deepcopy
import json
import numpy as np
import pytest

from validation.ifbo_finite_contract import contract
from validation.ifbo_finite_reference import verify_updates, exact, optimum, close
from validation.ifbo_finite_campaign import consume
from validation.evidence import decision


def raw_arm():
    initial=[2.,3.]
    q=np.array([[.6,-.8],[.8,.6]])
    h=q@np.diag([1.,3.])@q.T
    trace=[]
    for i,x in enumerate([.2,.4,.6]):
        state=q@np.array(initial)
        for step in range(1,9):
            state=state-(.025+.6*x)*h@state
            trace.append({'id':i,'update':{'x':x,'step':step,'state':state.tolist(),
                         'loss':float(state@state/13)}})
    last=[r for r in trace if r['update']['step']==8]
    selected=min(last,key=lambda r:r['update']['loss'])['id']
    return initial,{'trace':trace,'selected_id':selected,'gradient_updates':32,
                   'certification':[deepcopy(r['update']) for r in trace if r['id']==selected]}


def test_direct_matrix_training_matches_independent_spectral_reference():
    initial,arm=raw_arm()
    verify_updates(initial,arm)
    eta,loss=optimum(initial)
    for shift in [-.05,-.005,.005,.05]:
        assert exact(initial,(eta+shift-.025)/.6,8)[1]>loss


@pytest.mark.parametrize('corruption',['state','loss','coordinate','step','selection','work','missing','certificate','nonfinite'])
def test_coherent_or_partial_training_evidence_is_refused(corruption):
    initial,arm=raw_arm()
    if corruption=='state':arm['trace'][7]['update']['state'][0]+=.01
    elif corruption=='loss':arm['trace'][3]['update']['loss']+=.01
    elif corruption=='coordinate':arm['trace'][1]['update']['x']+=.01
    elif corruption=='step':arm['trace'][1]['update']['step']=3
    elif corruption=='selection':arm['selected_id']=(arm['selected_id']+1)%3
    elif corruption=='work':arm['gradient_updates']=31
    elif corruption=='missing':arm['trace'].pop()
    elif corruption=='certificate':arm['certification'][0]['x']+=.01
    else:arm['trace'][3]['update']['loss']=float('nan')
    with pytest.raises(ValueError):verify_updates(initial,arm)


def test_interrupted_reconstruction_consumes_its_allocation(tmp_path):
    assert [consume(tmp_path) for _ in range(3)]==[1,2,3]
    with pytest.raises(ValueError,match='exhausted'):consume(tmp_path)
    assert len(list(tmp_path.glob('*-start.json')))==3


def test_claimed_pass_cannot_replace_finite_raw_evidence():
    assert decision('V15a',{'passed':True,'verdict':'PASS'})=='INCONCLUSIVE'


def test_integration_is_refused_before_directory_creation(tmp_path):
    from validation.run_validation_with_audit import ValidationRunner
    with pytest.raises(ValueError,match='V15b is not frozen'):
        ValidationRunner('V15b',artifact_root=tmp_path)
    assert not list(tmp_path.iterdir())


def test_contract_does_not_alias_and_retains_cancellation():
    a=contract();a['slots'].clear()
    assert len(contract()['slots'])==6
    assert 'cancel' in contract()['fail'] and 'cancel' in contract()['inconclusive']
    assert contract()['allocation']['maximum_gradient_updates_including_replays']==1536


@pytest.mark.parametrize('a,b',[(float('nan'),0),(float('inf'),0),([1],[1,1]),(0,1)])
def test_nonfinite_shape_or_numerical_substitution_rejected(a,b):
    with pytest.raises(ValueError):close(a,b)
