"""Safe successor handoff; donor is immutable and replacement requires evidence."""
from copy import deepcopy
import numpy as np
import torch
from ray.rllib.core.columns import Columns
from hponas_rl_bgpbt.work import charge
from hponas_rl_lqr_scalar.transfer import outputs,losses
from .adapter import SACMember,Actor,BATCH,MID,digest
from .diagnostics import q_values,evaluate,replace

def fidelity(student,teacher,obs,act,create_graph=False):
    u=act.detach().clone().requires_grad_(True)
    so=outputs(student.module,obs,u);to=outputs(teacher.module,obs,u)
    basic=losses(so,tuple(v.detach() for v in to))
    gradient=[]
    for s,t in zip(so[1:],to[1:]):
        gs=torch.autograd.grad(s.sum(),u,create_graph=create_graph,retain_graph=True)[0]
        gt=torch.autograd.grad(t.sum(),u,retain_graph=True)[0].detach()
        gradient.append((gs-gt).square().mean())
    projected=act.mean(-1,keepdim=True).expand_as(act)
    sp=q_values(student,obs,projected);tp=q_values(teacher,obs,projected)
    differences=[((sp[i]-so[i+1])-(tp[i]-to[i+1]).detach()).square().mean() for i in range(2)]
    return torch.cat((basic,torch.stack(gradient),torch.stack(differences)))

def critic_adapt(member,steps):
    before=digest(Actor(member.module).state_dict());alpha=member.learner.curr_log_alpha[MID].detach().clone()
    member._activate_rng();opts=member.optimizers()
    with charge(dict(critic_updates=steps),'frozen_actor_critic_adaptation'):
        for _ in range(steps):
            rows=[member.replay[i] for i in member.rng.integers(len(member.replay),size=BATCH)]
            obs,act,rew,nxt,done=zip(*rows)
            batch={Columns.OBS:torch.tensor(np.asarray(obs),dtype=torch.float32),
                   Columns.ACTIONS:torch.tensor(np.asarray(act),dtype=torch.float32),
                   Columns.NEXT_OBS:torch.tensor(np.asarray(nxt),dtype=torch.float32)}
            f=member.module.forward_train(batch)
            target=torch.tensor(rew,dtype=torch.float32)+.99*(1-torch.tensor(done,dtype=torch.float32))*(f['q_target_next']-alpha.exp()*f['logp_next_resampled'])
            target=target.detach()
            for name in ('qf','qf_twin'):opts[name].zero_grad(set_to_none=True)
            loss=torch.nn.functional.huber_loss(f['qf_preds'],target)+torch.nn.functional.huber_loss(f['qf_twin_preds'],target)
            loss.backward()
            for name in ('qf','qf_twin'):opts[name].step()
            with torch.no_grad():
                for main,target_net in member.module.get_target_network_pairs():
                    for p,q in zip(main.parameters(),target_net.parameters()):q.lerp_(p,.005)
    member._capture_rng()
    if before!=digest(Actor(member.module).state_dict()) or not torch.equal(alpha,member.learner.curr_log_alpha[MID]):raise ValueError('Critic-only adaptation changed actor or alpha')
    return dict(steps=steps,actor_unchanged=True,alpha_unchanged=True,critic_loss=float(loss.detach()))

def distill(teacher,config,seed,steps=256,adapt_steps=256):
    if not 1<=steps<=256 or not 0<=adapt_steps<=256:raise ValueError('Bounded transfer required')
    original=SACMember.identity(teacher.state())
    student=SACMember(config,seed,method=teacher.method)
    ids=np.linspace(0,len(teacher.replay)-1,min(512,len(teacher.replay)),dtype=int)
    rows=[teacher.replay[i] for i in ids]
    obs=torch.tensor(np.asarray([r[0] for r in rows]),dtype=torch.float32)
    act=torch.tensor(np.asarray([r[1] for r in rows]),dtype=torch.float32)
    student._activate_rng();initial=fidelity(student,teacher,obs,act).detach().tolist()
    groups=[(student.module.pi_encoder,student.module.pi),(student.module.qf_encoder,student.module.qf),(student.module.qf_twin_encoder,student.module.qf_twin)]
    opts=[torch.optim.Adam([p for m in group for p in m.parameters()],lr=.001) for group in groups]
    best=sum(initial);best_state=deepcopy(student.module.state_dict())
    with charge(dict(distillation_updates=steps),'policy_value_gradient_distillation'):
        for step in range(steps):
            idx=torch.tensor(student.rng.integers(len(rows),size=BATCH))
            for opt in opts:opt.zero_grad(set_to_none=True)
            loss=fidelity(student,teacher,obs[idx],act[idx],True).sum()
            if not torch.isfinite(loss):raise ValueError('Nonfinite transfer loss')
            loss.backward()
            for opt in opts:opt.step()
            if step%16==15 or step==steps-1:
                v=float(fidelity(student,teacher,obs,act).detach().sum())
                if v<best:best=v;best_state=deepcopy(student.module.state_dict())
    student.module.load_state_dict(best_state)
    for main,target in student.module.get_target_network_pairs():target.load_state_dict(main.state_dict())
    for opt in student.optimizers().values():opt.state.clear()
    with torch.no_grad():student.learner.curr_log_alpha[MID].copy_(teacher.learner.curr_log_alpha[MID])
    student.replay=deepcopy(teacher.replay);student.transitions=teacher.transitions;student.updates=teacher.updates;student.distill_updates=teacher.distill_updates+steps
    student.learner.last_update_ts_by_mid.update(teacher.learner.last_update_ts_by_mid);student._capture_rng()
    after_imitation=fidelity(student,teacher,obs,act).detach().tolist()
    adaptation=critic_adapt(student,adapt_steps) if adapt_steps else None
    after_adaptation=fidelity(student,teacher,obs,act).detach().tolist()
    if original!=SACMember.identity(teacher.state()):raise ValueError('Teacher mutated')
    return student,dict(teacher_unchanged=True,initial=initial,after_imitation=after_imitation,after_adaptation=after_adaptation,
        metrics=['policy_KL','q1_MSE','q2_MSE','q1_gradient_MSE','q2_gradient_MSE','q1_action_difference_MSE','q2_action_difference_MSE'],
        steps=steps,adaptation=adaptation,gradient_components=3*steps+2*adapt_steps,
        target_policy='copy_distilled_online_then_critic_only_polyak',actor_release='shadow_candidate_only; measured donor/recipient gate before population replacement')
