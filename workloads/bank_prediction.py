"""Finite prediction profiles with independent algebraic references elsewhere."""
import math
from statistics import fmean

from hponas import EvaluationFold, EvaluationObjective, StudyDeclaration
from workloads.bank_workflow import BankProfile, identity


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Finite numeric data required')
    return value


def fit_ridge(train, ridge):
    x=[_number(r['x']) for r in train]; y=[_number(r['y']) for r in train]
    center=fmean(x); target_center=fmean(y)
    scale=math.sqrt(fmean((v-center)**2 for v in x))
    if not scale > 0: raise ValueError('Training predictor has zero scale')
    z=[(v-center)/scale for v in x]
    slope=math.fsum(a*(b-target_center) for a,b in zip(z,y))/(math.fsum(a*a for a in z)+ridge)
    return {'kind':'standardized_ridge_v1','center':center,'scale':scale,
            'target_center':target_center,'coefficient':slope,'ridge':ridge}


def predict(model, rows):
    kind=model.get('kind')
    if kind=='standardized_ridge_v1':
        if not _number(model['scale']) > 0: raise ValueError('Invalid fitted scale')
        return [model['target_center']+model['coefficient']*(_number(r['x'])-model['center'])/model['scale'] for r in rows]
    if kind=='ar_coefficient_v1':
        return [model['coefficient']*_number(r['x']) for r in rows]
    if kind in ('bernoulli_probability_v1','geometric_hazard_v1'):
        p=_number(model['probability'])
        if not 0 < p < 1: raise ValueError('Probability outside (0,1)')
        return [p for _ in rows]
    raise ValueError('Unsupported prediction model schema')


def ridge_loss(config, train, score):
    model=fit_ridge(train,config['ridge'])
    predictions=predict(model,score)
    loss=fmean((a-_number(r['y']))**2 for a,r in zip(predictions,score))
    return dict(loss=loss,model=model,predictions=predictions,work=len(train)+len(score),
                metrics={'loss_unit':'squared_target_units','preprocessing_train_ids':[r['id'] for r in train]})


def event_counts(rows, censored):
    events=failures=0
    for row in rows:
        event=row['event'] if censored else row['y']
        if type(event) is not int or event not in (0,1): raise ValueError('Binary outcome required')
        if censored:
            if row.get('censoring') != 'independent': raise ValueError('Independent censoring assumption required')
            t=row['time']
            if type(t) is not int or t<1: raise ValueError('Positive integer survival time required')
            failures+=t-event
        else: failures+=1-event
        events+=event
    return events,failures


def probability_loss(config, train, score, *, censored=False):
    events,failures=event_counts(train,censored)
    a=config['alpha']; p=(events+a)/(events+failures+2*a)
    if not 0<p<1: raise ValueError('Training likelihood has boundary probability')
    model={'kind':'geometric_hazard_v1' if censored else 'bernoulli_probability_v1',
           'probability':p,'alpha':a,'training_events':events,'training_survival_periods':failures}
    score_events,score_failures=event_counts(score,censored)
    loss=-(score_events*math.log(p)+score_failures*math.log1p(-p))/len(score)
    return dict(loss=loss,model=model,predictions=predict(model,score),work=len(train)+len(score),
                metrics={'loss_unit':'nats_per_row','score_events':score_events,
                         'score_survival_periods':score_failures})


def censored_loss(config, train, score):
    return probability_loss(config,train,score,censored=True)


def ar_loss(config, train, score):
    x=[_number(r['x']) for r in train]; y=[_number(r['y']) for r in train]
    denominator=math.fsum(v*v for v in x)+config['ridge']
    if denominator<=0: raise ValueError('AR fit has zero denominator')
    model={'kind':'ar_coefficient_v1','coefficient':math.fsum(a*b for a,b in zip(x,y))/denominator,
           'ridge':config['ridge']}
    predictions=predict(model,score)
    return dict(loss=fmean((a-_number(r['y']))**2 for a,r in zip(predictions,score)),
        model=model,predictions=predictions,work=len(train)+len(score),
        metrics={'loss_unit':'squared_target_units','forecast':'one_step_observed_lag'})


def _declaration(name, records, tuning, final, model_id, unit):
    return StudyDeclaration(objective_id=name+':v1',model_id=model_id,
        data_id=name+'-generator-v1:'+identity(records),protocol_id=name+'-disjoint-refit:v1',
        objectives=(EvaluationObjective('loss','min',unit),),tuning_folds=tuple(tuning),
        final_folds=tuple(final),tuning_seeds=(0,),final_seeds=(1000,))


def prediction_profile(name):
    if name=='ridge':
        records={}; folds=[]
        for index,c in enumerate((0,10,20)):
            prefix='group'+str(index); parts={}
            for role,offsets in [('train',(-2,-1,1,2)),('score',(-3,0,6))]:
                ids=[]
                for i,d in enumerate(offsets):
                    ident=f'{prefix}_{role}_{i}'; ids.append(ident)
                    records[ident]={'id':ident,'group':prefix+'_'+role,'x':c+d,
                                    'y':1+2*(c+d)+(d if role=='train' else 0)}
                parts[role]=tuple(ids)
            folds.append(EvaluationFold(prefix,parts['train'],parts['score'],mode='grouped',
                train_groups=(prefix+'_train',),score_groups=(prefix+'_score',)))
        declaration=_declaration(name,records,folds[:2],folds[2:],
                                 'standardized-ridge-intercept:v1','squared_target_units')
        return BankProfile(name,{'ridge':[0,1,2,4]},declaration,records,ridge_loss)
    if name in ('bernoulli','censored'):
        records={}; folds=[]
        for role in ('tune','final'):
            parts={}
            for part in ('train','score'):
                ids=[]
                for i,(t,event) in enumerate(((1,1),(2,1),(2,0),(2,0))):
                    ident=f'{role}_{part}_{i}'; ids.append(ident)
                    records[ident]=({'id':ident,'time':t,'event':event,'censoring':'independent'}
                                    if name=='censored' else {'id':ident,'y':int(i==0)})
                parts[part]=tuple(ids)
            folds.append(EvaluationFold(role,parts['train'],parts['score']))
        declaration=_declaration(name,records,folds[:1],folds[1:],name+'-beta-fit:v1','nats_per_row')
        return BankProfile(name,{'alpha':[0,1,3]},declaration,records,
                           censored_loss if name=='censored' else probability_loss)
    if name=='ar':
        records={f't{t}':{'id':f't{t}','time':t,'feature_time':t-1,'x':2.**(-(t-1)),'y':2.**(-t)}
                 for t in range(1,12)}
        folds=[]
        for name_,end,score in [('early',3,(5,6)),('late',5,(7,8)),('final',7,(10,11))]:
            folds.append(EvaluationFold(name_,tuple(f't{t}' for t in range(1,end+1)),
                tuple(f't{t}' for t in score),mode='temporal',train_until=end,
                score_from=score[0],score_until=score[-1],gap=1))
        declaration=_declaration(name,records,folds[:2],folds[2:],'ar-ridge-no-intercept:v1','squared_target_units')
        return BankProfile(name,{'ridge':[0,.25,1]},declaration,records,ar_loss)
    raise ValueError('Unknown prediction profile')
