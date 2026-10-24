"""Reconstruct retained results without importing the fitter, torch or searcher.

Independent scalar logistic likelihood/KKT and NumPy neural chain rule are the
numerical oracles. Finite enumeration gives a reference for this exact training
procedure and seeds, not a globally optimal trained network.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def check_close(actual, expected, atol=2e-10):
    if not np.allclose(actual, expected, rtol=2e-9, atol=atol):
        raise AssertionError('Independent numerical reconstruction differs')


def verify_regret(reported, selected, complete_reference):
    expected = selected - min(complete_reference)
    check_close(reported, expected)
    if reported < -2e-10:
        raise AssertionError('Negative finite reference regret')


def artifact(path):
    document = read(path)
    encoded = json.dumps(document['payload'], sort_keys=True, separators=(',', ':'), allow_nan=False)
    if hashlib.sha256(encoded.encode()).hexdigest() != document['sha256']:
        raise AssertionError('Model bytes altered')
    return document['payload']


def logistic_reference(weights, train, score, alpha, l1_ratio):
    ratio = l1_ratio
    grad = [0., 0., 0.]
    for x1, x2, label in train:
        row = (1., x1, x2)
        logit = sum(w*x for w,x in zip(weights, row))
        probability = 1/(1+math.exp(-logit))
        for j in range(3):
            grad[j] += (probability-label)*row[j]/len(train)
    residuals = [abs(grad[0])]
    for j in (1,2):
        g = grad[j] + alpha*(1-ratio)*weights[j]
        residuals.append(abs(g + alpha*ratio*math.copysign(1,weights[j])) if weights[j] else max(abs(g)-alpha*ratio,0))
    terms = []
    for x1,x2,label in score:
        z = weights[0]+weights[1]*x1+weights[2]*x2
        terms.append(max(z,0)+math.log1p(math.exp(-abs(z)))-label*z)
    return math.fsum(terms)/len(terms), max(residuals)


def network_reference(layers, states):
    states = np.asarray(states)
    value = states.copy()
    jac = np.broadcast_to(np.eye(2), (len(states),2,2)).copy()
    for i, layer in enumerate(layers):
        weights, bias = np.asarray(layer['weight']), np.asarray(layer['bias'])
        value = value @ weights.T + bias
        jac = np.einsum('oi,nij->noj', weights, jac)
        if i != len(layers)-1:
            value = np.tanh(value)
            jac = (1-value*value)[:,:,None] * jac
    y = states[:,0]*value[:,0]
    derivative = states[:,0,None]*jac[:,0,:]
    derivative[:,0] += value[:,0]
    return y, derivative


def verify_payload(payload, records, design):
    train = [records[k] for k in payload['train_ids']]
    score = [records[k] for k in payload['score_ids']]
    assert not set(payload['train_ids']) & set(payload['score_ids'])
    assert all(k.startswith('final_') for k in payload['score_ids']) == (payload['role']=='final')
    if payload['name'] == 'response':
        loss,kkt=logistic_reference(payload['model']['weights'],train,score,**payload['physical'])
        assert kkt <= design['response']['kkt_tolerance']*1.01
        check_close(kkt,payload['model']['kkt'])
        work=2*len(train)*payload['model']['iterations']+len(score)
    else:
        cfg=design['equilibrium'];states=np.asarray(score);layers=payload['model']['layers']
        y,jac=network_reference(layers,states)
        future=states.copy();future[:,0]*=cfg['rho']
        fy,_=network_reference(layers,future)
        res=y-cfg['beta']*fy-states[:,0]*states[:,1]
        loss=float(np.dot(res,res)/len(res))
        expected=states[:,0]*states[:,1]/(1-cfg['beta']*cfg['rho'])
        expected_jac=states[:,[1,0]]/(1-cfg['beta']*cfg['rho'])
        metrics=payload['metrics']
        for actual,want in [(metrics['y'],y),(metrics['jacobian'],jac),(metrics['residual'],res),
                            (metrics['z'],cfg['lambda']*y+states[:,0]),
                            (metrics['policy_max_error'],max(abs(y-expected))),
                            (metrics['state_derivative_max_error'],max(abs(jac[:,0]-expected_jac[:,0]))),
                            (metrics['parameter_derivative_max_error'],max(abs(jac[:,1]-expected_jac[:,1])))]:
            check_close(actual,want)
        # An independently implemented central difference catches chain-rule defects.
        for j in (0,1):
            left=states.copy();right=states.copy();left[:,j]-=1e-5;right[:,j]+=1e-5
            numerical=(network_reference(layers,right)[0]-network_reference(layers,left)[0])/2e-5
            check_close(jac[:,j],numerical,atol=2e-7)
        parameter_count=sum(np.size(l['weight'])+len(l['bias']) for l in layers)
        assert parameter_count==payload['model']['parameters']
        assert len(layers)==payload['physical']['depth']+1
        assert len(layers[0]['bias'])==payload['physical']['width']
        work=2*(payload['model']['epochs']*len(train)+len(score))*parameter_count
    check_close(payload['loss'],loss)
    assert payload['work']==work
    return loss


def verify_run(directory):
    directory=Path(directory);design=read(directory/'design.json');summary=read(directory/'summary.json')
    count=0;traces=[]
    for seed in design['replicates']:
        base=directory/str(seed);records=read(base/'data.json');grid=read(base/'grid.json')
        recomputed={}
        for path in sorted((base/'grid/models').glob('*.json')):
            payload=artifact(path);loss=verify_payload(payload,records,design);count+=1
            key=json.dumps(payload['config'],sort_keys=True)
            recomputed.setdefault(key,[]).append(loss)
        oracle=min(math.fsum(v)/len(v) for v in recomputed.values())
        check_close(grid['minimum'],oracle)
        assert len(recomputed)==(15 if summary['name']=='response' else 18)
        for row in grid['rows']:
            check_close(row['mean'],math.fsum(recomputed[json.dumps(row['config'],sort_keys=True)])/2)
        for method in design['methods']:
            target=base/method;saved=read(target/'summary.json');trial={};final=[];work={'tuning':0,'final':0}
            for path in sorted((target/'models').glob('*.json')):
                payload=artifact(path);loss=verify_payload(payload,records,design);count+=1
                work[payload['role']]+=payload['work']
                if payload['role']=='final': final.append((payload,loss))
                else:
                    key=json.dumps(payload['config'],sort_keys=True)
                    trial.setdefault(key,[]).append(loss)
                    check_close(loss,recomputed[key][design['tuning_seeds'].index(payload['seed'])])
            means={k:math.fsum(v)/len(v) for k,v in trial.items()}
            check_close(saved['best_tuning'],min(means.values()))
            verify_regret(saved['regret'],min(means.values()),[oracle])
            assert len(final)==2 and all(p['config']==saved['best_config'] for p,_ in final)
            check_close(saved['final_mean'],math.fsum(v for _,v in final)/2)
            assert saved['proposals']==design['search_budget'] and saved['failures']==0
            assert saved['unique']==len(trial) and saved['resume_unchanged']
            assert saved['resource']['tuning']['attempts']==2*design['search_budget']
            assert saved['resource']['final']['attempts']==2
            for role in ('tuning','final'):
                assert saved['resource'][role]['charged_work']==work[role]
                assert saved['resource'][role]['contract_breaches']==0
            traces.append({'replicate':seed,'method':method,'regret':saved['regret'],'final_mean':saved['final_mean'],'checked':True})
    assert len(summary['rows'])==len(traces)
    for actual,expected in zip(summary['rows'],traces):
        for key in ('replicate','method','regret','final_mean'): assert actual[key]==expected[key]
    return {'passed':True,'name':summary['name'],'models_reconstructed':count,'studies':traces,
            'oracle':'Scalar logistic KKT/likelihood and independent NumPy forward/chain-rule plus central differences',
            'claim':'Finite numerical and workflow conformance; no empirical superiority or global neural approximation certificate'}


if __name__=='__main__':
    print(json.dumps(verify_run(sys.argv[1]),indent=2))
