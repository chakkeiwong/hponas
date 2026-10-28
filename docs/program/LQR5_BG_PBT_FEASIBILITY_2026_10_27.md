# RL-LQR-02: five-state joint search definition and BG-PBT readiness

The user requested five LQR states, actor and critic networks with two through
four layers, eight through 64 neurons, and continuous learning rates, and asked
whether BG-PBT can handle this problem. This successor implements and verifies
that benchmark and search definition and gives a source-based capability
assessment. It does not allocate a population training campaign or claim that
the existing finite-MDP BG-PBT implementation supports RLlib SAC. RL-LQR-01 and
its unfavorable fresh-training results remain immutable.

## Concrete interpretation

* Five coupled state coordinates, one continuous action retained from RL-LQR-01,
  horizon eight and discount 0.99. Observation is the five states plus remaining
  time. An input/state coordinate is not a hidden layer.
* Each actor and each critic has exactly 2, 3 or 4 hidden layers. Every active
  layer has its own integer width from 8 through 64 inclusive. The two critics
  have the same architecture specification but independent weights and targets.
  The encoder/head split must not multiply the requested hidden-layer count.
* Actor and critic Adam learning rates are independent continuous numbers in
  [1e-5, 1e-2], represented and sampled on a logarithmic scale. This is a
  prospective engineering search range, not a proven optimal range. Temperature
  learning rate, tanh activation and the other SAC controls are fixed.
* Joint configurations include both architectures and both rates. Inactive
  widths are absent, not additional search dimensions. The possible architecture
  count is (57^2 + 57^3 + 57^4)^2; this is not an exhaustive-run allocation.

## Known-answer five-state problem

Let C be the cyclic permutation matrix, A = 0.8 I + 0.12 C, B = e1,
Q = Q_terminal = I, R = 0.1, and |u| <= 1. Dynamics are
x_next = A x + B u + w. Initial coordinates are independent equiprobable
plus/minus 0.5. Each time has one independent binary innovation, with
w = plus/minus 0.025 (1,-1,1,-1,1). The initial covariance is full rank;
instantaneous innovation covariance is rank one. The coupled dynamics and
single actuator are controllable. This choice retains 2^(5+8) = 8192 paths
instead of pretending that independent noise in five coordinates is free to
enumerate. General full-rank process noise would need a different evaluation
contract; it is not silently approximated by this one.

Minimize E[sum(t=0..7) gamma^t (x_t' Q x_t + R u_t^2)
+ gamma^8 x_8' Q_terminal x_8]. Matrix Riccati recursion supplies a lower
bound; complete oracle-path feasibility establishes attainability under the
action bound. Independently condense the deterministic finite-horizon quadratic
control problem and eliminate its action vector to check each Riccati matrix.
Check the expected-cost/performance-difference identity on the complete law.
Numerical tolerances concern floating-point reconstruction only. No learning
success threshold is set by human acceptance. SAC still trains its standard
entropy-regularized loss; the tuning score is deterministic unregularized cost.

## Source-based BG-PBT assessment

BG-PBT's method is appropriate for discrete architecture choices coupled to
continuous learning-rate schedules. The current public LocalBGPBT implementation
does not accept this task:

1. hponas/bg_pbt.py and population.py require the finite-MDP objective interface
   and shared CoordinateMLP policy/value state, not SAC actor/twin-critic state.
2. That architecture uses one shared width and depth; the explicit architecture
   proposal pool is limited to 32 entries. It cannot represent this requested
   full conditional actor/critic space as a complete finite pool.
3. BGPopulationExplorer has one continuous learning-rate coordinate plus
   categorical SGD momentum, with LocalBGPBT fixing its default range. SAC
   requires two independent Adam-rate coordinates in this design.
4. ArchitectureGeneration distills finite discrete-action policy/value outputs.
   Continuous Gaussian-policy distillation, twin soft-Q functions, target state,
   replay, temperature and Adam state need an explicit SAC transfer contract.
5. AdapterPopulation is model-neutral PBT over a finite exploration roster. It
   does not automatically supply Bayesian generational search or SAC transfer.
6. Existing ResourceExecutor CPU/GPU infrastructure is reusable, but previous
   two-GPU SAC fits and finite-MDP BG-PBT tests do not qualify this combination.

## Implementation sequence needed for an actual BG-PBT/SAC run

These are specific remaining capabilities, not delivered features or an active
scientific allocation. A subsequent execution instruction should register them
as stages, with source-bound bounded manifests before dispatch:

1. SAC population adapter: persistent train/evaluate/checkpoint operations;
   same-shape exploit copies actor, both critics and targets, all Adam states,
   replay and temperature, then explicitly changes the two rate schedules.
   Test restoration and continuation using actual learner counters and tensors.
2. Conditional Bayesian search: independent actor/critic depth and per-layer
   widths, canonical inactive dimensions, two log-rate dimensions, contextual
   temporal GP/trust regions within generations and architecture proposals
   between generations. Reuse the temporal kernel only within its verified
   dimension/observation envelope. A sampled proposal batch is not the domain.
3. Changed-shape transfer: freeze the teacher; use recorded training-only
   states/actions to distill its Gaussian policy and both soft-Q outputs into
   fresh networks; reset incompatible Adam state and target critics explicitly.
   Preserve replay only under the identical environment/role contract. Charge
   distillation separately. Never load mismatched tensor or optimizer shapes.
4. Engineering validation: force both compatible exploit and changed-shape
   transfer, verify teachers remain unchanged, continuous proposals are not a
   fixed grid, cost/transition/update accounting includes every attempt, and
   crash/replay cannot duplicate committed training. Verify actual CPU overlap
   before a separately bounded two-idle-GPU check.
5. Learning calibration then frozen search: first diagnose the predecessor's
   64-update poor-learning result on learning curves; prospectively choose a
   common finite training budget from calibration. Reserve fresh confirmation
   seeds before selection. Freeze the complete selected lineage/schedule and
   specify whether confirmation replays that lineage or tests a final static
   configuration; these are different estimands. Report exact Riccati gaps,
   all failures, retraining variation and equal-work baseline comparisons.
6. Documentation and independent final audit: reconstruct architecture shapes,
   proposals, transfers, learning work, exact scores and selected schedule.
   Any run can establish empirical performance only, not global NAS optimality.

## Reviewed execution for this request

REVIEW -> PREFLIGHT -> AUDIT -> GAP-01/FINAL-AUDIT. The preflight builds real
RLlib modules and verifies the matrix oracle, Gym environment, conditional
SearchSpace, continuous rates, literal layer counts, twin independence and
unsupported LocalBGPBT refusal. No Ray cluster or optimizer training is started.
The separate audit binds and replays the preflight result and source closure;
the last master stage reconciles the original qualification and this limited
capability assessment without asserting population support.

One inspector/editor. Operations use one CPU, one numerical thread, no GPU,
no network, at most 300 seconds each, 8 GiB owned RSS, 128 MiB outputs and a
4 GiB free-disk floor. Fixed commands live in docs/PROGRAM_OPERATIONS.md.
All prior source/evidence is retained. New work lives in extensions/rl-lqr5;
accepted core code is unchanged. Scientific training allocation is zero.

Review verdict: the requested benchmark/search definition is executable as a
bounded no-training preflight. An end-to-end BG-PBT claim is blocked by the
specific adapter/search/transfer implementation gaps above, not by the size of
these neural networks or a lack of hardware. This assessment is the answer to
the user's capability question, not a completion claim for that future work.
