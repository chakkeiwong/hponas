"""Fixed paired diagnostic; preserves APP-01 source and all historical fits."""
import json
import math
from pathlib import Path
import statistics
import sys
import numpy as np
import torch

ROOT=Path('/home/ubuntu/workspace/hponas')
sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from models import Network,nas_loss,save_net
from references import close
from app02_trace import NAS,score,read,payload,binding,canonical

BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'

def run(out):
    design=read(BASE/'nas-isolation-design-01.json');torch.set_num_threads(1)
    mesh=np.array([(x,a) for x in np.linspace(-.5,.5,41) for a in np.linspace(.2,.6,41)])
    models=[];matches=[]
    for rep in design['replicates']:
        base=NAS/str(rep);records=read(base/'data.json')
        points={role:np.array([records[key]['x'] for key in sorted((k for k in records if k.startswith(role+'_')),key=lambda k:int(k.split('_')[1]))]) for role in ('train','validation','final')}
        points['refit_train']=np.concatenate((points['train'],points['validation']));points['mesh']=mesh
        originals={}
        for path in sorted(base.glob('*/models/*.json')):
            p=payload(path);cfg=p['physical']
            if cfg['activation']=='silu' and cfg['depth']==2 and cfg['learning_rate']==.03 and cfg['width'] in design['widths']:
                key=(cfg['width'],p['seed'],'train' if p['role']=='tuning' else 'refit_train')
                originals.setdefault(key,(p,path))
        for width in design['widths']:
            cfg={'width':width,'depth':2,'activation':'silu','learning_rate':.03}
            for train_role in design['training_roles']:
                for seed in design['seeds']:
                    x=torch.tensor(points[train_role],dtype=torch.float64,requires_grad=True)
                    with torch.random.fork_rng(devices=[]):
                        torch.manual_seed(rep*10000+seed);net=Network(cfg,2);optimizer=torch.optim.Adam(list(net.parameters()),lr=.03)
                        checkpoints=[]
                        for epoch in range(1,max(design['checkpoints'])+1):
                            optimizer.zero_grad();loss=nas_loss(net,x)[0].sum()
                            if not torch.isfinite(loss):raise AssertionError('Nonfinite diagnostic fit')
                            loss.backward();optimizer.step()
                            if epoch not in design['checkpoints']:continue
                            layers=save_net(net);m={'layers':layers,'config':cfg,'parameters':sum(p.numel() for p in net.parameters()),'log_scale':0.,'epochs':epoch}
                            scores={role:score(m,values) for role,values in points.items()}
                            post=nas_loss(net,x)[0].sum();grads=torch.autograd.grad(post,list(net.parameters()))
                            close(float(post.detach()),scores[train_role]['loss'])
                            checkpoint={'epoch':epoch,'pre_update_training_loss':float(loss.detach()),'post_update_training_loss':float(post.detach()),
                                        'parameter_gradient_l2':math.sqrt(sum(float(g.square().sum()) for g in grads)),
                                        'scores':scores,'model':m}
                            key=(width,seed,train_role)
                            if epoch==120 and key in originals:
                                p,path=originals[key]
                                for actual,expected in zip(layers,p['model']['layers']):
                                    close(actual['weight'],expected['weight'],tol=1e-11);close(actual['bias'],expected['bias'],tol=1e-11)
                                role='validation' if train_role=='train' else 'final';close(scores[role]['loss'],p['loss'],tol=1e-11)
                                matches.append({'replicate':rep,'width':width,'seed':seed,'training_role':train_role,'original':binding(path)})
                            checkpoints.append(checkpoint)
                    row={'replicate':rep,'width':width,'seed':seed,'training_role':train_role,'checkpoints':checkpoints}
                    models.append(row)
                    name=f'{rep}-w{width}-{train_role}-s{seed}.json'
                    with (out/name).open('x') as f:json.dump(row,f,sort_keys=True,allow_nan=False)
                    print(json.dumps({'fit':name,'loss120':checkpoints[0]['post_update_training_loss'],'loss480':checkpoints[-1]['post_update_training_loss'],'mesh_ratio120':checkpoints[0]['scores']['mesh']['max_limit_ratio'],'mesh_ratio480':checkpoints[-1]['scores']['mesh']['max_limit_ratio']}),flush=True)
    assert len(models)==48 and len(matches)==20,(len(models),len(matches))
    duration=[];groups=[]
    for epoch in design['checkpoints']:
        rows=[next(c for c in m['checkpoints'] if c['epoch']==epoch) for m in models]
        duration.append({'epoch':epoch,'mesh_feasible_models':sum(c['scores']['mesh']['feasible'] for c in rows),
                         'mean_mesh_loss':statistics.mean(c['scores']['mesh']['loss'] for c in rows),
                         'median_mesh_limit_ratio':statistics.median(c['scores']['mesh']['max_limit_ratio'] for c in rows),
                         'worst_mesh_limit_ratio':max(c['scores']['mesh']['max_limit_ratio'] for c in rows)})
        for width in design['widths']:
            for role in design['training_roles']:
                selected=[next(c for c in m['checkpoints'] if c['epoch']==epoch) for m in models if m['width']==width and m['training_role']==role]
                groups.append({'epoch':epoch,'width':width,'training_role':role,'n':len(selected),
                               'mesh_feasible':sum(c['scores']['mesh']['feasible'] for c in selected),
                               'mean_mesh_loss':statistics.mean(c['scores']['mesh']['loss'] for c in selected)})
    paired=[]
    for rep in design['replicates']:
        for width in design['widths']:
            for seed in design['seeds']:
                a=next(m for m in models if m['replicate']==rep and m['width']==width and m['seed']==seed and m['training_role']=='train')
                b=next(m for m in models if m['replicate']==rep and m['width']==width and m['seed']==seed and m['training_role']=='refit_train')
                paired.append({'replicate':rep,'width':width,'seed':seed,'refit_data_mesh_loss_change':[y['scores']['mesh']['loss']-x['scores']['mesh']['loss'] for x,y in zip(a['checkpoints'],b['checkpoints'])]})
    result={'passed':True,'stage':'APP-02/NAS-ISOLATE','design':binding(BASE/'nas-isolation-design-01.json'),'fits':len(models),
            'original_120_epoch_reproductions':matches,'duration':duration,'groups':groups,'paired_data_effects':paired,
            'improved_training_loss_120_to_480':sum(m['checkpoints'][-1]['post_update_training_loss']<m['checkpoints'][0]['post_update_training_loss'] for m in models),
            'improved_mesh_loss_120_to_480':sum(m['checkpoints'][-1]['scores']['mesh']['loss']<m['checkpoints'][0]['scores']['mesh']['loss'] for m in models),
            'artifacts':[binding(p) for p in sorted(out.glob('*.json')) if p.name.startswith(('401-','502-','603-'))],
            'limits':['Exploratory diagnosis on retained data, not fresh confirmation.','Finite mesh feasibility is not a uniform-domain certificate.','Duration intervention retains exact architecture, Adam settings, training objective and seeds.','No model is selected using old final results; no new optimizer performance claim.']}
    with (out/'isolation.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ('passed','fits','duration','improved_training_loss_120_to_480','improved_mesh_loss_120_to_480')}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
