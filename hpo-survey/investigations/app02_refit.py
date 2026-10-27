"""Prospectively fixed fresh-seed NAS duration/boundary comparison."""
import itertools,json,math,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from models import Network,nas_loss,save_net,restore_net
from references import close
from app02_trace import score,LIMITS

def run(out):
    torch.set_num_threads(1);rows=[]
    boundary=np.array([[-.5,.2],[-.5,.6],[.5,.2],[.5,.6],[0.,.2],[0.,.6],[-.5,.4],[.5,.4]])
    mesh=np.array(list(itertools.product(np.linspace(-.5,.5,81),np.linspace(.2,.6,81))))
    for rep in (2201,2202,2203):
        rng=np.random.default_rng(rep);raw=rng.uniform([-.5,.2],[.5,.6],(80,2));final=rng.uniform([-.5,.2],[.5,.6],(512,2))
        with (out/f'data-{rep}.json').open('x') as f:json.dump({'raw':raw.tolist(),'final':final.tolist(),'boundary':boundary.tolist()},f)
        for width,n,seed,arm in itertools.product((4,8),(48,80),(17,29),('random','boundary')):
            points=raw[:n].copy()
            if arm=='boundary':points[:8]=boundary
            config=dict(width=width,depth=2,activation='silu',learning_rate=.03)
            torch.manual_seed(rep*10000+seed);net=Network(config,2);optimizer=torch.optim.Adam(net.parameters(),lr=.03)
            x=torch.tensor(points,dtype=torch.float64,requires_grad=True);checkpoints=[]
            for epoch in range(1,481):
                optimizer.zero_grad();loss=nas_loss(net,x)[0].sum();assert torch.isfinite(loss);loss.backward();optimizer.step()
                if epoch not in (120,480):continue
                model=dict(config=config,layers=save_net(net),parameters=sum(p.numel() for p in net.parameters()),epochs=epoch)
                scores={role:score(model,values) for role,values in [('train',points),('final',final),('mesh',mesh)]}
                # Independently reconstruct NumPy derivatives with torch autograd.
                restored=restore_net(config,model['layers'],2)
                for role,values in [('train',points),('final',final),('mesh',mesh)]:
                    z=torch.tensor(values,dtype=torch.float64,requires_grad=True);losses,y,jac,ref=nas_loss(restored,z);maximum=(jac-ref).abs().max(0).values.detach().numpy()
                    close(float(losses.sum().detach()),scores[role]['loss']);close(maximum,[scores[role]['dx_max'],scores[role]['da_max']])
                checkpoints.append(dict(epoch=epoch,model=model,scores=scores))
            row=dict(replicate=rep,width=width,training_rows=n,seed=seed,arm=arm,checkpoints=checkpoints);rows.append(row)
            with (out/f'fit-{rep}-{width}-{n}-{seed}-{arm}.json').open('x') as f:json.dump(row,f,allow_nan=False)
        print(json.dumps({'replicate':rep,'fits_complete':len(rows)}),flush=True)
    assert len(rows)==48
    groups=[]
    for arm,n,epoch in itertools.product(('random','boundary'),(48,80),(120,480)):
        selected=[next(c for c in r['checkpoints'] if c['epoch']==epoch) for r in rows if r['arm']==arm and r['training_rows']==n]
        groups.append(dict(arm=arm,training_rows=n,epoch=epoch,fits=len(selected),mesh_feasible=sum(c['scores']['mesh']['feasible'] for c in selected),
                           final_feasible=sum(c['scores']['final']['feasible'] for c in selected),mean_mesh_loss=float(np.mean([c['scores']['mesh']['loss'] for c in selected])),
                           worst_ratio=max(c['scores']['mesh']['max_limit_ratio'] for c in selected)))
    paired=[]
    for rep,width,n,seed in itertools.product((2201,2202,2203),(4,8),(48,80),(17,29)):
        matches=[r for r in rows if (r['replicate'],r['width'],r['training_rows'],r['seed'])==(rep,width,n,seed)];a=next(r for r in matches if r['arm']=='random');b=next(r for r in matches if r['arm']=='boundary')
        paired.append(dict(replicate=rep,width=width,training_rows=n,seed=seed,boundary_minus_random_ratio=b['checkpoints'][-1]['scores']['mesh']['max_limit_ratio']-a['checkpoints'][-1]['scores']['mesh']['max_limit_ratio']))
    summary=dict(passed=True,stage='APP-02/REFIT-STABILITY',fits=48,independently_reconstructed_checkpoints=96,limits=LIMITS,groups=groups,paired=paired,
                 residual_failures=[{k:r[k] for k in ('replicate','width','training_rows','seed','arm')}|{'mesh':r['checkpoints'][-1]['scores']['mesh']} for r in rows if not r['checkpoints'][-1]['scores']['mesh']['feasible']],
                 interpretation='Fresh bounded matched test; architecture/optimizer/limits fixed. Finite mesh and fresh random points are not a continuous-domain certificate. Boundary intervention replaces8 random rows at constant sample count; no extra HPO or selection on final scores.')
    with (out/'refit.json').open('x') as f:json.dump(summary,f,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'groups':groups,'residual_failures':len(summary['residual_failures'])}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
