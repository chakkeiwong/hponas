"""Finite neural ODE solver with separate task feasibility and a public front."""
import numpy as np

from hponas import EvaluationFold, EvaluationObjective, StudyDeclaration
from workloads.bank_neural import CHOICES, fit, evaluate, measure
from workloads.bank_workflow import BankProfile, identity

TOLERANCE=2.**-20
WORK_UNIT='hidden_affine_multiply_adds'
OBJECTIVES=[{'name':'residual_loss','direction':'min','lower':0.,'upper':16.},
            {'name':'parameters','direction':'min','lower':0.,'upper':32.}]
CONSTRAINTS={'value_residual':TOLERANCE,'derivative_residual':TOLERANCE,'boundary_residual':TOLERANCE,
             'condition_number':4096.,'coefficient_l1':64.,'feature_scale':16.}
CONTRACT={'objectives':OBJECTIVES,'constraints':CONSTRAINTS,'work_unit':WORK_UNIT}


def task_residuals(values, derivatives, nodes, boundary):
    values=np.asarray(values);derivatives=np.asarray(derivatives);nodes=np.asarray(nodes)
    if (values.shape!=nodes.shape or derivatives.shape!=nodes.shape or nodes.size==0
            or not np.all(np.isfinite(values)) or not np.all(np.isfinite(derivatives))
            or not np.isfinite(boundary) or np.any(np.abs(nodes)>1)):
        raise ValueError('Invalid solver evaluation values or domain')
    value=values-nodes*nodes;derivative=derivatives-2*nodes
    return {'value_residual':float(np.max(np.abs(value))),
            'derivative_residual':float(np.max(np.abs(derivative))),
            'boundary_residual':abs(float(boundary)),
            'loss':float(np.mean(value*value)+np.mean((derivative/2)**2)+boundary*boundary)}


def feasible(constraints):
    return set(constraints)==set(CONSTRAINTS) and all(
        np.isfinite(v) and 0<=v<=CONSTRAINTS[key] for key,v in constraints.items())


def solver_loss(config,train,score):
    if ([r['task'] for r in train].count('derivative')!=4 or [r['task'] for r in train].count('boundary')!=1):
        raise ValueError('Frozen solver requires four derivative rows and one boundary')
    model,diagnostics=fit(config,train)
    nodes=[r['x'] for r in score];probes=evaluate(model,nodes+[0.])
    values=probes['values'][:-1];derivatives=probes['derivatives'][:-1];boundary=probes['values'][-1]
    residual=task_residuals(values,derivatives,nodes,boundary)
    constraints={k:residual[k] for k in ('value_residual','derivative_residual','boundary_residual')}
    constraints.update(condition_number=diagnostics['condition_number'],coefficient_l1=diagnostics['coefficient_l1'],
                       feature_scale=max(diagnostics['training_feature_scale'],probes['feature_scale']))
    size=measure(model);work=diagnostics['training_hidden_affine_operations']+probes['hidden_affine_operations']
    return dict(loss=residual['loss'],model=model,predictions={'values':values,'derivatives':derivatives,'boundary':boundary},
        work=work,objectives={'residual_loss':residual['loss'],'parameters':size['parameters']},constraints=constraints,
        metrics={**size,**diagnostics,'probe_output_multiply_adds':probes['output_multiply_adds'],
            'meter_scope':'Actual hidden affine value and derivative multiply/adds; excludes activation and solve operations.'},
        assessment={'status':'feasible' if feasible(constraints) else 'infeasible',
                    'task_constraints':constraints,'tolerance':TOLERANCE,'domain':[-1,1],
                    'scope':'Finite known-solution collocation fixture; no global approximation certificate.'})


def solver_profile():
    records={};train=[]
    for i,x in enumerate((-1.,-.5,.5,1.)):
        ident=f'derivative_{i}';train.append(ident)
        records[ident]={'id':ident,'x':x,'target':2*x,'task':'derivative'}
    train.append('boundary');records['boundary']={'id':'boundary','x':0.,'target':0.,'task':'boundary'}
    folds=[]
    for name,nodes in [('tune',(-.75,-.25,.25,.75)),('final',(-.875,-.375,.375,.875))]:
        ids=[]
        for i,x in enumerate(nodes):
            ident=f'{name}_{i}';ids.append(ident);records[ident]={'id':ident,'x':x,'target':x*x,'task':'probe'}
        folds.append(EvaluationFold(name,tuple(train),tuple(ids),mode='known_answer'))
    declaration=StudyDeclaration(objective_id='ode-residual-and-size:v1',model_id='fixed-hidden-coordinate-network:v1',
        data_id='ode-known-nodes:v1:'+identity(records),protocol_id='disjoint-neural-probes:v1',
        objectives=(EvaluationObjective('residual_loss','min','normalized_squared_residual'),
                    EvaluationObjective('parameters','min','parameters')),
        tuning_folds=(folds[0],),final_folds=(folds[1],),tuning_seeds=(0,),final_seeds=(1000,))
    return BankProfile('solver',CHOICES,declaration,records,solver_loss,
                       vector_contract=CONTRACT,work_unit=WORK_UNIT,max_work_per_call=880)
