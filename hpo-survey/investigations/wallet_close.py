"""Wallet closure: reconstruct fresh CV study and quantify retained selection noise."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.integrate import quad
from scipy.special import ndtr, expit
from wallet_model import (GRID, parameters, truth, log_parts, covariate_rule,
                         objective, projected_gradient, bounds, population_metrics)
from wallet_preflight import scalar_nll
ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'

def close(a,b,tol=1e-9):
    if not math.isfinite(a) or not math.isfinite(b) or abs(a-b)>tol*(1+abs(b)):raise AssertionError((a,b))

def truncated_moments(mu,sigma):
    """E[L^k 1(L>0)] k0..4 from normal integration-by-parts recurrence."""
    a=-mu/sigma;phi=np.exp(-a*a/2)/math.sqrt(2*math.pi)
    z=[ndtr(-a),phi]
    for k in range(2,5):z.append(a**(k-1)*phi+(k-1)*z[k-2])
    return [sum(math.comb(k,j)*mu**(k-j)*sigma**j*z[j] for j in range(k+1)) for k in range(5)]

def difference_moments(a,b,order=48):
    x,w=covariate_rule(order);mt,st,et=truth(x);pt=expit(et)
    ma,sa,ea=parameters(np.array(a['theta']),x,a['config']);mb,sb,eb=parameters(np.array(b['theta']),x,b['config'])
    lpa,lqa=log_parts(ma,sa,ea);lpb,lqb=log_parts(mb,sb,eb);_,lqt=log_parts(mt,st,et)
    c=[-lpa+lpb+np.log(sa/sb)+.5*(ma*ma/(sa*sa)-mb*mb/(sb*sb)),
       -ma/(sa*sa)+mb/(sb*sb),.5/(sa*sa)-.5/(sb*sb)]
    t=truncated_moments(mt,st);square=[np.zeros(len(x)) for _ in range(5)]
    for i in range(3):
        for j in range(3):square[i+j]+=c[i]*c[j]
    d0=lqb-lqa;q0=np.exp(lqt)
    mean=w@(q0*d0+pt*sum(c[k]*t[k] for k in range(3)))
    second=w@(q0*d0*d0+pt*sum(square[k]*t[k] for k in range(5)))
    return float(mean),float(max(0.,second-mean*mean))

def load_data(path):
    raw=json.loads(path.read_text())
    return {r:{k:(np.array(v) if k in ('x','wallet','observed') else v) for k,v in row.items()} for r,row in raw.items()}

def run(out):
    manifest=json.loads((BASE/'wallet-close-manifest-01.json').read_text());study=ROOT/manifest['study_directory'];selection=ROOT/manifest['selection_directory']
    result=json.loads((selection/'selection-results.json').read_text())
    expected={(s,m) for s in (1721,1822,1923) for m in ('holdout','cv3')}
    assert len(result['studies'])==6 and {(r['seed'],r['mode']) for r in result['studies']}==expected
    checked=0;model_times=[];audit_rows=[]
    for row in result['studies']:
        directory=selection/str(row['seed'])/row['mode'];data=load_data(selection/str(row['seed'])/'data.json')
        mapping={i:(x,float(w)) for d in data.values() for i,x,w,ok in zip(d['ids'],d['x'],d['wallet'],d['observed']) if ok}
        declaration=json.loads((directory/'declaration.json').read_text());folds={f['name']:f for f in declaration['tuning_folds']+declaration['final_folds']}
        records=[json.loads(p.read_text()) for p in sorted((directory/'models').glob('*.json'))]
        tuning=[r for r in records if r['role']=='tuning'];final=[r for r in records if r['role']=='final'];nfolds=3 if row['mode']=='cv3' else 1
        assert len(tuning)==24*nfolds and len(final)==1
        for rec in records:
            fold=folds[rec['fold']];assert rec['train_ids']==fold['train_ids'] and rec['score_ids']==fold['score_ids']
            assert not set(rec['train_ids'])&set(rec['score_ids'])
            tx=np.array([mapping[i][0] for i in rec['train_ids']]);ty=np.array([mapping[i][1] for i in rec['train_ids']])
            sx=np.array([mapping[i][0] for i in rec['score_ids']]);sy=np.array([mapping[i][1] for i in rec['score_ids']]);m=rec['model'];theta=np.array(m['theta'])
            close(scalar_nll(theta,sx,sy,m['config']),rec['loss']);value,gradient=objective(theta,tx,ty,m['config']);close(value,m['objective'])
            assert projected_gradient(theta,gradient,bounds(m['config']))<=1e-6;checked+=1;model_times.append(m['seconds'])
        scores=[]
        for cfg in GRID:
            selected=[r for r in tuning if r['model']['config']==cfg];assert len(selected)==nfolds
            assert len({r['fold'] for r in selected})==nfolds;scores.append((float(np.mean([r['loss'] for r in selected])),cfg))
        close(min(v for v,c in scores),row['selection_score']);assert final[0]['model']['config']==row['best_config']
        assert final[0]['model']==row['final_model'];close(final[0]['loss'],row['final_sample_nll'])
        metrics=population_metrics(row['final_model'],96)
        for k,v in metrics.items():close(v,row['population'][k])
        audit_rows.append(dict(seed=row['seed'],mode=row['mode'],fits=len(records),population=metrics))
    assert checked==result['fits']==294
    # Independent quadrature checks the fourth-order recurrence used below.
    moment_errors=[]
    for mu,sigma in ((-.5,.4),(.2,.7),(.8,1.)):
        values=truncated_moments(np.array([mu]),np.array([sigma]))
        for k in range(5):
            numerical=quad(lambda z:z**k*math.exp(-.5*((z-mu)/sigma)**2)/(sigma*math.sqrt(2*math.pi)),0,np.inf,epsabs=1e-11)[0]
            error=abs(numerical-values[k][0]);moment_errors.append(error);assert error<1e-9
    original=json.loads((study/'results.json').read_text());decomposition=[]
    for seed in (711,812,913):
        grid=json.loads((study/str(seed)/'grid.json').read_text());diagnostic=next(g for g in original['grids'] if g['seed']==seed)
        val=min(grid['rows'],key=lambda r:r['validation']);pop=min(diagnostic['rows'],key=lambda r:r['population']['expected_nll']);competitor=next(g for g in grid['rows'] if g['index']==pop['index'])
        mean,var=difference_moments(val['model'],competitor['model']);data=load_data(study/str(seed)/'data.json');n=int(data['validation']['observed'].sum());se=math.sqrt(var/n)
        expected_difference=population_metrics(val['model'],48)['expected_nll']-population_metrics(competitor['model'],48)['expected_nll'];close(mean,expected_difference)
        observed=val['validation']-competitor['validation']
        decomposition.append(dict(seed=seed,validation_winner=val['index'],population_best_fitted_candidate=pop['index'],validation_observed=n,
                    observed_nll_difference=observed,known_law_expected_difference=mean,known_law_difference_sd=math.sqrt(var),
                    fixed_pair_mean_standard_error=se,descriptive_standardized_deviation=(observed-mean)/se if se else None,
                    interpretation='Pair selected after inspection: descriptive noise scale only, not a selection-adjusted p-value or confidence interval.'))
    controls=[]
    try:close(audit_rows[0]['population']['expected_nll']+.1,audit_rows[0]['population']['expected_nll'])
    except AssertionError:controls.append('altered population score rejected')
    else:raise AssertionError('Control missed')
    report=dict(passed=True,reconstructed_fresh_fits=checked,prior_reconstructed_fits=468,
                maximum_moment_formula_error=float(max(moment_errors)),selection_noise=decomposition,
                fresh_studies=audit_rows,controls=controls,contrasts=result['contrasts'],
                interpretation={'sampling':'Known-law NLL difference variance quantifies finite validation noise without new simulation; post-selection pairs are descriptive.',
                                'repair':'Exact enumeration removes duplicate evaluations in this24-candidate deterministic domain. CV evidence is mixed and is not promoted as a universal repair.',
                                'scope':'Known synthetic mechanisms, independent of sibling runtime. Does not establish the full SMEwallet program or general neural NAS.'})
    with (out/'closure.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(report),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
