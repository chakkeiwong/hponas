# RL-LQR-08 scalar repair results

The reviewed repair sequence was executed end to end. The one-state/three-action learner failure is substantially reduced by structure-aware critics. Generic black-box SAC remains unresolved.

## Controlled learner comparison

| Critic | Mean pilot cost | Mean excess cost |
| --- | ---: | ---: |
| plain | 2.405756558 | 2.119093972 |
| quadratic | 0.294680138 | 0.008017552 |
| informed | 0.291656319 | 0.004993734 |

Same actor initialization, rates 0.001, [32,32] hidden layers,8,192 transitions and1,984 SAC updates per seed; seeds 10801–10803. The representation intervention is prospective; no Riccati labels enter SAC training. Quadratic is a learned even concave form. Informed analytically factors known reward/dynamics/terminal cost with a learned continuation value. Both change representational assumptions; neither qualifies all bank tasks.

The exact-Q actor diagnostic reaches cost 0.28702558961202257 using 2,048 actor-only updates. This demonstrates actor capacity on a fixed diagnostic design, not successful SAC learning.

## Fresh fixed-learner confirmation

| Seed | Plain SAC | Informed repair | Repair gap / optimum |
| --- | ---: | ---: | ---: |
| 10811 | 0.682831579 | 0.287041864 | 0.1323% |
| 10812 | 3.264182656 | 0.289633048 | 1.0362% |
| 10813 | 1.111944837 | 0.288787454 | 0.7412% |

Fixed endpoint,8,192 transitions each, 16,384 fresh paths seed 1089001. All three repaired runs improve; three same-sign results have a one-sided sign-test probability 1/8 under equal chance, so this is not 5% distribution-free training-seed significance. Path standard errors are conditional on each frozen policy. Exact attainable optimum: 0.2866625854674511.

## Architecture transfer and population protection

Two architectures across three donors: 2/6 children pass comparison with recipient and donor continuation. Failed children are retained as evidence and excluded from population replacement. Policy KL, both value errors, action-difference errors and gradients are recorded separately; critic-only adaptation freezes actor and temperature. This demonstrates safe refusal, not universal transfer fidelity. The child is trained in an isolated trial after critic adaptation; no numerical gradient-fidelity threshold certifies safe actor release. Population entry is guarded by measured objective performance.

## Matched joint HPO/NAS

| Seed | Repaired BG-PBT | Repaired static | Plain protected BG-PBT | BG-PBT gap / optimum |
| --- | ---: | ---: | ---: | ---: |
| 10821 | 0.288166586 | 0.287021340 | 0.335784624 | 0.5247% |
| 10822 | 0.288435025 | 0.288435025 | 0.392714196 | 0.6183% |
| 10823 | 0.287534242 | 0.287216671 | 0.434681084 | 0.3041% |

Per method per seed: 20,480 transitions and 20,992 gradient-component minibatches. Three initial members, three rounds, continuous actor/critic rates and 2–4 hidden layers with 8–64 neurons. For the informed critic, the network learns the time-dependent continuation, while the action dependence follows known dynamics. Dynamic methods use 4,928 SAC + 256 imitation + 256 critic-only updates; static uses 5,248 SAC updates. These are matched work units, not equal parameter FLOPs or time. All winners are sealed before 16,384-path evaluation on seed 1089002. Contemporary plain BG-PBT uses the same protections, isolating the critic representation from scheduler differences.

Static search beats repaired BG-PBT in two seeds and ties in one. All 12 architecture replacement attempts across the repaired and plain joint procedures are rejected; the 6 compatible-copy replacements are accepted. The tied seed selects the same shared initial lineage. This is expected under historical-best selection and does not imply the search explored every configuration. No architecture-transfer benefit or BG-PBT superiority is established.

## What remains unresolved

- Structured critic uses LQR assumptions and known dynamics/reward; not generic SAC qualification.
- Three training seeds provide descriptive replication; no population-level superiority certificate.
- Fixed policies have nonzero sampled regret; no proof of neural or NAS global optimality.
- Protected replacement is nonworsening on measured validation only.
- Transfer still rejects unsuccessful children; universal shape-transfer fidelity is not established.
- Larger/padded states and production bank tasks are not qualified by this scalar repair.

## Audit and operation evidence

Independent audit verifies 396 retained source bindings, all operation ledgers, exact references, 15 fixed endpoints, 6 handoff children and 9 joint winners. Every training allocation is consumed once. One pre-dispatch operation-name collision and one audit rollout-order mismatch were repaired without repeating training; both records are retained. Accepted core fingerprint is unchanged. Full results/receipts: docs/program/evidence/2026-10-28/rl-lqr-08.

Scientific allocations total 316,416 environment transitions, 77,376 SAC updates, 3,072 imitation updates, 3,072 critic-only updates, and a separate 2,048 exact-Q diagnostic actor updates. The four scientific operations took about 356 seconds combined, with less than 5 GiB peak owned RSS. Engineering adds 1,472 transitions, 112 SAC, 8 imitation and 16 critic-only updates. Source/data preparation and audits are separate from these run times.
