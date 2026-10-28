# RL-LQR-01: known-answer RL and joint actor/critic tuning

Authorized by the user's 27 October 2026 instruction to review the proposed
RL-LQR-01 plan thoroughly and execute it. This is an additive application
extension of master revision 2.646, not a reinterpretation of its finite-MDP
BG-PBT results. The accepted core source and all consumed evidence stay bound
to their original identities. One inspector/editor owns this execution.

## Reviewed design

Use the installed Ray 2.58.0 PyTorch SAC implementation, with an isolated local
overlay for its missing RLlib dependencies. MacroFinance supplies read-only
interface context; no sibling imports, data, paths or services enter execution.
MushroomRL's public LQR equations and solver API informed the design; the new
environment and independent reference are written here, without a MushroomRL
runtime dependency. TensorFlow is not required by this extension.

The finite-horizon fully observed scalar system is
`x[t+1] = 0.8*x[t] + u[t] + w[t]`, `u in [-1,1]`, with independent equiprobable
`x[0] in {-1,1}` and `w[t] in {-0.05,0.05}`, horizon 8, discount 0.99,
stage cost `x*x + 0.1*u*u`, and terminal cost `x[8]*x[8]`.
The observation includes remaining time. The terminal cost is included once
in the last reward, multiplied by the discount. There is no state clipping.
This is discrete time with continuous states/actions, not discrete actions.

Backward Riccati recursion has an independent exact rational reference. The
analytic controller is feasible along every reachable oracle path, so its
unconstrained lower bound is attained for this bounded-action problem too.
Enumerate all 512 initial-state/noise paths for every frozen deterministic
policy. This removes evaluation sampling error; it does not remove neural
training randomness or floating-point error. Verify the performance-difference
identity `J(policy)-J(optimal) = E sum gamma^t S[t]*(u[t]+K[t]*x[t])^2`.
Use floating-point tolerances for numerical identities only, derived from
machine precision, horizon and magnitudes; do not invent a learning-success
percentage or tune a threshold to the result.

SAC retains its standard entropy-regularized training loss. HPO minimizes the
unregularized expected cost of its deterministic inference policy. These are
explicitly different objectives. The Riccati optimum is a benchmark for the
delivered controller, not a claim about the SAC soft critic's optimum.

Independent actor and twin-critic architectures are built through an RLlib
catalog adapter. Search the full Cartesian product of actor shapes `[16]` or
`[32,32]`, critic shapes `[32]` or `[64,64]`, and two learning-rate recipes
`(actor=0.0003, critic=0.001)` or `(actor=0.001, critic=0.003)`.
Each architecture gets both hyperparameter recipes, fresh model/optimizer
state and the same prospective training budgets. This is an exhaustive small
joint search through HPO-NAS Study, not architecture selection followed by
one reused optimizer setting. It establishes the best observed candidate
within this roster, not a global optimum over architectures/hyperparameters.

Two fixed training seeds per candidate (1101, 1102); the selected configuration
is frozen before two fresh training seeds (2101, 2102). Both phases enumerate
the same complete known distribution: seed separation concerns training
randomness, not fictitious held-out dynamics. Report every result, exact
benchmark gap and zero-action comparison. No statistical superiority claim
over optimizers, random seeds or other environments is allocated.

## Sequence and completion evidence

1. **REVIEW:** Register this plan, source lineage, limitations and operation
   bounds; review objective alignment, time limits, resource ownership and
   failure preservation before training.
2. **RUNTIME:** Install only the four missing RLlib dependency families into
   `.hponas-runtime/rl-lqr-deps`, retaining wheel hashes and exact versions;
   verify imports without changing the base environment.
3. **ORACLE:** Implement dynamics, rational/numerical Riccati references,
   enumerated scoring and numerical checks. Test terminal discounting, seed
   behavior, action refusal, oracle feasibility, cost lower bound and the
   performance-difference identity, including negative controls.
4. **LEARNER:** Implement independent actor/critic networks around standard
   RLlib SAC. Verify actual optimizer updates, twin/target critics, finite
   parameters, deterministic inference, checkpoint restore and resumed
   learning. Smoke allocation: at most two fits of 512 transitions each.
5. **JOINT:** Execute eight configurations, two tuning seeds each, then two
   fresh final fits of the selected configuration. Each fit gets exactly 4,096
   transitions. Use two CPU workers, durable Study state and complete path
   evaluation. Verify completed Study resume does not train again.
6. **HARDWARE:** Run two independent 512-transition SAC fits concurrently on
   two distinct GPUs with HPO-NAS ResourceExecutor. Retain actual device/PID/
   interval evidence, nonzero gradient updates and complete path scores.
   This tests parallel SAC workloads, not BG-PBT/SAC architecture distillation.
7. **DOCUMENTATION:** Publish the runnable example, installation recipe,
   mathematical assumptions and actual outcomes in a versioned LaTeX manual.
8. **AUDIT:** Reconstruct source/runtime identities, all raw scores and the
   frozen selection; check stage completeness and explicit limitations.
   GAP-01/FINAL-AUDIT remains the final master phase and includes this audit.

At each boundary retain failures, repair demonstrated implementation defects,
refresh only the next bounded plan and continue. A weak learned policy is a
scientific outcome, not permission to increase the search budget. A failed
engineering allocation gets a separately reviewed successor; no automatic
retry or silent budget extension.

## Bounds and approvals

At most four CPU cores (two learning workers, one numerical thread each), two
GPUs only for the hardware phase, 16 GiB aggregate owned host RSS, 2 GiB new
outputs, and a 4 GiB free-disk floor. Runtime installation: 600 seconds,
250 MiB wheel cap. Oracle tests: 300 seconds. Learner: 600 seconds. Joint
study: 3,600 seconds, 73,728 transitions total. Hardware: 600 seconds, 1,024
transitions. Documentation and final audit: 600 seconds each. The learner
smoke adds at most 1,024 transitions; total training allocation is 75,776.

Fixed commands and exact rosters live in docs/PROGRAM_OPERATIONS.md. Each
operation binds its runner and extension inputs, owns its descendants, records
progress/exit/cleanup and refuses an already successful training allocation.
Network permission is limited to fetching the missing Python wheels; local
sockets/GPU permission is requested through the managed tool layer if needed.
No global rules, protected configuration, history, release or deployment edits.

## Review findings and dispositions

* Infinite-horizon Riccati versus truncated rewards: resolved by finite-horizon
  recursion and explicitly discounted terminal cost.
* Unconstrained oracle versus squashed actions: resolved by checking analytic
  feasibility on every oracle path; violating policies are refused, not clipped.
* Stochastic evaluation cost: resolved by a bounded discrete noise law and
  full enumeration; do not mislabel the example Gaussian LQG.
* Entropy mismatch: explicitly score the delivered deterministic controller;
  retain standard SAC learning without claiming its loss equals LQR cost.
* Shared-width architecture search: replace with independent actor/critic
  construction and test tensor shapes and parameter independence.
* Optimizer transfer across shapes: each joint-search candidate starts fresh.
  BG-PBT/SAC replay and cross-shape distillation remain unsupported, explicitly
  outside this first LQR integration. Existing BG-PBT claims are unchanged.
* Reusing exposed evaluation as independent confirmation: the entire dynamics
  law is known. Fresh training seeds assess retraining only; no held-out-data
  or population-generalization language is permitted.
* Scope/qualification drift: implement an optional companion under
  extensions/rl-lqr with its own tests and source binding. Any demonstrated
  core defect requires a separate source-impact review before a core edit.

Review verdict: executable as a bounded integration and joint-search example,
with objective engineering checks and numerical optimality-gap measurement.
No empirical learning success is assumed in advance.

## Execution amendments (27 October 2026)

The original 18-fit scientific roster is fully consumed and is not repeated.
Its selected configuration failed to beat zero action on both fresh training
seeds. Completed Study replay is verified in a separate zero-training operation;
the original wrapper failure came from an eager executor context in the test.

The first two-GPU attempt completed 1,024 transitions but its short learning
intervals did not overlap. The reviewed hardware successor adds a two-worker
ready barrier after construction and CUDA synchronization around timing. It
repeats only the two 512-transition engineering fits, adding 1,024 transitions;
the aggregate bound is therefore **76,800**, with the original **75,776** retained
as the initial allocation. Its observed learning overlap is 2.104343 seconds.
This repairs the hardware harness and does not alter learning criteria or the
scientific search. Review: evidence/2026-10-27/rl-lqr-01/hardware-successor-review.md.

The companion uses a deterministic tanh(mean) distribution adapter because the
installed Ray 2.58.0 conversion returns the unsquashed location. Standard SAC
stochastic training behavior is unchanged. Recovery explicitly supplements
replay, its RNG and standalone temperature; future environment trajectory
identity is not certified. All failed attempts and consumed input snapshots
remain immutable. Final audits reconstruct all 24 fit segments, including the
failed hardware pair, and reconcile GAP-01/FINAL-AUDIT last.
