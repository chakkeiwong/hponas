"""Signed/censored valuation and exact two-asset decisions from fitted inputs."""
import math
from statistics import fmean

from hponas import EvaluationFold, EvaluationObjective, StudyDeclaration
from workloads.bank_workflow import BankProfile,identity

COVARIANCE=((.25,.05),(.05,.1))


def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite decision input required')
    return float(value)


def discounted_value(cashflows, rate, survival=1.):
    rate=finite(rate);survival=finite(survival)
    if rate<=-1 or not 0<=survival<=1 or not cashflows:raise ValueError('Invalid discount/survival contract')
    if any(type(t) is not int or t<0 for t,_ in cashflows) or len({t for t,_ in cashflows})!=len(cashflows):
        raise ValueError('Unique nonnegative integer cashflow times required')
    return math.fsum(finite(c)*survival**t/(1+rate)**t for t,c in cashflows)


def survival_counts(rows):
    events=periods=0
    for r in rows:
        if (type(r['time']) is not int or r['time']<1 or type(r['event']) is not int
                or r['event'] not in (0,1) or type(r['identified']) is not bool):
            raise ValueError('Invalid censored observation or identification declaration')
        events+=r['event'];periods+=r['time']-r['event']
    return events,periods


def valuation_loss(config,train,score):
    events,periods=survival_counts(train);e,s=survival_counts(score);alpha=config['alpha']
    p=(events+alpha)/(events+periods+2*alpha)
    if not 0<p<1:raise ValueError('Boundary working hazard')
    identified=all(r['identified'] for r in train+score)
    cashflows=[[0,-100.],[1,60.],[2,60.]]
    model={'kind':'censored_cashflow_v1','hazard':p,'alpha':alpha,
           'cashflows':cashflows,'discount_rate':.1,'currency_unit':'synthetic_currency',
           'identified':identified,'working_likelihood':'geometric_independent_censoring'}
    value=discounted_value(cashflows,.1,1-p)
    assessment={'status':'identified_finite_model' if identified else 'unidentified',
        'npv':value if identified else None,'bounds':None if identified else [-100.,discounted_value(cashflows,.1)],
        'unit':'synthetic_currency','assumption':'independent censoring required for hazard and NPV identification'}
    return dict(loss=-(e*math.log(p)+s*math.log1p(-p))/len(score),model=model,
        predictions=[p]*len(score),work=len(train)+len(score),assessment=assessment,
        metrics={'loss_unit':'working_likelihood_nats_per_row','sign_convention':'initial outflow negative',
                 'score_events':e,'score_survival_periods':s})


def wallet_loss(config,train,score):
    if any(type(r['observed']) is not int or r['observed'] not in (1,2) for r in train+score):
        raise ValueError('Wallet observations must be min(W,2), W in {1,2,3}')
    alpha=config['alpha'];p=(sum(r['observed']==1 for r in train)+alpha)/(len(train)+2*alpha)
    if not 0<p<1:raise ValueError('Boundary observed-category probability')
    probabilities=[p if r['observed']==1 else 1-p for r in score]
    return dict(loss=-fmean(math.log(v) for v in probabilities),
        model={'kind':'censored_wallet_v1','mass_at_one':p,'tail_probability':1-p,
               'tail_support':[2,3],'alpha':alpha},predictions=probabilities,work=len(train)+len(score),
        metrics={'loss_unit':'observed_category_nats_per_row'},
        assessment={'status':'partially_identified','latent_mean':None,'bounds':[2-p,3-2*p],
                    'unit':'synthetic_wallet_units','reason':'Censoring leaves the tail allocation unidentified.'})


def portfolio_utility(weight, means, covariance=COVARIANCE, risk_aversion=1.):
    w=finite(weight);m1,m2=map(finite,means);k=finite(risk_aversion)
    if not 0<=w<=1 or k<0:raise ValueError('Long-only weight and nonnegative risk aversion required')
    variance=w*w*covariance[0][0]+2*w*(1-w)*covariance[0][1]+(1-w)**2*covariance[1][1]
    return w*m1+(1-w)*m2-k*variance/2


def exact_allocation(means, covariance=COVARIANCE, risk_aversion=1.):
    m1,m2=map(finite,means);k=finite(risk_aversion)
    if k<0:raise ValueError('Nonnegative risk aversion required')
    if len(covariance)!=2 or any(len(row)!=2 for row in covariance):raise ValueError('Two-asset covariance required')
    a,b,c,d=(finite(v) for row in covariance for v in row)
    if b!=c or a<=0 or d<=0 or a*d-b*b<=0:raise ValueError('Positive definite symmetric covariance required')
    if k==0:
        if m1==m2:return {'weight':None,'optimal_weights':[0.,1.],'kind':'LP_tie_interval'}
        w=1. if m1>m2 else 0.
    else:w=min(1.,max(0.,((m1-m2)-k*(b-d))/(k*(a+d-2*b))))
    return {'weight':w,'optimal_weights':[w,w],'kind':'exact_QP' if k else 'exact_LP',
            'utility':portfolio_utility(w,(m1,m2),covariance,k)}


def robust_allocation(intervals):
    if len(intervals)!=2 or any(len(row)!=2 for row in intervals):raise ValueError('Two mean intervals required')
    bounds=[tuple(map(finite,row)) for row in intervals]
    if any(a>b for a,b in bounds):raise ValueError('Mean interval bounds reversed')
    lower=[a for a,_ in bounds];robust=exact_allocation(lower)
    first=exact_allocation((bounds[0][0],bounds[1][1]))['weight']
    last=exact_allocation((bounds[0][1],bounds[1][0]))['weight']
    return {'robust_weight':robust['weight'],'worst_case_utility':robust['utility'],
            'possible_optimal_weights':[first,last],'mean_intervals':[list(row) for row in bounds]}


def allocation_loss(config,train,score):
    train_means=[fmean(finite(r['returns'][i]) for r in train) for i in (0,1)]
    score_means=[fmean(finite(r['returns'][i]) for r in score) for i in (0,1)]
    fitted=[(1-config['shrinkage'])*v for v in train_means]
    decision=exact_allocation(fitted);w=decision['weight']
    intervals=score[0].get('mean_intervals')
    if any(r.get('mean_intervals')!=intervals for r in train+score):raise ValueError('Uncertainty contract differs between rows')
    model={'kind':'shrunken_mean_allocation_v1','shrinkage':config['shrinkage'],
           'training_means':train_means,'fitted_means':fitted,'covariance':[list(row) for row in COVARIANCE],
           'risk_aversion':1.,'decision':decision,'mean_intervals':intervals}
    if intervals is None:
        utility=portfolio_utility(w,score_means);reference=exact_allocation(score_means)
        assessment={'status':'identified_finite_decision','weight':w,'utility':utility,
                    'reference_weight':reference['weight'],'decision_regret':reference['utility']-utility,
                    'unit':'synthetic_return_utility'}
    else:
        robust=robust_allocation(intervals);lower=[v[0] for v in intervals]
        utility=portfolio_utility(w,lower)
        assessment={'status':'bounded_robust_decision','point_identified_optimum':None,'weight':w,
                    'candidate_worst_case_utility':utility,'decision_regret':robust['worst_case_utility']-utility,
                    'unit':'synthetic_return_utility',**robust}
    return dict(loss=-utility,model=model,predictions=[w]*len(score),work=len(train)+len(score),
                metrics={'loss_unit':'negative_synthetic_return_utility'},assessment=assessment)


def decision_profile(name):
    if name not in ('valuation','valuation_unidentified','wallet','allocation','allocation_uncertain'):
        raise ValueError('Unknown decision profile')
    records={};folds=[]
    for role in ('tune','final'):
        parts={}
        for part in ('train','score'):
            ids=[]
            for i in range(4):
                ident=f'{role}_{part}_{i}';ids.append(ident)
                if name.startswith('valuation'):
                    t,event=((1,1),(2,1),(2,0),(2,0))[i]
                    row={'time':t,'event':event,'identified':name=='valuation'}
                elif name=='wallet':row={'observed':(1,1,2,2)[i]}
                else:
                    means=(.15,.05) if part=='train' else (.1,.05)
                    offsets=((.02,0.),(-.02,0.),(0.,.02),(0.,-.02))[i]
                    row={'returns':[a+b for a,b in zip(means,offsets)],
                         'mean_intervals':[[.08,.12],[.03,.07]] if name=='allocation_uncertain' else None}
                records[ident]={'id':ident,**row}
            parts[part]=tuple(ids)
        folds.append(EvaluationFold(role,parts['train'],parts['score']))
    allocation=name.startswith('allocation')
    unit='negative_synthetic_return_utility' if allocation else 'observed_likelihood_nats_per_row'
    declaration=StudyDeclaration(objective_id=name+'-score:v1',model_id=name+'-fit:v1',
        data_id=name+'-generator:v1:'+identity(records),protocol_id=name+'-disjoint-refit:v1',
        objectives=(EvaluationObjective('loss','min',unit),),tuning_folds=(folds[0],),final_folds=(folds[1],),
        tuning_seeds=(0,),final_seeds=(1000,))
    return BankProfile(name,{'shrinkage':[0.,.25,.5]} if allocation else {'alpha':[0,1,3]},
        declaration,records,allocation_loss if allocation else wallet_loss if name=='wallet' else valuation_loss)


def reload_decision(model):
    kind=model.get('kind')
    if kind=='censored_cashflow_v1':
        return {'npv':discounted_value(model['cashflows'],model['discount_rate'],1-model['hazard']) if model['identified'] else None}
    if kind=='censored_wallet_v1':
        p=model['mass_at_one'];return {'latent_mean':None,'bounds':[2-p,3-2*p]}
    if kind=='shrunken_mean_allocation_v1':
        return exact_allocation(model['fitted_means'],model['covariance'],model['risk_aversion'])
    raise ValueError('Unknown decision model schema')
