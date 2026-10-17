# Workload scope and phase contracts

The supported Tier-0 workload is real Brax PPO with moderate architecture
coordinates. `workloads/rl_routine.py` constructs width/depth-dependent networks
and passes activation to the PPO network factory. The maintained
`examples/v14_day_one_walk.py` varies learning rate, width, depth and activation;
it fixes the remaining training settings. The scope does not promise that every
illustrative knob in the older NAS example is implemented. Optimizer selection,
dropout, weight decay and schedules are not currently exposed by this workload.

The search objective is the mean return on the recipe's search-evaluation
episodes, maximized. Search observations include measured elapsed cost,
configuration, training/search seeds, policy checkpoint, recipe and learning
curve. Fidelity scales `RLSettings.max_timesteps`; a call starts fresh training
and charges all of it. There is no optimizer-state resume contract or live
executor `reporter` argument. Stored curves do not supply live median pruning.

The example uses `RLSettings.smoke()` on inverted pendulum with one search
trial and a separate protected evaluation after search. V14 is its bounded
integration gate. V04-T0/V05 use the adopted named Ant/HalfCheetah/Hopper 100k
recipes, equal task weights, fixed budgets and independent vector streams.
The suite was exposed during development; the claim is conditional on that
named suite and uses prospective protected evaluation, not an unobserved task
population. Actual pilot/confirmation allocation and acceptance remain open.

Search never accepts a protected `test_seed`. `evaluate_checkpoint` is a
separate post-selection operation; it refuses overlap with training/search
evaluation seeds. Campaign orchestration binds recipes, checkpoints, source,
phase, every scheduled slot and the disjoint seed namespaces. The protected
rank evidence cannot certify mean-return superiority or another workload.

| Retained obligation | Phase owner and objective closure |
|---|---|
| Tier-0 real PPO and architecture axes | WL-00: documented executable contract, architecture/protected-seed regressions and current V14 integration; PPO-01 separately owns statistical comparison. |
| Routine RL with live ASHA/median and real fidelity accounting | T1-MF: connect real progress/control/checkpoint semantics, declare restart versus resume, verify measured costs, then V06 quality/cost and default consequence. |
| Broad routine-RL method recommendation | WL-01/T3-01: retained task/seed exposure and owned DEHB V07 evidence; no general claim from the Tier-0 named suite. |
| Large-parallel RL and architecture transfer | WL-01/T2-POP: both resource regimes, PBT/PB2-Mix/BG-PBT dependencies, architecture/checkpoint compatibility, distillation and V08. |
| Neural-transport sampler | WL-01: actual learned transport, inner-adaptation contract and V13 correctness/vetoes; existing ordinary HMC remains a diagnostic. |
| Hamiltonian network | WL-01/T1-MO: prediction, rollout stability and conservation objectives, fidelity/veto gates, held-out task and the V09/V10 family. |
| Finance | WL-01: no current supported template or capability claim. Retain a later explicit project/task/data/acceptance disposition before implementation or release; absence of a project is not a scientific success or silent deletion. |
| Distributed production use | OPS-01: multi-node fault, hard-budget, backup/restore, monitoring and security evidence before broad deployment. |

Every later supported template must bind a search schema, objective, fidelity
and measured cost, immutable task/seed specification, held-out evaluation and
maintained example. A planned template is not shipped support. These phase
assignments preserve the complete product obligations without treating an
endpoint PPO demo as acceptance of all workload families.
