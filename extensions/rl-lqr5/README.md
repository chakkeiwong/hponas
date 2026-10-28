# Five-state LQR: joint architecture and continuous-rate definition

This successor implements a coupled five-state, one-action LQR environment and
the requested SAC search space. It is a **no-training preflight**, not a completed
BG-PBT/SAC run. The current LocalBGPBT implementation is specific to a shared
finite-MDP policy/value model. The required SAC adapter, Bayesian conditional
architecture proposals and cross-architecture distillation are specified in
[the reviewed master addition](../../docs/program/LQR5_BG_PBT_FEASIBILITY_2026_10_27.md).

Both actor and critic have **2, 3 or 4 actual hidden layers**; every layer has an
independent integer width from **8 through 64**. Actor and critic learning rates
are independent continuous values from **1e-5 through 1e-2**, sampled on a log
scale. Twin critics have independent weights and the same selected architecture.
There are 10,744,443 architectures per network and 115,443,055,380,249 pairs.
No exhaustive search is proposed. Tanh activations and temperature-learning
rate are fixed; the continuous learning-rate range is a prospective design
choice, not a proven best range.

The actor has six inputs (five states and time), 2–4 hidden layers and two
Gaussian distribution outputs. Each critic concatenates state/time/action into
seven inputs, has 2–4 hidden layers and one scalar output. Actor plus twin critics
range from 436 to 39,172 neural parameters; including target critics the range
is 726 to 65,286, plus SAC's separate temperature scalar.

The known dynamics use A = 0.8 I + 0.12 C (C is a cyclic permutation), B = e1,
identity state/terminal cost, action cost 0.1, discount 0.99, horizon eight and
|u| <= 1. Initial coordinates are independent plus/minus 0.5; each transition
has an independent sign multiplying 0.025 (1,-1,1,-1,1). This is an explicitly
rank-one process innovation and a full-rank initial-state distribution. All
8,192 paths can be evaluated without Monte Carlo estimation. Matrix Riccati
recursion and independent block quadratic elimination check the reference;
oracle action feasibility is checked over the entire finite law.

The outer objective is expected unregularized cost of the deterministic trained
controller. SAC's inner training objective includes entropy. No claim equates
its soft critics to a Riccati value function, or proves global NAS optimality.
The previous scalar example's poor fresh-seed results remain unchanged.

Use the runtime in `../rl-lqr/runtime-lock.json`, HPO-NAS and this directory on
Python's import path. The following creates a configuration only:

```python
import numpy as np
from hponas_rl_lqr5.reference import oracle_report
from hponas_rl_lqr5.search import search_space, decode, capability_report
from hponas_rl_lqr5.catalog import sac_config

print(oracle_report())
row = search_space().sample_config(np.random.default_rng(73))
joint_configuration = decode(row)
algorithm_configuration = sac_config(joint_configuration, seed=1101)
print(capability_report())  # current_local_bgpbt_sac_supported = False
```

These interfaces do not launch Ray or train. `FiniteLQR5Env` is Gymnasium
compatible; `enumerate_policy(policy)` scores a policy taking `(states, step)`
and returning an `(N, 1)` action array. The policy sees no future disturbances.
`LiteralSACCatalog` ensures encoder/head splitting does not duplicate hidden
layers. Invalid dimensions, inactive width coordinates and infeasible actions
are refused explicitly. Training budgets require calibration before a run;
the scalar example's 64 optimizer updates are not a convergence criterion.

Exact reviewed verification commands appear in `docs/PROGRAM_OPERATIONS.md`.
Preflight builds real RLlib modules, tests numerical references, conditional
coordinates, rates and targets, and saves source-bound evidence. No CPU/GPU
population execution, transfer or learning claim follows from those checks.
