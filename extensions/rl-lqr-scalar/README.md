# Scalar-state, three-action diagnosis

RL-LQR-06 asks whether a large state representation is necessary for the
SAC tuning gaps seen in RL-LQR-05. It freezes three matched diagnostic cases:

| Case | Cost-relevant states | Observed physical states | Actions | Actor inputs incl. time |
| --- | ---: | ---: | ---: | ---: |
| scalar1 | 1 | 1 | 1 | 2 |
| scalar3 | 1 | 1 | 3 | 2 |
| padded3 | 1 | 10 | 3 | 11 |

## Three actions with one state
The active dynamics are x_next=.92*x+(u1+...+um)/sqrt(m)+w.
The stage cost is x^2+.1*sum(u_i^2). Gamma=.99, horizon30,
initial x is a sign times .5, noise is a fresh sign times .025,
and each action is in [-1,1]. The padded case adds nine stable observed
coordinates which cannot affect x or any cost. The active initial/noise
sampling is exactly paired across cases. Nuisance observations supply no
additional predictive information given the active state and time.

Define b=ones(m)/sqrt(m), effective action v=b*u, and residual action
u_perp=u-b*v. For three actuators, u_perp has two independent directions
which affect effort cost but cannot change the state. Its stage cost is
.1*||u_perp||^2. The optimal policy sets u_perp=0 and divides the scalar
control equally among the three actuators. Both one-action and three-action
oracles satisfy their bounds; their exact cost is the same, 0.286662585467451.
Zero action costs1.620099849071693 in all three cases.

The action network is the SAC actor. It takes state/time and emits m means
plus m log standard deviations, then uses tanh-squashed Gaussian samples for
training or tanh(mean) for deterministic evaluation. The twin critics see
state/time and the m-vector action. BG-PBT jointly selects 2--4 hidden layers,
8--64 units each, and separate log-continuous actor/critic rates1e-5--1e-2.
Changing case is a contract change; cross-case checkpoints/replay/transfer
are refused. Architecture changes within a case receive training-replay
actor/twin-critic distillation followed by actual SAC training.

## What this comparison identifies
Scalar3 versus scalar1 tests redundant-action coordination in a normalized
scalar plant. The feasible effective-action ranges and automatic entropy
target differ, so this is not a pure entropy-controlled parameter-count test.
Padded3 versus scalar3 preserves the entire cost-relevant plant/action model
and adds irrelevant state observations. Their actual training trajectories
can differ because the policies and network initializations differ. It tests
sensitivity to nuisance observations and representation size at this budget.
The original ten-state example has ten coupled cost-relevant states and is
not equivalent to padding. These experiments cannot attribute all original
failures to state dimension, or show that more neurons alone would repair them.

All selected-policy excess cost is decomposed into effective-control regret
and nullspace effort, with a pathwise equality and independent reference
checks. This identifies where cost is lost, not the optimizer's causal failure
mechanism. No oracle control enters SAC training or distillation.

## Execution and results
The master stage is RL-LQR-06. Exact bounded commands are listed in
../../docs/PROGRAM_OPERATIONS.md. Three paired procedure seeds per case use
a shared reviewed budget. All nine selections freeze before the separate
16,384-path holdout evaluation. The comparator is equal-work static search;
the default comparator uses just its one-member lineage and less total work.
The uncertainty intervals concern test paths conditional on fixed policies,
not optimizer-seed variability. See RESULTS.md for every outcome, decomposition
and selected architecture. No fixed numerical tolerance turns these measured
neural-policy gaps into optimality or convergence certificates.

The successful study allocation cannot be repeated; reconstruction uses saved
source-bound artifacts without retraining. Prior RL-LQR evidence and qualified
core source are preserved. Separate-machine testing remains waived.
