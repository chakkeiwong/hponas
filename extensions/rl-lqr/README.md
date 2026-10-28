# Known-answer LQR and joint SAC tuning

This optional example connects HPO-NAS Study and ResourceExecutor to standard
PyTorch RLlib SAC. Actor and twin-critic architectures vary independently; each
network pair receives both learning-rate recipes and starts with fresh optimizer
state. It imports no sibling repository code, data, environments or services.

The bounded run verifies integration and measures learning quality. It **did not
produce a reliably good controller**. The selected configuration's tuning mean
cost was 1.699976; two fresh retrainings cost 13.049656 and 3.265531. The no-action
cost is 2.725760, and the attainable Riccati optimum is 1.078527. All results are
retained. Neither neural convergence nor global HPO/NAS optimality is claimed.

## Model and objective

Discrete time, continuous action: `x_next = .8*x + u + w`, `u ∈ [-1,1]`.
Initial state is equally likely -1 or +1; each disturbance is independently
-0.05 or +0.05. The eight-step cost is
`E[sum(t=0..7) .99^t*(x[t]^2+.1*u[t]^2) + .99^8*x[8]^2]`.
Observation is `[x, remaining_steps/8]`. No state or action clipping occurs in
the environment. The actor emits a bounded squashed Gaussian action; deterministic
evaluation uses tanh(mean). This is not a discrete-action or Gaussian LQG example.

Backward finite-horizon Riccati recursion is cross-checked against an independent
rational calculation and SciPy's discounted infinite-horizon limit. The oracle
uses at most 0.730304 action magnitude on all reachable paths, proving its
unconstrained lower bound is attainable under the action constraint. Every saved
deterministic actor is scored on all **512** paths. The performance-difference
identity checks the exact expected gap up to floating-point arithmetic.

SAC trains its usual entropy-regularized loss. Selection scores the deterministic
controller's unregularized cost. These objectives differ; the critic is a soft
action-value network, not a fitted Riccati value-function certificate.

## Runtime and execution

The tested base runtime is Python 3.13, Ray 2.58.0, Torch 2.13.0+cu130,
NumPy 2.5.2 and SciPy 1.18.1. The isolated overlay pins Gymnasium 1.2.2,
farama-notifications 0.0.4, lz4 4.4.5 and ormsgpack 1.13.0. Exact wheel and file
identities are in `runtime-lock.json`. TensorFlow and MacroFinance are not needed.
The core HPO-NAS package need not use Ray; this optional learner uses RLlib/Ray.

The reviewed checkout operations are listed in `docs/PROGRAM_OPERATIONS.md`:
`rl_lqr_ops.py oracle`, `learner`, `joint`, `joint-replay`, `hardware`, `build`,
`audit`, and `master-audit`, using the exact absolute paths in that runbook.
They require the registered stage, reviewed manifests and owned output directory.
Training allocations cannot silently repeat. The retained completed Study replay
runs with an objective that always refuses calls and verifies no workers start.

For reuse in a Python program, install HPO-NAS and the listed RLlib dependencies,
then add this `extensions/rl-lqr` directory to Python's import path. Public entry
points are `FiniteLQREnv`, `reference.oracle_report`, `reference.enumerate_policy`,
and `experiment.fit`, `experiment.declaration`, `experiment.roster`. Example:

```python
from hponas_rl_lqr.reference import oracle_report
from hponas_rl_lqr.environment import FiniteLQREnv

print(oracle_report())                   # no learning or GPU required
env = FiniteLQREnv()
observation, info = env.reset(seed=7)
```

For a separately allocated fit, `fit(roster()[0], seed, new_output_directory,
transitions=4096)` owns a one-CPU Ray instance and returns exact cost, gap,
measured transition/update counts and artifacts. `use_gpu=True` uses the one GPU
assigned to that worker. The surrounding ResourceExecutor sets CPU/thread/GPU
visibility before importing the workload. Use a fresh destination. A standalone
caller owns resource limits; the registered runner supplies time/RSS/disk guards.

## Search contract and actual outcomes

Eight configurations: actor coordinate `[16]` or `[32,32]`, critic coordinate
`[32]` or `[64,64]`, paired learning rates `(0.0003,0.001)` or `(0.001,0.003)`.
These are architecture **coordinates**, not literal full-network layer lists:
the actor uses its coordinate in both encoder and head; each critic uses its
coordinate for observation/action streams, fusion and scalar-value head.
Twin critics and target copies have separate parameters. The structural tests
verify every coordinate combination and independence.

Each candidate trains 4,096 transitions (64 minibatch updates per optimizer,
batch size 64, replay capacity 1,024, training intensity 1.0, initial temperature
0.01, gamma 0.99, tau 0.005). Tuning seeds are 1101/1102; final seeds 2101/2102
are trained only after the configuration is durably frozen. Both phases evaluate
the same fully known law; fresh seeds test retraining, not held-out dynamics.

| Actor coordinate | Critic coordinate | LR recipe | Mean tuning cost |
|---|---|---|---:|
| [16] | [32] | 0 | 2.529902 |
| [16] | [32] | 1 | **1.699976** |
| [16] | [64,64] | 0 | 4.029705 |
| [16] | [64,64] | 1 | 5.146045 |
| [32,32] | [32] | 0 | 10.548371 |
| [32,32] | [32] | 1 | 38.232926 |
| [32,32] | [64,64] | 0 | 9.849207 |
| [32,32] | [64,64] | 1 | 4.199699 |

The selected actor [16], critic [32], recipe 1 has final mean **8.157594**.
The finite roster minimum is an observed minimum over these seeds and budgets;
it does not establish an expected-seed, global architecture or control optimum.
Sixty-four updates is a small learning budget. Its poor result is recorded,
not repaired by increasing training until a favorable score appears.

## Recovery, parallelism and artifacts

Every fit saves a standalone TorchScript `actor.pt`, all path states/actions/
costs, optimizer counts, learning-device/PID/time evidence and a full checkpoint.
RLlib's new-stack checkpoint is supplemented with replay, replay RNG and SAC's
standalone temperature. The smoke verifies matching model/target/optimizer/
temperature/replay identities and continued updates from 8 to 16. Exact future
environment trajectories and GPU bitwise reproduction are not claimed.

Completed CPU fits overlap on two assigned cores. GPU verification uses two
physical GPU UUIDs, one visible local cuda:0 per worker and a ready barrier before
timed learning; measured overlap is 2.104343 seconds. The first GPU attempt's nonoverlapping training intervals are
retained as a failure. Its repaired successor adds 1,024 transitions, making
**76,800 total measured transitions**, including all engineering attempts.

`results-index.json` binds the retained operation receipts. The audit independently
replays each actor and cost, exact finite selection, work ledger, checkpoint Adam
counts and CPU/GPU intervals. False score, noise, action, selection, freeze and
hardware controls must fail. Historical failed attempts remain available.

This extends standard SAC integration. **BG-PBT/SAC cross-architecture replay,
distillation and population transfer are unsupported.** The existing finite-MDP
BG-PBT qualification remains separate. No economic effectiveness, speedup,
multi-machine reliability or production claim is made.
