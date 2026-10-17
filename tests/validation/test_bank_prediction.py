"""Independent finite formulas and scientific adverse cases for prediction."""
from copy import deepcopy
from dataclasses import replace
import math

import pytest

from validation.bank_references import ar_reference, probability_reference, ridge_reference
from workloads.bank_prediction import prediction_profile, predict, event_counts
from workloads.bank_workflow import validate_rows

TOL=2.**-38


def reference(name, config, fold):
    if name=='ridge': return ridge_reference(config['ridge'],int(fold.name[-1])*10)
    if name=='ar': return ar_reference(config['ridge'],int(fold.train_until),
                                       range(int(fold.score_from),int(fold.score_until)+1))
    return probability_reference(config['alpha'],censored=name=='censored')


@pytest.mark.parametrize('name',['ridge','bernoulli','censored','ar'])
def test_every_coordinate_and_role_matches_independent_reference(name):
    profile=prediction_profile(name)
    key,values=next(iter(profile.choices.items()))
    for fold in profile.declaration.tuning_folds+profile.declaration.final_folds:
        for value in values:
            config={key:value}; actual=profile.evaluate(config,fold); expected=reference(name,config,fold)
            assert actual['loss']==pytest.approx(expected['loss'],rel=TOL,abs=TOL)
            if name=='ridge':
                assert actual['model']['coefficient']/actual['model']['scale']==pytest.approx(expected['slope'],rel=TOL)
                assert actual['model']['center']==int(fold.name[-1])*10
                assert actual['model']['scale']==pytest.approx(math.sqrt(2.5),rel=TOL)
            elif name=='ar': assert actual['model']['coefficient']==expected['slope']
            else: assert actual['model']['probability']==expected['p']
            assert actual['work']==len(fold.train_ids)+len(fold.score_ids)
            score=[profile.records[i] for i in fold.score_ids]
            assert predict(actual['model'],score)==actual['predictions']


def test_ridge_preprocessing_never_fits_score_rows():
    profile=prediction_profile('ridge'); fold=profile.declaration.tuning_folds[0]
    train,score=validate_rows(profile.records,fold)
    before=profile.evaluator({'ridge':2},train,score)
    altered=deepcopy(score); altered[0]['x']=1e6; altered[0]['y']=-1e6
    after=profile.evaluator({'ridge':2},train,altered)
    assert before['model']==after['model']
    assert before['metrics']['preprocessing_train_ids']==list(fold.train_ids)
    assert after['loss']>before['loss']


def test_reused_entities_and_final_exposure_are_rejected():
    profile=prediction_profile('ridge'); d=profile.declaration; fold=d.tuning_folds[0]
    with pytest.raises(ValueError,match='disjoint declared entities'):
        replace(fold,score_groups=fold.train_groups)
    leaked=replace(d.final_folds[0],score_ids=fold.score_ids,score_groups=fold.score_groups)
    with pytest.raises(ValueError,match='exposed'):
        replace(d,final_folds=(leaked,))
    changed=deepcopy(profile.records); changed[fold.score_ids[0]]['group']='wrong_entity'
    with pytest.raises(ValueError,match='entity'):
        replace(profile,records=changed)


@pytest.mark.parametrize('case',['future_feature','train_time','score_time'])
def test_temporal_profile_rejects_information_leakage(case):
    profile=prediction_profile('ar'); rows=deepcopy(profile.records)
    if case=='future_feature': rows['t5']['feature_time']=5
    elif case=='train_time': rows['t1']['time']=10
    else: rows['t6']['time']=20
    with pytest.raises(ValueError,match='time'):
        replace(profile,records=rows)


@pytest.mark.parametrize('value',[0,-1,1.5,True])
def test_invalid_survival_times_are_not_silently_coerced(value):
    with pytest.raises(ValueError,match='integer survival'):
        event_counts([{'time':value,'event':1,'censoring':'independent'}],True)


def test_censoring_contributes_survival_and_requires_assumption():
    profile=prediction_profile('censored'); fold=profile.declaration.tuning_folds[0]
    train,score=validate_rows(profile.records,fold)
    assert event_counts(train,True)==(2,5)
    actual=profile.evaluate({'alpha':0},fold)
    p=2/7
    wrong_drop_censored=-(2*math.log(p)+math.log1p(-p))/2
    assert abs(actual['loss']-wrong_drop_censored)>0.1
    score[0]['censoring']='unknown'
    with pytest.raises(ValueError,match='assumption'):
        profile.evaluator({'alpha':0},train,score)


def test_mutated_data_and_undeclared_config_cannot_keep_original_identity():
    profile=prediction_profile('ridge'); fold=profile.declaration.tuning_folds[0]
    with pytest.raises(ValueError,match='domain'): profile.evaluate({'ridge':True},fold)
    with pytest.raises(ValueError,match='domain'): profile.evaluate({'ridge':2,'extra':0},fold)
    profile.records[fold.score_ids[0]]['y']=99
    with pytest.raises(ValueError,match='data changed'): profile.evaluate({'ridge':2},fold)
