"""Cross-fitted finite nuisance tuning with explicit causal identification."""
from itertools import product
import math
from statistics import fmean

from hponas import EvaluationFold, EvaluationObjective, StudyDeclaration
from workloads.bank_workflow import BankProfile, identity


def validate_structural_rows(rows):
    if not rows or any(type(r.get('a')) is not int or r['a'] not in (0,1)
           or type(r.get('x')) is not int or r['x'] not in (-1,1)
           or type(r.get('y')) not in (int,float) or not math.isfinite(r['y'])
           or not -3<=r['y']<=5 or type(r.get('exogeneity')) is not bool for r in rows):
        raise ValueError('Invalid structural-model row or assumptions')


def fit_nuisance(config, train):
    validate_structural_rows(train)
    outcomes={};support={};propensity={}
    for arm in (0,1):
        subset=[r for r in train if r['a']==arm]
        if not subset: raise ValueError('Treatment arm absent from training')
        center=fmean(r['x'] for r in subset); target=fmean(r['y'] for r in subset)
        variance=math.fsum((r['x']-center)**2 for r in subset)
        denominator=variance+config['ridge']
        slope=(math.fsum((r['x']-center)*(r['y']-target) for r in subset)/denominator
               if denominator>0 else 0.)
        outcomes[str(arm)]={'intercept':target-slope*center,'slope':slope}
    for x in (-1,1):
        subset=[r for r in train if r['x']==x]
        if not subset: raise ValueError('Covariate stratum absent from training')
        counts=[sum(r['a']==a for r in subset) for a in (0,1)]
        support[str(x)]=counts
        propensity[str(x)]=(counts[1]+config['alpha'])/(len(subset)+2*config['alpha'])
    return {'kind':'crossfit_linear_nuisance_v1','outcomes':outcomes,'propensity':propensity,
            'raw_support':support,'exogeneity':all(r['exogeneity'] for r in train),
            'train_ids':[r['id'] for r in train],'config':dict(config)}


def predict_nuisance(model, score):
    if model.get('kind')!='crossfit_linear_nuisance_v1': raise ValueError('Unsupported nuisance model schema')
    rows=[]
    for row in score:
        x=row['x']
        if x not in (-1,1): raise ValueError('Unsupported covariate stratum')
        rows.append({'m0':model['outcomes']['0']['intercept']+model['outcomes']['0']['slope']*x,
                     'm1':model['outcomes']['1']['intercept']+model['outcomes']['1']['slope']*x,
                     'propensity':model['propensity'][str(x)]})
    return rows


def assess_effect(model, score, predictions):
    base={'estimand':'E[Y(1)-Y(0)]','unit':'target_units',
          'assumptions':['consistency','structural_exogeneity','raw_positivity'],
          'method':'cross_fitted_augmented_inverse_probability'}
    if not all(all(count>0 for count in counts) for counts in model['raw_support'].values()):
        return {**base,'status':'unsupported_overlap','effect':None,'bounds':[-8.,8.]}
    if not model['exogeneity'] or not all(r['exogeneity'] for r in score):
        return {**base,'status':'unidentified','effect':None,'bounds':[-8.,8.]}
    scores=[]
    for row,prediction in zip(score,predictions):
        a,y=row['a'],row['y'];e=prediction['propensity']
        if not 0<e<1: raise ValueError('Identified propensity must be interior')
        scores.append(prediction['m1']-prediction['m0']+a*(y-prediction['m1'])/e
                      -(1-a)*(y-prediction['m0'])/(1-e))
    return {**base,'status':'identified_finite_model','effect':fmean(scores),'bounds':None,
            'scores':scores,'scope':'Known finite structural fixture; not observational identification evidence.'}


def causal_loss(config, train, score):
    validate_structural_rows(train);validate_structural_rows(score)
    if set(r['id'] for r in train).intersection(r['id'] for r in score):
        raise ValueError('Nuisance fitting and scoring rows overlap')
    if {r['group'] for r in train}.intersection(r['group'] for r in score):
        raise ValueError('Cross-fitting requires separate entity groups')
    model=fit_nuisance(config,train); predictions=predict_nuisance(model,score)
    mse=fmean((r['y']-p['m'+str(r['a'])])**2 for r,p in zip(score,predictions))
    brier=fmean((r['a']-p['propensity'])**2 for r,p in zip(score,predictions))
    return dict(loss=mse+brier,model=model,predictions=predictions,work=len(train)+len(score),
        metrics={'outcome_mse':mse,'treatment_brier':brier,'loss_unit':'dimensionless_prediction_loss'},
        assessment=assess_effect(model,score,predictions))


def causal_profile(*, overlap=True, identified=True):
    if type(overlap) is not bool or type(identified) is not bool:
        raise ValueError('Explicit boolean assumptions required')
    name='causal' if overlap and identified else 'causal_overlap' if not overlap else 'causal_unidentified'
    records={};groups=[]
    for group in range(3):
        ids=[]
        for i,(x,u,error) in enumerate(product((-1,1),(.125,.375,.625,.875),(-1,1))):
            propensity=.25 if x==-1 else .75
            a=int(u<propensity) if overlap else int(x==1)
            ident=f'g{group}_{i}';ids.append(ident)
            records[ident]={'id':ident,'group':f'g{group}','x':x,'a':a,
                            'y':1+x+2*a+error,'exogeneity':identified}
        groups.append(tuple(ids))
    tuning=tuple(EvaluationFold(f'crossfit_{i}',groups[i],groups[1-i],mode='grouped',
                    train_groups=(f'g{i}',),score_groups=(f'g{1-i}',)) for i in (0,1))
    final=(EvaluationFold('final_refit',groups[0]+groups[1],groups[2],mode='grouped',
                          train_groups=('g0','g1'),score_groups=('g2',)),)
    declaration=StudyDeclaration(objective_id='structural-nuisance-loss:v1',
        model_id='crossfit-ridge-propensity:v1',data_id=name+'-generator:v1:'+identity(records),
        protocol_id='group-crossfit-disjoint-final:v1',
        objectives=(EvaluationObjective('loss','min','dimensionless_prediction_loss'),),
        tuning_folds=tuning,final_folds=final,tuning_seeds=(0,),final_seeds=(1000,))
    return BankProfile(name,{'ridge':[0,.25,1],'alpha':[0,1]},declaration,records,causal_loss)
