"""Actual neural construction versus high precision fitting and exact ODE."""
from copy import deepcopy

import numpy as np
import pytest

from workloads.bank_neural import configurations,build,evaluate,measure,transfer,validate_model
from workloads.bank_solvers import solver_profile,task_residuals,feasible,CONSTRAINTS,TOLERANCE
from validation.bank_references import neural_reference


def test_all_32_neural_models_match_independent_high_precision_fit_and_derivatives():
    profile=solver_profile();fold=profile.declaration.tuning_folds[0]
    train=[profile.records[i] for i in fold.train_ids]
    for config in configurations():
        row=profile.evaluate(config,fold);model=row['model']
        nodes=[profile.records[i]['x'] for i in fold.score_ids]+[0.]
        reference=neural_reference(config,train,nodes)
        assert model['output']==pytest.approx(reference['coefficients'],rel=2**-30,abs=2**-30)
        actual=evaluate(model,nodes)
        assert actual['values']==pytest.approx(reference['values'],rel=2**-30,abs=2**-30)
        assert actual['derivatives']==pytest.approx(reference['derivatives'],rel=2**-30,abs=2**-30)
        h=2**-17
        finite=(np.array(evaluate(model,[x+h for x in nodes])['values'])-np.array(evaluate(model,[x-h for x in nodes])['values']))/(2*h)
        assert finite==pytest.approx(actual['derivatives'],rel=0,abs=2**-18)
        width=config['width'];depth=config['depth'];rep=config['representation']
        count=2*width+(width*width+width if depth==2 else 0)+rep+1
        assert measure(model)['parameters']==count
        assert row['work']==10*(4*(width+(width*width if depth==2 else 0))+width*depth)
        assert row['metrics']['trainable_parameters']==rep+1
        assert row['assessment']['status']==('feasible' if feasible(row['constraints']) else 'infeasible')


def test_known_constructed_square_solution_and_low_loss_infeasibility():
    profile=solver_profile();config={'width':2,'depth':1,'activation':'square','representation':1,'ridge':0.}
    for fold in profile.declaration.tuning_folds+profile.declaration.final_folds:
        row=profile.evaluate(config,fold)
        assert row['model']['output']==pytest.approx([0.,1.],abs=2**-38)
        assert feasible(row['constraints'])
        assert row['constraints']['derivative_residual']<TOLERANCE
    # A small normalized scalar from down-weighting the ODE cannot pass it.
    residual=task_residuals([0.]*4,[0.]*4,[-.75,-.25,.25,.75],0.)
    assert residual['boundary_residual']==0
    assert 1e-12*residual['loss']<TOLERANCE
    constraints={key:0. for key in CONSTRAINTS}
    constraints.update({k:residual[k] for k in ('value_residual','derivative_residual','boundary_residual')})
    assert not feasible(constraints)


def test_architecture_coordinates_change_constructed_arrays_and_transfer_refuses():
    base={'width':2,'depth':1,'activation':'square','representation':1,'ridge':0.}
    original=build(base)
    for key,value in [('width',4),('depth',2),('activation','tanh'),('representation',2)]:
        changed={**base,key:value};model=build(changed)
        assert model!=original
        with pytest.raises(ValueError,match='Incompatible'):transfer(original,changed)
    transferred=transfer(original,{**base,'ridge':.0625})
    assert transferred['output']==original['output'] and transferred['layers']==original['layers']
    bad=deepcopy(original);bad['layers'][0]['weight'][0][0]=2
    with pytest.raises(ValueError,match='arrays differ'):validate_model(bad)
    with pytest.raises(ValueError,match='domain'):evaluate(original,[-1.01])
    with pytest.raises(ValueError,match='domain'):task_residuals([1.],[1.],[1.01],0.)
