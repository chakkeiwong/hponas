"""Structural intervention and conditional-moment checks independent of fitting."""
from copy import deepcopy
from itertools import product

import pytest

from workloads.bank_causal import causal_profile, causal_loss
from workloads.bank_workflow import validate_rows
from validation.bank_references import causal_reference

TOL=2.**-38


def test_all_candidates_crossfit_and_final_match_conditional_moment_reference():
    profile=causal_profile()
    for fold in profile.declaration.tuning_folds+profile.declaration.final_folds:
        copies=2 if fold.name=='final_refit' else 1
        for ridge,alpha in product((0,.25,1),(0,1)):
            actual=profile.evaluate({'ridge':ridge,'alpha':alpha},fold)
            expected=causal_reference(ridge,alpha,training_groups=copies)
            assert actual['loss']==pytest.approx(expected['loss'],rel=TOL,abs=TOL)
            for key in ('outcome_mse','treatment_brier'):
                assert actual['metrics'][key]==pytest.approx(expected[key],rel=TOL,abs=TOL)
            effect=actual['assessment']['effect']
            assert actual['assessment']['status']=='identified_finite_model'
            assert effect==pytest.approx(expected['effect'],rel=TOL,abs=TOL)
            if ridge==0 or alpha==0: assert effect==pytest.approx(2.,abs=TOL)
            else: assert abs(effect-2)>TOL  # Both nuisance biases remain visible.
            assert set(actual['model']['train_ids'])==set(fold.train_ids)
            assert not set(actual['model']['train_ids']).intersection(fold.score_ids)


def test_structural_intervention_reference_is_not_predictive_fit():
    effects=[(1+x+2+noise)-(1+x+noise) for x,noise in product((-1,1),(-1,1))]
    assert effects==[2,2,2,2]
    profile=causal_profile();fold=profile.declaration.tuning_folds[0]
    actual=profile.evaluate({'ridge':0,'alpha':0},fold)
    assert actual['metrics']['outcome_mse']==1  # Irreducible finite noise remains.
    assert actual['assessment']['effect']==2


@pytest.mark.parametrize('alpha',[0,1])
def test_smoothing_never_repairs_missing_raw_overlap(alpha):
    profile=causal_profile(overlap=False);fold=profile.declaration.tuning_folds[0]
    actual=profile.evaluate({'ridge':0,'alpha':alpha},fold)
    assert actual['assessment']['status']=='unsupported_overlap'
    assert actual['assessment']['effect'] is None
    assert actual['assessment']['bounds']==[-8,8]
    assert actual['model']['raw_support']=={'-1':[8,0],'1':[0,8]}
    if alpha: assert all(0<p<1 for p in actual['model']['propensity'].values())


def test_undeclared_identification_does_not_change_loss_or_create_an_effect():
    normal=causal_profile();unknown=causal_profile(identified=False)
    a=normal.evaluate({'ridge':0,'alpha':0},normal.declaration.tuning_folds[0])
    b=unknown.evaluate({'ridge':0,'alpha':0},unknown.declaration.tuning_folds[0])
    assert a['loss']==b['loss']
    assert b['assessment']['status']=='unidentified' and b['assessment']['effect'] is None
    assert b['assessment']['bounds']==[-8,8]


def test_crossfit_refuses_reused_rows_entities_and_untyped_assumptions():
    profile=causal_profile();train,score=validate_rows(profile.records,profile.declaration.tuning_folds[0])
    with pytest.raises(ValueError,match='rows overlap'): causal_loss({'ridge':0,'alpha':0},train,train)
    changed=deepcopy(score);changed[0]['group']=train[0]['group']
    with pytest.raises(ValueError,match='entity groups'): causal_loss({'ridge':0,'alpha':0},train,changed)
    changed=deepcopy(score);changed[0]['exogeneity']='yes'
    with pytest.raises(ValueError,match='assumptions'): causal_loss({'ridge':0,'alpha':0},train,changed)
