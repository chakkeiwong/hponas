"""Zero-training probes of retained RL-LQR-06 checkpoints."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import torch
from ray.rllib.core.columns import Columns
from hponas_rl_lqr_scalar.adapter import SACMember,MID
from hponas_rl_lqr_scalar.reference import LQRSpec,riccati,sample_policy
from hponas_rl_lqr_scalar.scoring import action_rows
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-07'
STUDY=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3'

def read(p):return json.loads(Path(p).read_text())
def bind(p):
 p=Path(p); return dict(path=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def forbid(*a,**k):raise RuntimeError('Training forbidden in RL-LQR-07 diagnosis')
def stats(x):
 x=np.asarray(x,dtype=float);return dict(mean=float(x.mean()),rms=float(np.sqrt(np.square(x).mean())),max_abs=float(abs(x).max()))
def logits(member,obs):return member.module.forward_inference({Columns.OBS:obs})[Columns.ACTION_DIST_INPUTS]
def q_values(member,obs,act):
 m=member.module;b={Columns.OBS:obs,Columns.ACTIONS:act}
 q1=m._qf_forward_train_helper(b,m.qf_encoder,m.qf)
 q2=m._qf_forward_train_helper(b,m.qf_twin_encoder,m.qf_twin)
 return q1,q2,torch.minimum(q1,q2)

def null_probe(member,obs,act):
 b=torch.ones(member.actions)/math.sqrt(member.actions)
 u=act.detach().clone().requires_grad_(True)
 projected=(u@b)[:,None]*b;orthogonal=u-projected
 old=q_values(member,obs,u);new=q_values(member,obs,projected)
 exact=.1*orthogonal.square().sum(1)
 values=[]
 for label,old_q,new_q in zip(('q1','q2','minimum'),old,new):
  grad=torch.autograd.grad(old_q.sum(),u,retain_graph=True)[0]
  gn=grad-(grad@b)[:,None]*b
  directional=(grad*(-orthogonal)).sum(1)
  values.append(dict(critic=label,estimated_improvement=(new_q-old_q).detach().tolist(),exact_improvement=exact.detach().tolist(),
   improvement_error=stats((new_q-old_q-exact).detach().numpy()),wrong_ranking_count=int(((new_q-old_q<0)&(exact>1e-8)).sum()),
   eligible_count=int((exact>1e-8).sum()),null_gradient_error=stats((gn+.2*orthogonal).detach().numpy()),
   directional_toward_projection=directional.detach().tolist(),exact_directional=(2*exact).detach().tolist(),
   wrong_direction_count=int(((directional<0)&(exact>1e-8)).sum())))
 return dict(rows=len(obs),critics=values)

def probe_checkpoint(case,seed,role,chosen):
 path=Path(chosen.get('task') or chosen['selection_task']);saved=read(path/'result.json')
 before_hash=bind(path/'checkpoint.pt');member=SACMember.restore(path/'checkpoint.pt',case=case)
 assert member.counters()==saved['after']
 member.train=forbid; member._update=forbid
 for opt in member.optimizers().values():opt.step=forbid
 spec=member.specification;d=spec.states;m=spec.actions
 x=np.array([-.5,-.1,0.,.1,.5]);times=[0,15,29]
 grid=np.array([[v,*([0.]*(d-1)),(30-t)/30] for t in times for v in x],dtype=np.float32)
 obs=torch.from_numpy(grid)
 with torch.no_grad():
  raw=logits(member,obs);mu,ls=raw.chunk(2,-1);acts=torch.tanh(mu)
  dist=member.module.get_train_action_dist_cls().from_logits(raw)
  torch.manual_seed(1071000+seed)
  actions,logp=dist.rsample_and_logp(sample_shape=(256,))
  entropy=-logp.mean(0);stochastic_null=actions-(actions.sum(-1,keepdim=True)/m)
  std=ls.clamp(-20,2).exp()
  exported=torch.jit.load(str(path/'actor.pt')).eval()(obs)
 assert float(abs(exported-acts).max())<1e-6
 ids=np.linspace(0,len(member.replay)-1,min(512,len(member.replay)),dtype=int)
 rows=[member.replay[i] for i in ids]
 replay_obs=torch.tensor(np.asarray([r[0] for r in rows]),dtype=torch.float32)
 replay_act=torch.tensor(np.asarray([r[1] for r in rows]),dtype=torch.float32)
 with torch.no_grad():replay_mu=torch.tanh(logits(member,replay_obs).chunk(2,-1)[0])
 replay_errors=[];clock_errors=[];dyn_errors=[]
 for old,u,reward,nxt,done in member.replay:
  t=int(round(30*(1-float(old[-1]))));expected=-(old[:-1]@spec.Q@old[:-1]+u@spec.R@u+(spec.gamma*nxt[:-1]@spec.Q@nxt[:-1] if done else 0))
  replay_errors.append(reward-expected);clock_errors.append(abs(float(nxt[-1])-(29-t)/30))
  if done!=(t==29):raise ValueError('Recorded termination differs')
  innovation=nxt[:-1]-spec.A@old[:-1]-spec.B@u
  dyn_errors.append(min(np.max(abs(innovation-spec.noise_vector)),np.max(abs(innovation+spec.noise_vector))))
 terminal_obs=np.repeat(grid[-5:],4,axis=0)
 terminal_actions=[]
 for i,v in enumerate(x):
  optimal=-riccati(spec)['K'][29]@np.array([v,*([0.]*(d-1))])
  terminal_actions.extend([acts[-5+i].numpy(),np.zeros(m),optimal,np.ones(m)*.5])
 tu=torch.tensor(np.asarray(terminal_actions),dtype=torch.float32);to=torch.tensor(terminal_obs)
 tx=to[:,:d].numpy();ua=tu.numpy();next_mean=tx@spec.A.T+ua@spec.B.T
 exact_terminal=-(np.einsum('bi,ij,bj->b',tx,spec.Q,tx)+np.einsum('bi,ij,bj->b',ua,spec.R,ua)+spec.gamma*(np.einsum('bi,ij,bj->b',next_mean,spec.Q,next_mean)+spec.noise_vector@spec.Q@spec.noise_vector))
 with torch.no_grad():pred=[z.numpy() for z in q_values(member,to,tu)]
 terminal=[dict(critic=k,predicted=a.tolist(),exact=exact_terminal.tolist(),error=stats(a-exact_terminal)) for k,a in zip(('q1','q2','minimum'),pred)]
 clocks={str(k):int(v) for k,v in member.learner.last_update_ts_by_mid.items()}
 summary=dict(case=case,seed=seed,role=role,checkpoint=before_hash,actor=bind(path/'actor.pt'),result=bind(path/'result.json'),counters=member.counters(),target_clocks=clocks,
  replay_count=len(member.replay),replay_reward_error=stats(replay_errors),replay_clock_error=stats(clock_errors),replay_dynamics_error=stats(dyn_errors),
  replay_state_quantiles=np.quantile(abs(np.asarray([r[0][0] for r in member.replay])),[0,.25,.5,.75,.95,1]).tolist(),
  replay_fraction_abs_x_below_point1=float(np.mean(abs(np.asarray([r[0][0] for r in member.replay]))<.1)),
  replay_terminal_count=sum(bool(r[4]) for r in member.replay),target_entropy=float(member.learner.target_entropy[MID]),
  grid=dict(observations=grid.tolist(),actions=acts.tolist(),pre_tanh_std=std.tolist(),entropy=entropy.tolist(),mean_stochastic_null_cost=(.1*stochastic_null.square().sum(-1)).mean(0).tolist()),
  grid_null=null_probe(member,obs,acts),replay_policy_null=null_probe(member,replay_obs,replay_mu),
  replay_behavior_null=null_probe(member,replay_obs,replay_act),terminal=terminal)
 if case=='scalar3' and role=='bgpbt':
  actor=torch.jit.load(str(path/'actor.pt')).eval()
  def policy(states,t):return action_rows(actor,states,t)
  def projection(states,t):
   u=policy(states,t);return np.repeat(u.mean(1,keepdims=True),m,axis=1)
  def odd(states,t):return .5*(policy(states,t)-policy(-states,t))
  def both(states,t):
   u=odd(states,t);return np.repeat(u.mean(1,keepdims=True),m,axis=1)
  summary['interventions']={k:sample_policy(f,spec=spec,count=4096,seed=1070001) for k,f in [('original',policy),('projected',projection),('odd',odd),('odd_projected',both)]}
  a=summary['interventions']['original'];b=summary['interventions']['projected']
  assert abs((a['cost']-b['cost'])-a['nullspace_gap'])<1e-6
 if bind(path/'checkpoint.pt')!=before_hash:raise ValueError('Checkpoint changed')
 return summary

def population_trace():
 rows=[]
 for p in sorted(STUDY.glob('case-*/seed-*/selection-freeze.json')):
  f=read(p);events=[]
  for e in f['events']:
   if e['kind']!='architecture_generation':continue
   donor=read(Path(f['snapshots'][1]['members'][e['donor']])/'result.json')
   for recipient,child in zip(e['recipients'],e['student_results']):
    old=read(Path(f['snapshots'][1]['members'][recipient])/'result.json');new=read(Path(child)/'result.json')
    events.append(dict(recipient=recipient,old_cost=old['score']['cost'],new_cost=new['score']['cost'],worse=new['score']['cost']>old['score']['cost'],child=child))
   candidates=[]
   for path in e['candidate_results']:
    r=read(Path(path)/'result.json');tr=r['transfer']
    candidates.append(dict(task=path,config=r['task']['config'],donor_cost=donor['score']['cost'],after_distill_cost=r['before_score']['cost'],after_sac_cost=r['score']['cost'],distillation_final_losses=tr['final_losses'],distillation_initial_losses=tr['initial_losses'],alpha=r['after']['alpha']))
  all_rows=[read(Path(path)/'result.json') for path in f['population_results']]
  continued=[r for r in all_rows if r['task']['kind']=='train']
  rows.append(dict(case=f['case'],seed=f['seed'],freeze=bind(p),replacements=events,candidates=candidates,
   continuation_worsened=sum(r['score']['cost']>r['before_score']['cost'] for r in continued),continuations=len(continued),
   best=f['selected']['bgpbt'],final_best=min(f['snapshots'][-1]['costs'])))
 return rows

def main(out):
 torch.set_num_threads(1);torch.optim.Adam.step=forbid
 study=read(STUDY/'study-result.json'); results=[]
 for t in study['tests']:
  roles=('bgpbt','default') if t['case']=='scalar3' else ('bgpbt',)
  for role in roles:
   row=probe_checkpoint(t['case'],t['seed'],role,t['methods'][role]);results.append(row)
   write(out/f"probe-{t['case']}-{t['seed']}-{role}.json",row)
   print(json.dumps(dict(case=t['case'],seed=t['seed'],role=role,critic_wrong_projection=row['grid_null']['critics'][-1]['wrong_ranking_count'],terminal_q_rmse=row['terminal'][-1]['error']['rms'])),flush=True)
 assert len(results)==12
 upstream=Path('/home/ubuntu/miniforge3/lib/python3.13/site-packages/ray/rllib')
 report=dict(passed=True,new_training=dict(transitions=0,sac_updates=0,distillation_updates=0),study=bind(STUDY/'study-result.json'),checkpoint_probes=[bind(p) for p in sorted(out.glob('probe-*.json'))],population=population_trace(),
  upstream=[bind(upstream/p) for p in ['algorithms/sac/torch/sac_torch_learner.py','algorithms/sac/sac_learner.py','algorithms/sac/torch/default_sac_torch_rl_module.py','algorithms/dqn/dqn_learner.py','core/distribution/torch/torch_distribution.py']],
  limitations=['Post-hoc diagnostic, no repaired-policy training or confirmation.','Soft-Q need not equal hard optimal-Q; only policy-independent exact identities tested.','Neural critic approximation violations are measured symptoms, not proof of a software-sign bug.'])
 write(out/'diagnose-result.json',report)
