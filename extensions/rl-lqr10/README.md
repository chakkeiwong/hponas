# Ten-state, thirty-step joint SAC benchmark

Master stage: RL-LQR-04. The reviewed allocation and operations are recorded in
docs/program/LQR10_H30_STUDY_2026_10_27.md and docs/PROGRAM_OPERATIONS.md.
Predecessor five-state sources and evidence remain unchanged. This companion
uses the same upstream Ray RLlib SAC learner, conditional Bayesian population
search and training-replay distillation with dimension-specific adapters.

## Model

There are ten physical state variables and one continuous action bounded to
[-1,1]. The observation includes remaining time, hence eleven input features.
The finite horizon is thirty transitions, with discount 0.99. Dynamics are
A = 0.8 I + 0.12 C, where C is a cyclic shift, and B is the first coordinate.
State and terminal cost matrices are identity; action cost is 0.1 u squared.
Initial coordinates are independent signs times 0.5. Each transition has an
independent random sign multiplying 0.025 (1,-1,...,1,-1), so process noise has
rank one. This is an extension of the earlier model, not ten independent actions.

The attainable expected optimum is 7.8716918755290335; taking no action costs
8.714226728937764. Backward Riccati recursion, independent condensed quadratic
elimination and forward covariance propagation agree. Propagating coefficients
of every initial/noise sign proves the optimal action magnitude never exceeds
0.5993971764628899, below the action bound. No path enumeration is needed for
this feasibility proof or analytical expected cost.

## Joint tuning

Actor and critic architectures independently have 2--4 hidden layers, each
width 8--64. The two Q critics share the architecture specification, not weights.
Actor and critic learning rates are independently continuous in [1e-5,1e-2],
searched on a log scale. Hidden activations are tanh. SAC uses batch 128,
warmup 256 transitions, replay capacity 32768, one update per four transitions,
target coefficient 0.005 and automatic entropy tuning with initial alpha 0.01.

Three complete procedures use seeds 10301, 10302 and 10303. Within each pair,
population and static random search start with identical four configurations
and training seeds. Four main segments each contain 4096 transitions per member.
Every proposed architecture receives distillation followed by actual SAC before
selection; the best trained checkpoint is retained. Both methods receive 77824
transitions per pair and equal component-gradient minibatch counts. This does
not imply equal FLOPs or wall time. Final rates describe a transfer lineage,
not a newly validated recipe trained from scratch.

## Evaluation

The complete initial/noise law has 2^40 paths. Nonlinear neural policies are
therefore evaluated by sampling, not described as exact expectations.
For each policy trajectory we compute discounted squared deviations from the
Riccati action, weighted by the quadratic action curvature. Its expectation is
exactly the expected cost minus the analytical optimum. Adding the sampled mean
deviation to the exact optimum gives a variance-reduced cost estimate.

Selection uses 1024 fixed IID validation paths, seed 1030001. All six winners
are frozen before evaluating 16384 separate IID test paths, seed 1030002.
Common test paths enable paired differences. Standard errors and normal 95%
intervals measure test-path uncertainty conditional on a frozen policy. They
are approximate intervals, not finite-sample guarantees or optimizer-seed
reliability bounds. No zero-gap or convergence claim follows from executing
the experiment successfully.

Every path also checks the quadratic telescoping identity with its realized
noise martingale. A small nonlinear-policy fixture independently enumerates its
whole law and verifies equality of direct expected cost and analytical cost
plus expected regret. The study saves direct rollout means and per-time-step
regret alongside its principal estimator.

## Execution and recovery

The runner uses two single-thread CPU workers and a coordinator, source-bound
manifests, explicit work reservations, time/RSS/output limits and a disk floor.
Each task commits actor and full training checkpoint hashes. Completed work
replays without training; uncertain interrupted intent refuses automatic reuse.
The operation runner requires the correct active master stage and rejects a
repeat of a successful allocation. GPU sharing was separately verified by
RL-LQR-03; this experiment measures learning on CPU and does not measure speedup.

See RESULTS.md and results-index.json for the completed outcome and exact
evidence bindings once the study and reconstruction audit finish.
