import numpy as np
import pytest
import torch
from hponas_rl_lqr_scale.controller import LearnedController
from hponas_rl_lqr_scale.adapter import SACMember
from hponas_rl_lqr_scale.experiments import BASE,ROOT,read
from hponas_rl_lqr_scale.reference import LQRSpec

@pytest.mark.parametrize('case',['s1a5','s1a10','s10a5','s10a10'])
def test_learned_controller_matches_saved_diagnostic_and_export(case):
    phase='actions' if case.startswith('s1a') else 'states'
    r=next(x for x in read(BASE/(phase+'-result.json'))['rows'] if x['case']==case and x['method']=='symmetric')
    m=SACMember.restore(ROOT/r['checkpoint']['path'])
    for saved in r['greedy']:
        ctrl=LearnedController.from_member(m,saved['critic']);cert=ctrl.certificate()
        np.testing.assert_array_equal(ctrl.gains,saved['gains'])
        assert cert['feasible']==saved['feasible'] and cert['max_action_bound']==saved['max_action_bound']
        assert cert['exact_expected_cost']==saved['exact_cost']
        if cert['feasible']:
            network=ctrl.torch_module();x=np.full((1,m.specification.states),.1)
            for t in [0,15,29]:
                obs=torch.tensor(np.column_stack((x,np.full(1,(30-t)/30))),dtype=torch.float64)
                traced=torch.jit.trace(network,obs)
                np.testing.assert_allclose(traced(obs).numpy(),ctrl(x,t),rtol=0,atol=1e-14)
        else:
            with pytest.raises(ValueError):ctrl.torch_module()

def test_infeasible_controller_and_out_of_envelope_refused():
    s=LQRSpec.from_case('s10a5');g=np.ones((30,5,10));ctrl=LearnedController(g,s,'q1')
    assert not ctrl.certificate()['feasible'] and ctrl.certificate()['exact_expected_cost'] is None
    with pytest.raises(ValueError):ctrl.torch_module()
    with pytest.raises(ValueError):ctrl(np.ones((1,10)),0)
    with pytest.raises(ValueError):ctrl(np.zeros((1,10)),30)
    with pytest.raises(ValueError):ctrl(np.zeros((1,9)),0)
    with pytest.raises(ValueError):LearnedController(np.zeros((3,5,10)),s,'q1')
