# RL-LQR-09: scale actions first, then genuinely active states

Authorized: user accepts RL-LQR-08 as sufficient and requests5--10actions,
then10states, to identify an appropriate approach. This is a new bounded master
extension. Preserve all accepted core and RL-LQR-08 source/evidence.

## Scientific design and reviewed sequence

1. ENGINEERING: dimension-generic environment/reference, full PSD continuation
   critic, odd-mean/even-log-standard-deviation actor, export and exact checkpoint
   continuation. Verify terminal Q, action-nullspace gradient, oracle feasibility,
   independent condensed QP reference and covariance evaluation in all12cases.
2. ACTIONS: one state, each m in5,6,7,8,9,10. Dynamics x'=0.92x+sum(u)/sqrt(m)+w,
   stage cost x^2+0.1||u||^2. This preserves the predecessor optimum and effective
   control strength while increasing redundant dimensions.
3. REVIEW: audit paired action outcomes, freeze continuation without selecting on
   test paths. Record any implementation repair before new source admission.
4. STATES: ten physically active coupled states for each same m; A=0.8I+0.12cyclic
   shift, B=first m columns of I, Q=I,R=0.1I. This is the predecessor multi-action
   family extended to10controls, not nine irrelevant padded observations.
5. FREEZE: select one method per case by mean final validation regret across the
   two pilot seeds. Tie favors the simpler matrix method. All choices sealed
   before fresh confirmation. No human success threshold or favorable-only rows.
6. CONFIRM: three new paired training seeds for each12cases, both methods retained
   in this confirmation to measure whether symmetry replicates. Fixed endpoint;
   one fresh16384-path evaluation seed. No retuning from confirmation outcomes.
7. AUDIT: independently reconstruct references, scores, learning work, symmetry,
   exact greedy-controller diagnostics, all source snapshots and outcome claims.
   Publish result tables and limitations; final master reconciliation.

## Two methods, one controlled intervention

Both use unchanged RLlib SAC losses/entropy schedule/replay, actor/critic hidden
layers[32,32],rates0.001,8192transitions,1984SACupdates;batch128,warmup256,update
once per4transitions,tau0.005,initial alpha0.01,automatic entropy target -m.
Pilot curves at2048/4096/8192,4096validation paths,seed1090001.

Matrix: generalize the accepted known-dynamics critic to a full learned PSD matrix
P(t)=L(t)L(t)^T and scalar c(t): Q=-x^TQx-u^TRu+gamma[c-y^TPy-tr(PW)],y=Ax+Bu.
At the last step P=Qterminal,c=0 exactly. P,c are learned only from SAC targets;
no Riccati gains, optimal actions, analytical V labels or test paths enter training.
Bounded-action soft values need not be quadratic: this is an approximation and
fixture-specific model-informed adapter, not a universal SAC claim.

Symmetric: same critic and base actor weights, with Gaussian mean
mu(x,t)=[f_mu(x,t)-f_mu(-x,t)]/2 and logstd=[f_s(x,t)+f_s(-x,t)]/2.
Tanh preserves odd deterministic actions; entropy remains learned. Time is not
negated. This imposes the known sign symmetry of the benchmark, not optimal action
labels. Compare equal environment and gradient counts; extra forward cost recorded.

SAC reference: Haarnoja et al.,2018,arXiv1801.01290. Quadratic continuous-action
value parameterization precedent: Gu et al.,2016,arXiv1603.00748. This extension
keeps SAC and does not claim to implement NAF or its theoretical guarantees.

## Objective diagnostics and selection

Riccati plus independent condensed quadratic solve prove the reference. Propagate
all-sign robust action bounds to check that unconstrained optimum is feasible in
[-1,1]^m. Score mean nonnegative quadratic disadvantage plus exact optimal cost;
report relative gap, pathwise accounting and conditional standard errors.

For every final learned critic, derive the greedy linear controller from its
learned P(t), then compute robust action bounds and exact covariance expected cost
if feasible. This uses learned critics, not oracle gains. If infeasible, report
unsupported exact bounded cost, not an optimum claim. It is a frozen diagnostic
of actor versus critic errors and a separate deployment option; it is not neural
actor performance or additional SAC training. Both twin critics are reported
without selecting the better one from holdout.

Compare paired seeds, no5%training-population claims from onlythree confirmations.
Every outcome and final checkpoint retained. Fixed architecture isolates learning
before another HPO/NAS campaign; the predecessor found no BG-PBT advantage over
static search. No new broad joint-search allocation is implied by this extension.

## Frozen resource allocation

Four single-thread CPU workers plus coordinator;16GiB owned RSS,8GiB output cap,
8GiB free-disk floor;no GPU/network. Successful allocations consumed once.
Engineering at most4096transitions/1024SACupdates,600seconds.
ACTIONS:6cases*2methods*2seeds(10901,10902)=24runs;196608transitions/47616SAC;
2400seconds. STATES:24runs,seeds10911,10912,same budget;3600seconds.
CONFIRM:12cases*2methods*3seeds(10921--10923)=72runs;589824transitions/142848SAC;
7200seconds. Independent test paths seed1099001,16384per frozen endpoint.
Total scientific maximum983040transitions/238080SACupdates. This is a ceiling,
not a claim of wall time; earlier scalar operations suggest minutes per phase.
No transfer/distillation needed. Review/freeze/audit have zero training.

At boundaries repair demonstrated defects, refresh the next bounded phase and
continue authorized execution. If numerical/resource admission fails, retain the
attempt and repair before continuing; no recycled successful scientific runs.

## Pre-execution review

Changing both actuation and state count at once would confound the diagnosis;
sequential stages distinguish redundant-action growth from coupled-state learning.
For10states all coordinates enter reward and dynamics. Optima differ across action
counts there, so raw costs are accompanied by relative analytical regret. Full PSD
continuation can express cross-state effects; a diagonal-only critic cannot serve
as the sole test. Paired symmetry ablation changes only actor representation.
Analytic greedy diagnostics may reveal an actor optimization bottleneck, but are
labeled separately. Prior source, installed runtime and core qualification remain
unchanged. No optimality proof for neural training or global NAS is promised.
