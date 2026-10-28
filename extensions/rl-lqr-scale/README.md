# Dimensional LQR/SAC companion

This optional companion generalizes RL-LQR-08 to one or ten physical states and
5–10 continuous controls, horizon 30. Its purpose is to find an effective learning
representation before another joint HPO/NAS search. The accepted core package and
predecessor evidence are unchanged.

## Approach

Use exact structure where it is part of the stated problem; learn the remaining
value function. For y=Ax+Bu, the critic is

    Q_theta(x,u,t) = -x^T Q x - u^T R u
                       + gamma [c_theta(t)-y^T P_theta(t)y-w^T P_theta(t)w].

P_theta=L_theta L_theta^T is a full positive-semidefinite matrix. The network sees
remaining time and outputs a lower-triangular factor plus scalar c. Terminal
continuation is the known terminal reward. Nonterminal coefficients learn through
RLlib SAC targets; no Riccati solution enters training. Known dynamics/quadratic
reward are explicit fixture assumptions, not facts about arbitrary bank tasks.

The symmetric neural actor uses the same base parameters but takes the odd part
of the Gaussian mean network and even part of its log standard deviation. This
ensures zero mean action at zero state, preserves time direction and does not
hard-code an optimal gain. The matrix-only control uses the original actor form.

## Two controller outputs

1. Neural actor: deterministic SAC action tanh(mu_theta(x,t)). Its test cost is
   estimated on fresh paths using exact nonnegative quadratic disadvantage.
2. Learned-critic greedy controller, for either twin separately:

       K_theta(t) = [R+gamma B^T P_theta(t)B]^{-1} gamma B^T P_theta(t)A,
       u = -K_theta(t)x.

Positive R makes the small solve unique. It maximizes that individual learned
quadratic Q, not necessarily the true optimal Q or minimum of both critics. No
favorable twin is selected from test outcomes.

LearnedController.from_member(member,critic="q1") constructs gains from learned
parameters. Its certificate() computes robust action bounds and exact
real-arithmetic expected cost under the specified law when bounds are feasible.
Calling controller(states,time) refuses out-of-bound actions; it does not silently
clip. torch_module() exports a linear actor only after the initial/noise action
envelope passes. The module takes physical states followed by remaining-time
fraction; arbitrary external inputs are outside its certification.

The exact cost uses covariance recurrence. This separates actor optimization
error from inaccurate value coefficients without more training. It does not prove
that the neural policy is globally optimal; nonzero cost gaps stay visible.

## Families and protocol

One state: A=0.92,B=ones(m)/sqrt(m),Q=1,R=0.1I. The optimum is invariant in m;
the m−1 redundant action directions can only add effort cost.
Ten states: A=0.8I+0.12cyclic shift,B=first m identity columns,Q=I,R=0.1I.
All states affect dynamics and cost. Actuation changes the optimum, so use each
case's relative analytical regret.

Initial coordinates are independent signs of magnitude 0.5. Fresh symmetric-sign
noise has alternating-coordinate amplitude 0.025. Gamma 0.99, horizon 30, actions [-1,1].
The Riccati oracle is admitted only after an all-sign bound proves feasibility.

The study fixes actor/critic hidden layers [32,32], learning rates 0.001, 8,192 transitions and
1,984 SAC updates per learner. Equal updates do not imply equal FLOPs: symmetry adds
forwards. No HPO/NAS optimum is claimed. Prior protected BG-PBT did not improve
on matched static search; this extension isolates the learner first.

## Reproducibility

SACMember accepts the predecessor architecture/rate dictionary plus case="s10a10"
and method="symmetric" or "matrix". Save/restore includes replay, RNG, optimizer,
targets and clocks. Package/examples have no sibling repository dependencies.
The runtime is the existing reviewed RLlib/PyTorch environment.

Use exact RL-LQR-09 commands in docs/PROGRAM_OPERATIONS.md. Successful scientific
allocations cannot repeat. Inspect results or restore trusted checkpoints for
zero-training analysis; extra training needs a successor bounded allocation.

## Interpretation

Quadratic continuation is an approximation to bounded-action soft values. Sign
symmetry is structural; achieved training accuracy is empirical. Three fresh seeds
show replication, not a distribution-free 5% superiority certificate. Conditional
rollout errors and training-seed variability differ. Exact controller cost applies
to mathematical gains and the specified law, not arbitrary floating-point bank
deployment. See RESULTS.md and RL-LQR-09 evidence for all numerical outcomes.

## Execution record

The master stage is RL-LQR-09. The reviewed sequence is engineering, scalar
5–10-action pilot, continuation review, coupled ten-state pilot, selection freeze,
fresh paired confirmation, independent audit and final master reconciliation.
See the [bounded plan](../../docs/program/LQR_DIMENSION_SCALING_2026_10_28.md),
[registered operations](../../docs/PROGRAM_OPERATIONS.md) and
[master authority](../../CONSOLIDATED_MASTER_AUTHORITY.md).

Four one-thread CPU workers execute the independent learners. Each method/case
has two pilot seeds and three fresh confirmation seeds. Confirmation holds the
8,192-transition endpoint fixed and evaluates 16,384 fresh paths. Both methods
remain in the record even though the pilot selects one. Scientific allocations
cannot be repeated through the fixed runner after a successful receipt.
