"""The same real neural coordinates across prediction and constrained solving."""
import pytest

from workloads.bank_neural import configurations,evaluate,measure,transfer
from workloads.bank_solvers import solver_profile
from workloads.bank_nas import nas_prediction_profile
from validation.bank_references import neural_reference


def test_all_prediction_architectures_match_independent_fit_and_actual_parameters():
    profile=nas_prediction_profile();fold=profile.declaration.tuning_folds[0]
    train=[profile.records[i] for i in fold.train_ids];nodes=[profile.records[i]['x'] for i in fold.score_ids]
    for config in configurations():
        actual=profile.evaluate(config,fold);reference=neural_reference(config,train,nodes,task='prediction')
        assert actual['model']['output']==pytest.approx(reference['coefficients'],rel=2**-30,abs=2**-30)
        assert actual['predictions']['values']==pytest.approx(reference['values'],rel=2**-30,abs=2**-30)
        assert actual['predictions']['derivatives']==pytest.approx(reference['derivatives'],rel=2**-30,abs=2**-30)
        assert actual['loss']==pytest.approx(sum((v-x*x)**2 for v,x in zip(reference['values'],nodes))/4,abs=2**-30)
        assert measure(actual['model'])['parameters']==actual['objectives']['parameters']
        w,d=config['width'],config['depth']
        assert actual['work']==9*(4*(w+(w*w if d==2 else 0))+w*d)


def test_cross_profile_constructor_portability_preserves_arrays_but_not_training_semantics():
    prediction=nas_prediction_profile();solver=solver_profile()
    for config in configurations():
        p=prediction.evaluate(config,prediction.declaration.tuning_folds[0])
        s=solver.evaluate(config,solver.declaration.tuning_folds[0])
        assert p['model']['layers']==s['model']['layers']
        assert p['model']['config']==s['model']['config']
        copied=transfer(p['model'],config)
        assert evaluate(copied,[.125,.375])['values']==evaluate(p['model'],[.125,.375])['values']
        with pytest.raises(ValueError,match='Incompatible'):
            transfer(p['model'],{**config,'activation':'tanh' if config['activation']=='square' else 'square'})
    exact={'width':2,'depth':1,'activation':'square','representation':1,'ridge':0.}
    for profile in (prediction,solver):
        row=profile.evaluate(exact,profile.declaration.final_folds[0])
        assert row['loss']<2**-38
        assert row['model']['output']==pytest.approx([0.,1.],abs=2**-38)
