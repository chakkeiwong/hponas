"""Independent joint densities, rational integrators and handoff counterexamples."""
from copy import deepcopy
from itertools import product
import math

import pytest

from validation.bank_references import gaussian_sequence_reference, leapfrog_reference
from workloads.bank_inference import (kalman,filter_sequences,inference_profile,leapfrog,
    native_handoff,affine_transport,verify_transport,TARGET,DEVELOPMENT_STATES,VERIFICATION_STATES)


@pytest.mark.parametrize('r',[.25,1.,4.])
@pytest.mark.parametrize('values',[(1.,-.5,.75),(.5,0.,-.25),(.75,-.25,.5)])
def test_kalman_likelihood_matches_independent_joint_density(r,values):
    actual=kalman(values,r)
    assert actual['negative_log_likelihood']==pytest.approx(gaussian_sequence_reference(values,r),rel=2**-38,abs=2**-38)
    assert actual['trace'][0]['innovation_variance']==.5+r
    assert all(row['filtered_variance']>0 for row in actual['trace'])


def test_independent_sequences_reset_and_duplicate_times_refuse():
    rows=[{'group':g,'time':i,'y':y} for g in ('a','b') for i,y in enumerate((1.,-.5,.75),1)]
    actual=filter_sequences(rows,1.)
    assert actual['a']==actual['b']
    assert filter_sequences(list(reversed(rows)),1.)==actual
    changed=deepcopy(rows);changed[1]['time']=1
    with pytest.raises(ValueError,match='unique'): filter_sequences(changed,1.)


@pytest.mark.parametrize('r',[0,-1,float('nan'),True])
def test_invalid_inference_variance_refused(r):
    with pytest.raises(ValueError): kalman([0.,1.],r)


def test_every_native_pair_and_state_matches_rational_matrix_and_correction():
    result=native_handoff()
    assert len(result['verified_pairs'])==9
    for row in result['candidates']:
        c=row['candidate'];assert row['status']=='verified'
        for phase,states in [('development',DEVELOPMENT_STATES),('fresh',VERIFICATION_STATES)]:
            assert len(row[phase]['records'])==len(states)
            for check,state in zip(row[phase]['records'],states):
                expected=leapfrog_reference(state,c['step_size'],c['leapfrog_steps'])
                assert expected['determinant']==1
                for key in ('position','momentum','log_acceptance'):
                    assert check['result'][key]==pytest.approx(expected[key],rel=2**-40,abs=2**-40)


def test_fresh_failure_rejects_only_that_pair_after_development_passed():
    def corrupted(state,h,n):
        value=leapfrog(state,h,n)
        if tuple(state)==(.5,.25) and h==.5 and n==2: value['position']+=.1
        return value
    result=native_handoff(proposal=corrupted)
    assert len(result['verified_pairs'])==8
    failed=[r for r in result['candidates'] if r['status']=='rejected']
    assert len(failed)==1 and failed[0]['development']['status']=='verified'
    assert failed[0]['fresh']['status']=='failed' and failed[0]['failure_phase']=='fresh'


@pytest.mark.parametrize('defect',['missing','constant','changed_target'])
def test_missing_correction_or_changed_target_cannot_be_verified(defect):
    def bad(state,h,n):
        value=leapfrog(state,h,n)
        if defect=='missing':value.pop('log_acceptance')
        elif defect=='constant':value['log_acceptance']=0.
        else:value['target_id']='other_target'
        return value
    c={'step_size':.5,'leapfrog_steps':1,'target_id':TARGET}
    result=native_handoff([c],proposal=bad)
    assert result['verified_pairs']==[] and result['candidates'][0]['status']=='rejected'


def test_posterior_metrics_do_not_rank_or_delete_verified_candidates():
    first=native_handoff(posterior_assessment={'Rhat':100,'ESS':0,'MCSE':999})
    second=native_handoff(posterior_assessment={'Rhat':1,'ESS':1e9,'MCSE':0})
    assert first['verified_pairs']==second['verified_pairs']
    assert first['candidates']==second['candidates']
    assert not first['posterior_assessment_used_for_selection']
    result=native_handoff([{'step_size':.5,'leapfrog_steps':1,'target_id':'changed'}])
    assert not result['verified_pairs']
    assert result['candidates'][0]['failure_phase']=='candidate'


def test_transports_preserve_inverse_density_and_jacobian_on_all_declared_pairs():
    for a,b,x in product((.5,1.,2.),(-1.,0.,1.),(-2.,0.,1.5)):
        record=affine_transport(x,a,b)
        assert record['inverse']==x
        assert record['log_density']==pytest.approx(-math.log(a*math.sqrt(2*math.pi))-x*x/2,abs=2**-38)
        assert verify_transport(record)
    record=affine_transport(1.,2.,-1.)
    bad={**record,'log_abs_jacobian':0.}
    with pytest.raises(ValueError,match='Jacobian'): verify_transport(bad)
    bad=dict(record);bad.pop('log_abs_jacobian')
    with pytest.raises(ValueError,match='Jacobian'):verify_transport(bad)
    with pytest.raises(ValueError):affine_transport(1.,0.,0.)
