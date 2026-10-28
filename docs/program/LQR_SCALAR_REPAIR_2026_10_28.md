# RL-LQR-08: scalar learner and safe joint-search repair

Authorized by the user: review the program and execute. This successor implements
the dependency-ordered repairs from RL-LQR-07. Earlier source and results remain
immutable. Diagnosis completion was not learning repair completion.

## Reviewed sequence

1. CONTRACT: register this plan, source-bound operations and resource ceilings.
2. ENGINEERING: test exact last-step/nullspace identities and gradients, critic
   representation, unchanged plain learner continuation, transfer rejection and
   retained-population invariants. Replay all 18 historical replacement events.
3. LEARNER: fixed actor/critic hidden layers [32,32], rates 0.001, scalar3,
   horizon30. Compare plain SAC, a learned even concave quadratic critic, and an
   explicitly model-informed quadratic continuation critic. Same RLlib SAC
   objective, temperature, target schedule, replay and 8192 transitions each.
   Three paired seeds 10801--10803; checkpoints at 2048/4096/8192. No training
   uses Riccati values, optimal actions, or holdout observations.
4. REVIEW: freeze the validation-best eligible repair and the next stage from
   completed evidence. If no learned repair improves the plain learner on all
   three paired validation seeds, joint search is deferred, not declared fixed.
   Confirmation still evaluates the best prespecified repair and baseline.
5. HANDOFF: safe architecture transfer uses separate policy/value/action-gradient
   fidelity diagnostics, frozen-actor critic adaptation, donor continuation and
   incumbent comparison. Test on three retained pilot donors and two new shapes
   [16,16] and [32,32,32]. At most 256 imitation and 256 critic-only updates per
   child, then 1024 SAC transitions; donor continuation gets the same transitions.
   A failing child is discarded; failure is an outcome, never silently installed.
6. CONFIRM: three fresh paired training seeds 10811--10813, 8192 transitions per
   method, fixed endpoint (no best-checkpoint selection); independent evaluation
   seed1089001,16384paths. Compare the frozen repair with current plain SAC.
7. JOINT: only if fixed-learner validation gate passes, run three bounded joint
   procedures with protected incumbents, contemporary plain and matched static
   controls. Freeze the concrete allocation at REVIEW, before these seeds are
   consumed. No padded-state expansion in this repair.
8. AUDIT: independently reconstruct references, receipts, source hashes, training
   work, confirmation, transfer decisions and actual completeness. Publish all
   costs/gaps and unresolved limitations; reconcile the master.

## Representation interventions

Plain is the unmodified scalar RLlib SAC implementation. Quadratic replaces only
the critic representation with Q(x,u,t)=c(t)-||L(t)^T[x,u]||^2, learned from SAC
targets; lower-triangular L has positive diagonal. It assumes even quadratic,
concave value structure appropriate to this fixture, not general bank tasks.

Model-informed uses the known one-step dynamics and reward, plus learned
quadratic continuation V(y,t)=-p(t)y^2+c(t), p(t)>0. Terminal V=-y^2 is exact.
It enforces Q(x,project(u))-Q(x,u)=0.1||u_perp||^2 and terminal targets for every
parameter value. No Riccati coefficients enter training. This is an optional
structured adapter; its success cannot qualify generic black-box SAC.

Exact-Q actor optimization is a separate diagnostic control only: optimize the
same actor's deterministic action cost against known quadratic Q on a fixed
state/time design, without environment transitions. Its accounting, outputs and
claims remain separate from model-free learning and HPO/NAS. It tests the actor
optimizer/representation, not convergence of SAC. Maximum2048actor updates.

## Selection, uncertainty and objective evidence

Validation uses4096paths, seed1080001, common random paths across methods. Pilot
selection uses mean final validation regret across three seeds, ties in favor of
quadratic. No human acceptance threshold is used. Report full learning curves,
nullspace/effective regret, terminal error, critic action ranking/gradient error,
and zero-state actor bias. Three-seed comparisons are descriptive; even three
same-sign improvements cannot establish distribution-free significance at5%.
Confirmation reports every seed, paired differences and conditional rollout
standard errors. No finite experiment proves global NAS optimality.

Transfer release compares the candidate with both its recipient and the retained
donor on common validation paths. Strictly higher measured cost, nonfinite values
or absent evidence reject replacement; ties retain incumbent. This guarantees
nonworsening measured replacement only, not unseen-policy performance. Full
distribution and critic action-gradient discrepancies are recorded, not hidden
behind an arbitrary imitation count.

## Resources and phase boundaries

One inspector/editor. At most four one-thread CPU workers plus coordinator;
16GiB owned RSS,8GiB output,8GiB free-disk floor; no GPU/network required. Each
operation has a fixed timeout and append-only reservation ledger. Engineering
ceiling2048transitions/512SAC/128imitationupdates. Learner ceiling73728transitions/
17856SACupdates/2048diagnosticactorupdates. Handoff ceiling9216transitions/
2304SAC/1536imitation/1536critic-onlyupdates. Confirmation ceiling49152transitions/
11904SACupdates. Joint allocation is withheld until the reviewed learner gate.

At every boundary: retain the attempt, repair demonstrated implementation defects,
refresh the bounded next phase and continue authorized work. Scientific failure
does not authorize recycling successful allocations or modifying exposed results.
Failed engineering operations can be retried only with a recorded defect repair
and newly bound source. No broad campaign or global allow-rule changes.

## Review conclusions before execution

The baseline/current algorithm, learned structural hypothesis, model-informed
control and exact-Q actor diagnostic are distinct. Equal environment/SAC work
isolates critic representation; no rate/entropy changes are bundled into that
comparison. Architecture transfer comes after fixed-learner evidence. A gate
may explicitly defer joint tuning without treating the learning problem as
closed. Confirmation is prospective and cannot be used for choosing another
repair. Mathematical invariants replace subjective success thresholds; measured
regret and uncertainty replace claims of proven neural optimality.
