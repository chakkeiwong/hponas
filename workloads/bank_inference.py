"""Finite predictive likelihood and separately verified inference handoffs."""
from copy import deepcopy
from itertools import product
import math

from hponas import EvaluationFold, EvaluationObjective, StudyDeclaration
from workloads.bank_workflow import BankProfile, identity, write_artifact

TARGET='standard_normal:v1'
DEVELOPMENT_STATES=((1.,0.),(0.,1.),(1.,1.))
VERIFICATION_STATES=((-1.,0.),(0.,-1.),(1.,-1.),(.5,.25))


def _finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Finite numeric inference input required')
    return float(value)


def kalman(values, observation_variance):
    r=_finite(observation_variance)
    if r<=0 or not values: raise ValueError('Positive variance and nonempty sequence required')
    mean=0.;variance=1.;trace=[]
    for index,value in enumerate(values,1):
        y=_finite(value)
        prior_mean=.5*mean;prior_variance=.25*variance+.25
        innovation=y-prior_mean;innovation_variance=prior_variance+r
        gain=prior_variance/innovation_variance
        mean=prior_mean+gain*innovation;variance=prior_variance*r/innovation_variance
        trace.append({'time':index,'predictive_mean':prior_mean,
            'innovation':innovation,'innovation_variance':innovation_variance,
            'filtered_mean':mean,'filtered_variance':variance,
            'negative_log_likelihood':.5*(math.log(2*math.pi*innovation_variance)+innovation**2/innovation_variance)})
    return {'negative_log_likelihood':math.fsum(t['negative_log_likelihood'] for t in trace),
            'trace':trace}


def filter_sequences(rows, observation_variance):
    groups={}
    for row in rows: groups.setdefault(row['group'],[]).append(row)
    result={}
    for group,sequence in groups.items():
        ordered=sorted(sequence,key=lambda r:r['time'])
        if any(type(r['time']) is not int for r in ordered) or [r['time'] for r in ordered]!=list(range(1,len(ordered)+1)):
            raise ValueError('Sequence times must be contiguous and unique from one')
        # Each sequence is an independent replicate: never carry another
        # sequence's posterior into its prior.
        result[group]=kalman([r['y'] for r in ordered],observation_variance)
    return result


def predict_filter(model, rows):
    if (model.get('kind')!='linear_gaussian_filter_v1' or model.get('transition')!=.5
            or model.get('process_variance')!=.25 or model.get('initial_mean')!=0.
            or model.get('initial_variance')!=1.):
        raise ValueError('Filter target or model schema differs')
    return filter_sequences(rows,model['observation_variance'])


def inference_loss(config, train, score):
    r=config['observation_variance']
    fitted=filter_sequences(train,r)
    model={'kind':'linear_gaussian_filter_v1','transition':.5,'process_variance':.25,
           'initial_mean':0.,'initial_variance':1.,'observation_variance':r,'training_fits':fitted}
    predictions=predict_filter(model,score)
    loss=math.fsum(v['negative_log_likelihood'] for v in predictions.values())/len(score)
    return dict(loss=loss,model=model,predictions=predictions,work=len(train)+len(score),
        metrics={'loss_unit':'predictive_nats_per_observation','sequence_prior':'independent_reset'},
        assessment={'status':'finite_predictive_likelihood','posterior_convergence':'not_assessed',
                    'scope':'R is a statistical model choice; native numerical handoff holds its target fixed.'})


def inference_profile():
    records={};groups=[]
    for g,values in [('train',(1.,-.5,.75)),('tune',(.5,0.,-.25)),('final',(.75,-.25,.5))]:
        ids=[]
        for t,y in enumerate(values,1):
            ident=f'{g}_{t}';ids.append(ident)
            records[ident]={'id':ident,'group':g,'time':t,'y':y}
        groups.append(tuple(ids))
    tuning=(EvaluationFold('tune',groups[0],groups[1],mode='grouped',train_groups=('train',),score_groups=('tune',)),)
    final=(EvaluationFold('final',groups[0]+groups[1],groups[2],mode='grouped',
                           train_groups=('train','tune'),score_groups=('final',)),)
    declaration=StudyDeclaration(objective_id='gaussian-predictive-likelihood:v1',model_id='scalar-kalman:v1',
        data_id='independent-gaussian-sequences:v1:'+identity(records),protocol_id='independent-sequence-refit:v1',
        objectives=(EvaluationObjective('loss','min','predictive_nats_per_observation'),),
        tuning_folds=tuning,final_folds=final,tuning_seeds=(0,),final_seeds=(1000,))
    return BankProfile('inference',{'observation_variance':[.25,1.,4.]},declaration,records,inference_loss)


def leapfrog(state, step_size, steps):
    q,p=map(_finite,state);initial=.5*(q*q+p*p)
    h=_finite(step_size)
    if not 0<h<2 or type(steps) is not int or not 1<=steps<=3:
        raise ValueError('Stable finite leapfrog coordinates required')
    for _ in range(steps):
        p-=.5*h*q;q+=h*p;p-=.5*h*q
    return {'position':q,'momentum':p,'target_id':TARGET,
            'log_acceptance':min(0.,initial-.5*(q*q+p*p))}


def _matrix(h, length):
    one=((1-h*h/2,h),(-h+h**3/4,1-h*h/2));value=((1.,0.),(0.,1.))
    for _ in range(length):
        value=tuple(tuple(math.fsum(value[i][k]*one[k][j] for k in range(2)) for j in range(2)) for i in range(2))
    return value


def _close(a,b):
    return abs(_finite(a)-_finite(b))<=2.**-40*max(1.,abs(a),abs(b))


def _verify(candidate, states, proposal):
    h,length=candidate['step_size'],candidate['leapfrog_steps'];matrix=_matrix(h,length)
    if not _close(matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0],1.):
        raise ValueError('Analytic volume check failed')
    records=[]
    for state in states:
        expected=[math.fsum(matrix[i][j]*state[j] for j in range(2)) for i in range(2)]
        actual=proposal(state,h,length)
        if actual.get('target_id')!=TARGET: raise ValueError('Proposal target identity differs')
        if not (_close(actual['position'],expected[0]) and _close(actual['momentum'],expected[1])):
            raise ValueError('Candidate trajectory differs from target-preserving matrix')
        log_accept=min(0.,.5*(math.fsum(x*x for x in state)-math.fsum(x*x for x in expected)))
        if not _close(actual['log_acceptance'],log_accept):
            raise ValueError('Missing or incorrect Metropolis correction')
        backward=proposal((actual['position'],-actual['momentum']),h,length)
        if not (_close(backward['position'],state[0]) and _close(backward['momentum'],-state[1])):
            raise ValueError('Momentum-flip reversibility failed')
        records.append({'state':list(state),'result':actual,'expected_log_acceptance':log_accept})
    return {'status':'verified','records':records,'determinant':matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0]}


def native_handoff(candidates=None, *, proposal=leapfrog, posterior_assessment=None):
    """Keep every freshly verified pair; posterior diagnostics do not rank it.

    The default integrator has an analytic linear, symplectic/reversible proof.
    An injected callback receives finite diagnostics, not a general proof of
    target invariance for arbitrary implementation outside these checks.
    """
    if candidates is None:
        candidates=[{'step_size':h,'leapfrog_steps':n,'target_id':TARGET} for h,n in product((.25,.5,1.),(1,2,3))]
    if not isinstance(candidates,(list,tuple)) or len(candidates)>9:
        raise ValueError('At most nine explicit finite candidates required')
    if len({identity(c) for c in candidates})!=len(candidates): raise ValueError('Duplicate candidate identity')
    rows=[];verified=[]
    for candidate in candidates:
        row={'candidate':deepcopy(candidate),'development':{'status':'not_run'},'fresh':{'status':'not_run'}}
        phase='candidate'
        try:
            if set(candidate)!={'step_size','leapfrog_steps','target_id'} or candidate['target_id']!=TARGET:
                raise ValueError('Candidate target identity or schema differs')
            if (type(candidate['step_size']) not in (int,float) or candidate['step_size'] not in (.25,.5,1.)
                    or type(candidate['leapfrog_steps']) is not int or candidate['leapfrog_steps'] not in (1,2,3)):
                raise ValueError('Candidate outside the declared finite domain')
            phase='development';row['development']=_verify(candidate,DEVELOPMENT_STATES,proposal)
            phase='fresh';row['fresh']=_verify(candidate,VERIFICATION_STATES,proposal)
            row['status']='verified';verified.append(deepcopy(candidate))
        except Exception as exc:
            if phase!='candidate': row[phase]={'status':'failed','reason':str(exc)}
            row.update(status='rejected',reason=str(exc),error_type=type(exc).__name__,failure_phase=phase)
        rows.append(row)
    return {'schema':'native_handoff_v1','target_id':TARGET,'candidates':rows,'verified_pairs':verified,
            'selection_policy':'retain_all_freshly_verified_pairs','posterior_assessment':deepcopy(posterior_assessment),
            'posterior_assessment_used_for_selection':False,'scientific_acceptance':False,
            'scope':'Finite Gaussian numerical conformance; no posterior convergence claim.'}


def affine_transport(x, scale, shift):
    x=_finite(x);a=_finite(scale);b=_finite(shift)
    if a not in (.5,1.,2.) or b not in (-1.,0.,1.): raise ValueError('Transport outside the finite domain')
    z=a*x+b;inverse=(z-b)/a
    return {'target_id':TARGET,'scale':a,'shift':b,'source':x,'position':z,'inverse':inverse,
            'log_abs_jacobian':math.log(a),'log_density':-.5*(inverse**2+math.log(2*math.pi))-math.log(a)}


def verify_transport(record):
    if record.get('target_id')!=TARGET: raise ValueError('Transport target identity differs')
    expected=affine_transport(record['source'],record['scale'],record['shift'])
    if set(record)!=set(expected) or any(not _close(record[k],expected[k]) for k in expected if k!='target_id'):
        raise ValueError('Transport inverse, density or Jacobian differs')
    return True


def save_handoff(path, result):
    if result.get('schema')!='native_handoff_v1': raise ValueError('Unknown handoff schema')
    return write_artifact(path,{'kind':'native_inference_handoff','handoff':result})
