"""Reconstruct saved wallet evidence without fitting or feeding search."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from wallet_model import GRID, objective, projected_gradient, bounds, population_metrics, observed_rows
from wallet_preflight import scalar_nll
ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'

def close(a,b,tol=1e-9):
    if not np.isfinite(a) or not np.isfinite(b) or abs(a-b)>tol*(1+abs(b)):raise AssertionError((a,b))

def check_record(record,data):
    final=record['role']=='final';roles=('train','validation') if final else ('train',)
    score='final' if final else 'validation'
    train_ids=[i for r in roles for i,ok in zip(data[r]['ids'],data[r]['observed']) if ok]
    score_ids=[i for i,ok in zip(data[score]['ids'],data[score]['observed']) if ok]
    assert record['train_ids']==train_ids and record['score_ids']==score_ids
    assert not set(train_ids)&set(score_ids)
    tx,ty=observed_rows(data,roles);sx,sy=observed_rows(data,(score,));m=record['model'];theta=np.array(m['theta'])
    value,gradient=objective(theta,tx,ty,m['config']);close(value,m['objective'])
    residual=projected_gradient(theta,gradient,bounds(m['config']));close(residual,m['projected_gradient'])
    assert residual<=1e-6
    close(scalar_nll(theta,sx,sy,m['config']),record['loss'])

def check_roster(rows):
    expected={(seed,method) for seed in (711,812,913) for method in ('random','sobol','gp','tpe')}
    assert len(rows)==12 and {(r['seed'],r['method']) for r in rows}==expected

def run(out):
    manifest=json.loads((BASE/'wallet-review-manifest-01.json').read_text());source=ROOT/manifest['study_directory']
    result=json.loads((source/'results.json').read_text());check_roster(result['studies'])
    assert result['fits']==468;checked=0;grid_count=0;max_resolution=0.;fit_seconds=0.
    data_by_seed={}
    for seed in (711,812,913):
        raw=json.loads((source/str(seed)/'data.json').read_text())
        data={r:{k:(np.asarray(v) if k in ('x','wallet','observed') else v) for k,v in d.items()} for r,d in raw.items()};data_by_seed[seed]=data
        grid=json.loads((source/str(seed)/'grid.json').read_text());assert len(grid['rows'])==24
        assert {json.dumps(g['model']['config'],sort_keys=True) for g in grid['rows']}=={json.dumps(c,sort_keys=True) for c in GRID}
        tx,ty=observed_rows(data,('train',));vx,vy=observed_rows(data,('validation',))
        for g in grid['rows']:
            m=g['model'];theta=np.array(m['theta']);value,gradient=objective(theta,tx,ty,m['config'])
            close(value,m['objective']);assert projected_gradient(theta,gradient,bounds(m['config']))<=1e-6
            close(scalar_nll(theta,vx,vy,m['config']),g['validation']);grid_count+=1;fit_seconds+=m['seconds']
        close(min(g['validation'] for g in grid['rows']),grid['minimum'])
    for row in result['studies']:
        data=data_by_seed[row['seed']];directory=source/str(row['seed'])/row['method']
        records=[json.loads(p.read_text()) for p in sorted((directory/'models').glob('*.json'))]
        tune=[r for r in records if r['role']=='tuning'];final=[r for r in records if r['role']=='final']
        assert len(tune)==32 and len(final)==1
        for r in records:check_record(r,data);checked+=1;fit_seconds+=r['model']['seconds']
        close(min(r['loss'] for r in tune),row['best_validation'])
        close(row['best_validation']-row['finite_minimum'],row['search_regret'])
        assert row['unique']==len({json.dumps(r['model']['config'],sort_keys=True) for r in tune})
        assert final[0]['model']['config']==row['best_config'] and final[0]['model']==row['after']
        for role in ('before','after'):
            metrics=population_metrics(row[role],48)
            for k,v in metrics.items():close(v,row['population_'+role][k])
        m96=population_metrics(row['after'],96)
        resolution={k:abs(m96[k]-row['population_after'][k]) for k in m96}
        assert resolution['expected_nll']<1e-7
        max_resolution=max(max_resolution,resolution['allocation_decision_regret'])
    assert checked+grid_count==468
    controls=[]
    try:check_roster(result['studies'][:-1])
    except AssertionError:controls.append('omitted study rejected')
    else:raise AssertionError('Missing-study control not detected')
    bad=copy.deepcopy(records[0]);bad['loss']+=.1
    try:check_record(bad,data)
    except AssertionError:controls.append('altered score rejected')
    else:raise AssertionError('Score control not detected')
    bad=copy.deepcopy(records[0]);bad['train_ids'].append(bad['score_ids'][0])
    try:check_record(bad,data)
    except AssertionError:controls.append('role leakage rejected')
    else:raise AssertionError('Leakage control not detected')
    report=dict(passed=True,checked_model_records=checked+grid_count,controls=controls,
                max_allocation_regret_resolution_change_48_to_96=max_resolution,total_fit_seconds=fit_seconds,
                study_result={'path':str((source/'results.json').relative_to(ROOT)),'sha256':hashlib.sha256((source/'results.json').read_bytes()).hexdigest()},
                limits=['Stationarity is not global nonconvex optimality.','Analytic conditional risk integrated numerically over covariates.','Synthetic result does not establish real SME calibration.'])
    with (out/'review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(report),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
