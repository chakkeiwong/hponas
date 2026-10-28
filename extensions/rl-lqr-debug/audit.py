"""Independent arithmetic, exact-control and finite-difference diagnostic audit."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import torch
from ray.rllib.core.columns import Columns
from hponas_rl_lqr_scalar.adapter import SACMember
from hponas_rl_lqr_scalar.reference import LQRSpec
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-07'
DIAG=BASE/'20261027T164854Z-diagnose-e084a525'
STUDY=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bound(b):
 p=Path(b['path']);p=p if p.is_absolute() else ROOT/p
 if sha(p)!=b['sha256']:raise ValueError('Changed bound evidence: '+str(p))
 return p
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def forbid(*a,**k):raise RuntimeError('No training permitted')
def minimum(member,obs,act):
 module=member.module;values=[]
 for encoder,head in [(module.qf_encoder,module.qf),(module.qf_twin_encoder,module.qf_twin)]:
  values.append(head(encoder({Columns.OBS:obs,Columns.ACTIONS:act})['encoder_out']).squeeze(-1))
 return torch.minimum(*values)
def main(out):
 torch.set_num_threads(1);torch.optim.Adam.step=forbid
 receipt=read(DIAG/'receipt.json');assert receipt['passed'] and receipt['inputs_unchanged'] and not receipt['remaining_children']
 assert not (DIAG/'work.jsonl').exists()
 manifest=read(DIAG/'manifest.json')
 for b in [manifest['runner'],*manifest['inputs']]:bound(b)
 result=read(DIAG/'diagnose-result.json');bound(result['study'])
 for b in result['upstream']:bound(b)
 probes=[read(bound(b)) for b in result['checkpoint_probes']];assert len(probes)==12
 expected={(c,s,'bgpbt') for c in ['scalar1','scalar3','padded3'] for s in [10601,10602,10603]}|{('scalar3',s,'default') for s in [10601,10602,10603]}
 assert {(p['case'],p['seed'],p['role']) for p in probes}==expected
 # Independent algebra uses arbitrary actions, states, continuation values and noise signs.
 rng=np.random.default_rng(107071);exact_error=0.;negative_controls=0
 for states in [1,10]:
  for _ in range(100):
   x=rng.normal(size=states);u=rng.uniform(-1,1,3);v=np.full(3,np.mean(u));w=rng.normal(size=states)*.025
   a=.8*x;a[0]=.92*x[0];next_u=a+w;next_u[0]+=sum(u)/np.sqrt(3)
   next_v=a+w;next_v[0]+=sum(v)/np.sqrt(3)
   continuation=lambda y:float(np.sin(y).sum()+np.square(y).sum())
   q_u=-(x[0]**2+.1*sum(u*u))+.99*continuation(next_u)
   q_v=-(x[0]**2+.1*sum(v*v))+.99*continuation(next_v)
   expected_gain=.1*sum((u-v)**2);error=abs(q_v-q_u-expected_gain);exact_error=max(exact_error,error)
   assert error<1e-12 and max(abs(v))<=1
   if expected_gain>1e-8:
    assert abs(q_u-q_v-expected_gain)>1e-8;negative_controls+=1
 finite=[]
 for p in probes:
  for b in [p['checkpoint'],p['actor'],p['result']]:bound(b)
  task=read(ROOT/p['result']['path']);assert p['counters']==task['after']
  assert p['target_clocks']['default_policy']==p['counters']['transitions']
  for key in ('grid_null','replay_policy_null','replay_behavior_null'):
   for c in p[key]['critics']:
    estimates=np.array(c['estimated_improvement']);exact=np.array(c['exact_improvement']);direction=np.array(c['directional_toward_projection'])
    assert int(((estimates<0)&(exact>1e-8)).sum())==c['wrong_ranking_count']
    assert int(((direction<0)&(exact>1e-8)).sum())==c['wrong_direction_count']
    assert np.allclose(np.array(c['exact_directional']),2*exact,atol=1e-12,rtol=1e-6)
  for c in p['terminal']:
   err=np.array(c['predicted'])-np.array(c['exact']);assert abs(np.sqrt(np.mean(err**2))-c['error']['rms'])<1e-12
  if p['case']!='scalar3' or p['role']!='bgpbt':continue
  member=SACMember.restore(ROOT/p['checkpoint']['path'],case='scalar3');member.train=forbid;member._update=forbid
  # Reconstruct retained deterministic action and Q ranking via explicit encoder/head calls.
  obs=torch.tensor(p['grid']['observations']);logits=member.module.pi(member.module.pi_encoder({Columns.OBS:obs})['encoder_out'])
  act=torch.tanh(logits.chunk(2,-1)[0]).detach();assert np.max(abs(act.numpy()-np.array(p['grid']['actions'])))<1e-7
  projected=act.mean(1,keepdim=True).expand_as(act);orth=act-projected
  with torch.no_grad():
   gain=(minimum(member,obs,projected)-minimum(member,obs,act)).numpy()
   eps=.001
   fd=((minimum(member,obs,act-eps*orth)-minimum(member,obs,act+eps*orth))/(2*eps)).numpy()
  saved=p['grid_null']['critics'][-1]
  # Independent mean projection and b*(b'u) differ by float32 rounding.
  with torch.no_grad():scale=max(1.,float(abs(minimum(member,obs,act)).max()),float(abs(minimum(member,obs,projected)).max()))
  rounding_limit=float(64*np.finfo(np.float32).eps*scale)
  projection_numeric_error=float(abs(gain-np.array(saved['estimated_improvement'])).max())
  assert projection_numeric_error<=rounding_limit,(projection_numeric_error,rounding_limit)
  direction=np.array(saved['directional_toward_projection']);fd_error=float(abs(fd-direction).max());assert fd_error<.003
  # Terminal target independently averages both actual possible next states.
  terminal_obs=np.repeat(np.array(p['grid']['observations'][-5:]),4,axis=0);xs=np.array([-.5,-.1,0,.1,.5]);actions=[]
  gain=.99*.92/(.1+.99)
  for i,x in enumerate(xs):actions += [act[-5+i].numpy(),np.zeros(3),np.full(3,-gain*x/np.sqrt(3)),np.full(3,.5)]
  exact=[]
  for o,u in zip(terminal_obs,actions):
   x=float(o[0]);mu=.92*x+sum(u)/np.sqrt(3)
   exact.append(-x*x-.1*sum(u*u)-.99*((mu-.025)**2+(mu+.025)**2)/2)
  assert np.max(abs(np.array(exact)-np.array(p['terminal'][-1]['exact'])))<1e-7
  # Independent rollout accumulation compares preserved active trajectories under projection.
  states=np.array([-.5,.5]*128,dtype=np.float64);projected_states=states.copy();cost=np.zeros(256);projected_cost=np.zeros(256);waste=np.zeros(256)
  generator=np.random.default_rng(107073);noise=.025*(2*generator.integers(2,size=(30,256))-1)
  actor=torch.jit.load(str(ROOT/p['actor']['path'])).eval();max_state_error=0.
  for t in range(30):
   ob=torch.tensor(np.column_stack([states,np.full(256,(30-t)/30)]),dtype=torch.float32)
   with torch.no_grad():u=actor(ob).numpy().astype(np.float64)
   ubar=np.repeat(u.mean(1,keepdims=True),3,axis=1)
   cost+=.99**t*(states**2+.1*np.square(u).sum(1));projected_cost+=.99**t*(projected_states**2+.1*np.square(ubar).sum(1))
   waste+=.99**t*.1*np.square(u-ubar).sum(1)
   states=.92*states+u.sum(1)/np.sqrt(3)+noise[t]
   projected_states=.92*projected_states+ubar.sum(1)/np.sqrt(3)+noise[t]
   max_state_error=max(max_state_error,float(abs(states-projected_states).max()))
  cost+=.99**30*states**2;projected_cost+=.99**30*projected_states**2
  path_error=float(abs(cost-projected_cost-waste).max());assert path_error<1e-10 and max_state_error<1e-10
  a=p['interventions'];assert abs((a['original']['cost']-a['projected']['cost'])-a['original']['nullspace_gap'])<1e-6
  finite.append(dict(seed=p['seed'],projection_numeric_error=projection_numeric_error,projection_numeric_rounding_limit=rounding_limit,finite_difference_max_error=fd_error,projection_rollout_identity_error=path_error,maximum_state_difference=max_state_error))
 # Reconstruct every population event from its frozen source and bind every consumed result.
 inputs=[];bad=total=scalar_bad=scalar_total=deteriorated=scalar_deteriorated=0
 for row in result['population']:
  freeze=read(bound(row['freeze']));events=[];candidates=[]
  for e in freeze['events']:
   if e['kind']!='architecture_generation':continue
   for recipient,child in zip(e['recipients'],e['student_results']):
    oldp=Path(freeze['snapshots'][1]['members'][recipient])/'result.json';newp=Path(child)/'result.json';old=read(oldp);new=read(newp)
    oldcost=old['score']['cost'];newcost=new['score']['cost'];bad+=newcost>oldcost;total+=1
    if row['case']=='scalar3':scalar_bad+=newcost>oldcost;scalar_total+=1
    inputs.extend([oldp,newp]);events.append((oldcost,newcost))
   for path in e['candidate_results']:
    q=Path(path)/'result.json';c=read(q);inputs.append(q);deteriorated+=c['score']['cost']>c['before_score']['cost']
    if row['case']=='scalar3':scalar_deteriorated+=c['score']['cost']>c['before_score']['cost']
  assert events==[(e['old_cost'],e['new_cost']) for e in row['replacements']]
 assert (bad,total,scalar_bad,scalar_total,deteriorated,scalar_deteriorated)==(10,18,3,6,34,11)
 for path in STUDY.glob('case-*/seed-*/*/result.json'):
  old=read(path)
  for name,digest in old['artifacts'].items():assert sha(path.parent/name)==digest
  inputs.append(path)
 unique=sorted(set(inputs));assert len(unique)==396
 report_summary=read(BASE/'report-result.json')
 bound(report_summary['source_result'])
 for row in report_summary['summary']:
  probe=next(p for p in probes if p['case']=='scalar3' and p['role']=='bgpbt' and p['seed']==row['seed'])
  critic=probe['replay_policy_null']['critics'][-1]
  assert row['wrong_ranking']==critic['wrong_ranking_count'] and row['wrong_gradient']==critic['wrong_direction_count']
  assert row['intervention_costs']=={k:v['cost'] for k,v in probe['interventions'].items()}
  a=probe['interventions'];fraction=(a['original']['cost']-a['odd_projected']['cost'])/a['original']['gap']
  assert row['fraction_gap_removed']==fraction

 report=dict(passed=True,new_training=0,checkpoints=12,artifact_result_rows=len(unique),exact_control_identity_error=exact_error,sign_reversal_negative_controls=negative_controls,independent_checks=finite,
  replacement_worse=dict(all_cases=[bad,total],scalar3=[scalar_bad,scalar_total]),post_transfer_deterioration=dict(all_cases=[deteriorated,36],scalar3=[scalar_deteriorated,12]),
  diagnostic_result=dict(path=str((DIAG/'diagnose-result.json').relative_to(ROOT)),sha256=sha(DIAG/'diagnose-result.json')),
  inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in unique],qualification='Failure diagnosis verified; no training repair or convergence claim.')
 write(out/'audit-result.json',report)
 print(json.dumps({k:v for k,v in report.items() if k!='inputs'},indent=2))
