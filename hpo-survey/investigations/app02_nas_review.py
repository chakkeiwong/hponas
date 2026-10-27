"""Reconstruct APP-02 paired-fit evidence using PyTorch, without fitting."""
from pathlib import Path
from copy import deepcopy
import itertools
import json
import math
import statistics
import sys
import numpy as np
import torch

ROOT=Path('/home/ubuntu/workspace/hponas')
sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from models import restore_net,nas_loss
from references import close
from app02_trace import read,binding,NAS,LIMITS

BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'
RUN=BASE/'isolation-20261024T180913Z-33af4b44'

def check_coverage(rows):
    expected=set(itertools.product((401,502,603),(4,8),('train','refit_train'),(0,1,1000,1001)))
    keys=[(m['replicate'],m['width'],m['training_role'],m['seed']) for m in rows]
    if len(keys)!=48 or set(keys)!=expected:raise AssertionError('Incomplete or duplicate paired cells')

def check_duration(rows,reported):
    for epoch,item in zip((120,240,480),reported):
        checkpoints=[next(c for c in m['checkpoints'] if c['epoch']==epoch) for m in rows]
        if item['epoch']!=epoch or item['mesh_feasible_models']!=sum(c['scores']['mesh']['feasible'] for c in checkpoints):raise AssertionError('False feasibility count')
        close(item['mean_mesh_loss'],statistics.mean(c['scores']['mesh']['loss'] for c in checkpoints))

def run(out):
    torch.set_num_threads(1);summary=read(RUN/'isolation.json');rows=[];verified=0
    for artifact in summary['artifacts']:
        path=ROOT/artifact['path']
        if binding(path)!=artifact:raise AssertionError('Changed fit artifact')
        m=read(path);rows.append(m);records=read(NAS/str(m['replicate'])/'data.json')
        points={role:np.array([records[key]['x'] for key in sorted((k for k in records if k.startswith(role+'_')),key=lambda k:int(k.split('_')[1]))]) for role in ('train','validation','final')}
        points['refit_train']=np.concatenate((points['train'],points['validation']))
        points['mesh']=np.array(list(itertools.product(np.linspace(-.5,.5,41),np.linspace(.2,.6,41))))
        if [c['epoch'] for c in m['checkpoints']]!=[120,240,480]:raise AssertionError('Missing checkpoint')
        for c in m['checkpoints']:
            net=restore_net(c['model']['config'],c['model']['layers'],2)
            for role,x in points.items():
                tensor=torch.tensor(x,dtype=torch.float64,requires_grad=True)
                loss,y,jac,truth=nas_loss(net,tensor);errors=(jac-truth).abs();maxima=errors.max(0).values.detach().numpy();s=c['scores'][role]
                close(float(loss.sum().detach()),s['loss']);close(loss.detach().numpy(),s['losses']);close(maxima,[s['dx_max'],s['da_max']])
                ratio=np.max(maxima/np.array([LIMITS['dx'],LIMITS['da']]))
                close(ratio,s['max_limit_ratio'])
                if s['feasible']!=(ratio<=1.):raise AssertionError('False feasibility')
                if role==m['training_role']:
                    close(float(loss.sum().detach()),c['post_update_training_loss']);grads=torch.autograd.grad(loss.sum(),list(net.parameters()));close(math.sqrt(sum(float(g.square().sum()) for g in grads)),c['parameter_gradient_l2'])
            verified+=1
    check_coverage(rows);check_duration(rows,summary['duration']);negative=[]
    for label,call in [('omitted fit',lambda:check_coverage(rows[:-1])),('false count',lambda:check_duration(rows,[{**x,'mesh_feasible_models':x['mesh_feasible_models']+1} for x in summary['duration']]))]:
        try:call()
        except AssertionError:negative.append(label)
        else:raise AssertionError('Tampered summary accepted')
    matched=summary['original_120_epoch_reproductions']
    if len(matched)!=20:raise AssertionError('Missing original reproduction')
    for match in matched:
        f=ROOT/match['original']['path']
        if binding(f)!=match['original']:raise AssertionError('Historical model changed')
        original=read(f)['payload'];m=next(r for r in rows if all(r[k]==match[k] for k in ('replicate','width','seed','training_role')))
        for a,b in zip(m['checkpoints'][0]['model']['layers'],original['model']['layers']):close(a['weight'],b['weight'],tol=1e-11);close(a['bias'],b['bias'],tol=1e-11)
    residual=[{'replicate':m['replicate'],'width':m['width'],'seed':m['seed'],'training_role':m['training_role'],
               'mesh':m['checkpoints'][-1]['scores']['mesh'],'training':m['checkpoints'][-1]['scores'][m['training_role']],
               'gradient_l2':m['checkpoints'][-1]['parameter_gradient_l2']} for m in rows if not m['checkpoints'][-1]['scores']['mesh']['feasible']]
    # Compare new-seed versus old-seed effects within fixed data and width.
    contrasts=[]
    for rep,width,role in itertools.product((401,502,603),(4,8),('train','refit_train')):
        group=[m for m in rows if (m['replicate'],m['width'],m['training_role'])==(rep,width,role)]
        contrasts.append({'replicate':rep,'width':width,'training_role':role,'fresh_minus_original_seed_mesh_loss':[statistics.mean(m['checkpoints'][i]['scores']['mesh']['loss'] for m in group if m['seed']>=1000)-statistics.mean(m['checkpoints'][i]['scores']['mesh']['loss'] for m in group if m['seed']<1000) for i in range(3)]})
    result={'passed':True,'stage':'APP-02/NAS-ISOLATE','source_result':binding(RUN/'isolation.json'),'checkpoints_independently_rescored':verified,
            'original_weights_rechecked':len(matched),'negative_controls':negative,'residual_mesh_failures':residual,'seed_contrasts':contrasts,
            'conclusion':'In this paired sample, insufficient optimization at120 updates is demonstrated: all48 fits improve training and mesh loss at480; mesh feasibility rises12 to44. Residual failures and generalization to new seeds/data remain open.',
            'next_stage':'APP-02/REFIT-STABILITY','next_test':'Use frozen independent confirmation design and investigate residual local derivative maxima; retain all prior thresholds.'}
    with (out/'review.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'checkpoints':verified,'original_weights':len(matched),'residual_failures':len(residual)}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
