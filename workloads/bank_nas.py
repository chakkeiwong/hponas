"""Coordinate NAS for prediction using the same constructed solver networks."""
import numpy as np

from hponas import EvaluationFold,EvaluationObjective,StudyDeclaration
from workloads.bank_neural import CHOICES,fit,evaluate,measure
from workloads.bank_workflow import BankProfile,identity

CONTRACT={'objectives':[{'name':'prediction_mse','direction':'min','lower':0.,'upper':4.},
                        {'name':'parameters','direction':'min','lower':0.,'upper':32.}],
          'constraints':{'condition_number':4096.,'coefficient_l1':64.,'feature_scale':16.},
          'work_unit':'hidden_affine_multiply_adds'}


def neural_prediction_loss(config,train,score):
    model,diagnostics=fit(config,train,task='prediction')
    nodes=[r['x'] for r in score];probes=evaluate(model,nodes)
    loss=float(np.mean((np.array(probes['values'])-np.array([r['target'] for r in score]))**2))
    size=measure(model);constraints={k:diagnostics[k] for k in ('condition_number','coefficient_l1')}
    constraints['feature_scale']=max(diagnostics['training_feature_scale'],probes['feature_scale'])
    feasible=all(0<=v<=CONTRACT['constraints'][key] for key,v in constraints.items())
    return dict(loss=loss,model=model,predictions={'values':probes['values'],'derivatives':probes['derivatives']},
        work=diagnostics['training_hidden_affine_operations']+probes['hidden_affine_operations'],
        objectives={'prediction_mse':loss,'parameters':size['parameters']},constraints=constraints,
        metrics={**size,**diagnostics,'probe_output_multiply_adds':probes['output_multiply_adds'],
                 'meter_scope':'Hidden affine value/derivative operations; activation and solve excluded.'},
        assessment={'status':'numerically_admissible' if feasible else 'numerically_inadmissible',
                    'prediction_mse':loss,'constraints':constraints,
                    'scope':'Finite deterministic prediction; no empirical application performance claim.'})


def nas_prediction_profile():
    records={};train=[]
    for i,x in enumerate((-1.,-.5,0.,.5,1.)):
        ident=f'train_{i}';train.append(ident);records[ident]={'id':ident,'x':x,'target':x*x,'task':'prediction'}
    folds=[]
    for name,nodes in [('tune',(-.75,-.25,.25,.75)),('final',(-.875,-.375,.375,.875))]:
        ids=[]
        for i,x in enumerate(nodes):
            ident=f'{name}_{i}';ids.append(ident);records[ident]={'id':ident,'x':x,'target':x*x,'task':'prediction'}
        folds.append(EvaluationFold(name,tuple(train),tuple(ids),mode='known_answer'))
    declaration=StudyDeclaration(objective_id='neural-prediction-and-size:v1',model_id='fixed-hidden-coordinate-network:v1',
        data_id='square-known-nodes:v1:'+identity(records),protocol_id='disjoint-neural-prediction:v1',
        objectives=(EvaluationObjective('prediction_mse','min','squared_target_units'),
                    EvaluationObjective('parameters','min','parameters')),
        tuning_folds=(folds[0],),final_folds=(folds[1],),tuning_seeds=(0,),final_seeds=(1000,))
    return BankProfile('nas_prediction',CHOICES,declaration,records,neural_prediction_loss,
                       vector_contract=CONTRACT,work_unit=CONTRACT['work_unit'],max_work_per_call=792)
