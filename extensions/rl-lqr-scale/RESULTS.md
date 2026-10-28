# RL-LQR-09: 5–10 actions, then 10 active states

Completed 28 October 2026. The requested dimensional extension is supported by fixed-budget pilots, fresh confirmation and independent reconstruction. The useful approach for these fixtures is a full matrix continuation critic using known dynamics and quadratic rewards, paired with a sign-symmetric SAC actor. Numerical results are empirical; the attainable analytical reference is independently checked.

## Confirmed neural-actor results

Each row averages three fresh training seeds. Every learner uses 8,192 transitions, 1,984 SAC updates and a fixed endpoint. Each frozen endpoint is evaluated on 16,384 fresh paths. The percentage is 100 times excess expected cost divided by the case-specific attainable Riccati optimum. The neural-policy expectation is estimated; the reference is analytical.

| States | Actions | Analytical optimum | Matrix critic + ordinary actor gap | Matrix critic + symmetric actor gap | Symmetric seed range |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 0.286662585 | 0.5285% | 0.0329% | 0.0064–0.0699% |
| 1 | 6 | 0.286662585 | 1.4728% | 0.0324% | 0.0055–0.0618% |
| 1 | 7 | 0.286662585 | 2.6750% | 0.0386% | 0.0186–0.0634% |
| 1 | 8 | 0.286662585 | 2.5162% | 0.0550% | 0.0275–0.1000% |
| 1 | 9 | 0.286662585 | 6.2299% | 0.0213% | 0.0140–0.0322% |
| 1 | 10 | 0.286662585 | 1.1180% | 0.0251% | 0.0144–0.0337% |
| 10 | 5 | 5.513247623 | 1.0153% | 0.9371% | 0.6820–1.1516% |
| 10 | 6 | 4.925009291 | 1.2318% | 0.9954% | 0.8498–1.2455% |
| 10 | 7 | 4.340798860 | 1.3576% | 1.1224% | 1.0862–1.1902% |
| 10 | 8 | 3.769376837 | 1.6144% | 1.6912% | 0.6609–2.9133% |
| 10 | 9 | 3.237842285 | 1.2902% | 1.0078% | 0.8147–1.1867% |
| 10 | 10 | 2.817047725 | 1.2270% | 0.3216% | 0.2879–0.3417% |

Symmetry reduces the mean gap in 11 of 12 cases and the gap in 32 of 36 paired seed comparisons. The exception is 10 states / 8 actions: the symmetric mean gap is 1.6912%, compared with 1.6144% for the ordinary actor. The symmetric seed range is 0.6609–2.9133%, so the unfavorable outcome and variability remain visible. Three seeds do not establish population-wide superiority.

The pilot selected symmetry in all 12 cases before confirmation. That selection is retained, including the eight-action exception; the test results are not used to switch methods or choose a favorable checkpoint.

## What the comparison establishes

In the one-state family, increasing redundant action coordinates from 5 to 10 retains the same effective control strength and analytical optimum. The symmetric actor remains within 0.0213–0.0550% mean excess cost, versus 0.5285–6.2299% for the ordinary actor under the same training counts. This supports using the known sign symmetry to prevent wasteful actor bias in this family.

In the ten-state family, all ten coordinates affect dynamics and cost. The full learned positive-semidefinite continuation matrix can represent cross-state effects. The symmetric actor has 0.3216–1.6912% mean gaps, with no monotone relation to action count. Dimension alone does not cause failure in this tested family; residual critic approximation and actor optimization error remain.

For a problem with exactly known linear dynamics and quadratic costs, the Riccati controller is already the reference solution. The learning experiment tests whether the SAC adapter can recover low cost without receiving optimal gains or value labels. It is not needed to calculate the known-answer solution.

## Separate learned-critic controller diagnostic

For each frozen twin critic separately, solve the positive-definite system (R + gamma B^T P_theta B) K = gamma B^T P_theta A and apply u = -Kx. These gains use learned matrices, not Riccati labels. This maximizes one learned quadratic critic; it need not maximize the minimum of both critics or the true value function.

Every confirmation controller passes the robust action-envelope check. The following values average both twins across three seeds, with no test-based twin selection. A covariance recurrence computes exact mathematical expected cost for these gains under the specified initial/noise law; this is distinct from the neural actor and is not a floating-point deployment certificate.

| States | Actions | Ordinary-actor training: greedy mean gap | Symmetric-actor training: greedy mean gap | Symmetric-actor training: worst twin gap |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 0.003309% | 0.003450% | 0.009283% |
| 1 | 6 | 0.001473% | 0.001273% | 0.004051% |
| 1 | 7 | 0.000277% | 0.000279% | 0.000615% |
| 1 | 8 | 0.000212% | 0.000311% | 0.001080% |
| 1 | 9 | 0.001272% | 0.001571% | 0.004299% |
| 1 | 10 | 0.000841% | 0.000906% | 0.002344% |
| 10 | 5 | 1.075580% | 1.187994% | 1.500028% |
| 10 | 6 | 1.190169% | 1.400777% | 1.992519% |
| 10 | 7 | 1.093968% | 1.133378% | 1.391741% |
| 10 | 8 | 1.329968% | 1.919228% | 3.808830% |
| 10 | 9 | 0.520960% | 0.857741% | 1.086132% |
| 10 | 10 | 0.006949% | 0.007386% | 0.010813% |

The scalar greedy gaps are much smaller than the neural gaps, isolating an actor optimization component. At 10 states / 10 actions, the symmetric neural mean gap is 0.3216%, while the learned-controller mean is 0.007386%. At 10 states / 5–8 actions, the learned-controller gap remains around 1–2%; simply replacing the actor does not remove the learned-value error.

## Model and controlled intervention

- Horizon 30, discount 0.99, actions in [-1,1], Q = I, R = 0.1 I and terminal Q = I.
- One state: A = 0.92 and B = ones(m) / sqrt(m). Redundant action directions add effort cost without extra effective control strength.
- Ten states: A = 0.8 I + 0.12 cyclic-shift, B = the first m identity columns. These are ten active coupled states, not padded observations.
- Independent initial coordinate signs have magnitude 0.5. Fresh scalar-sign noise multiplies an alternating-coordinate vector of magnitude 0.025. Noise covariance is rank one; initial covariance has full state rank.
- The critic uses known one-step dynamics/reward and a full learned P_theta(t) = L_theta(t) L_theta(t)^T. Nonterminal matrices and constants are learned through unchanged RLlib SAC targets; terminal continuation is known exactly.
- The symmetric Gaussian actor uses the odd part of its mean and the even part of its log standard deviation with respect to physical state; time is not reflected. Tanh preserves odd deterministic actions.
- Both methods use hidden layers [32,32], actor/critic learning rates 0.001, batch 128, warmup 256, one update per four transitions, tau 0.005, initial alpha 0.01 and automatic target entropy -m.
- Paired learners start with identical base actor parameters and random streams. Symmetry adds forward evaluations, so equal optimizer/environment counts do not imply equal FLOPs.

## Execution and independent audit

| Operation | Learners | Transitions | SAC updates | Wall seconds | Peak owned GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| actions | 24 | 196,608 | 47,616 | 181.07 | 4.855 |
| states | 24 | 196,608 | 47,616 | 212.09 | 5.042 |
| confirm | 72 | 589,824 | 142,848 | 584.34 | 5.213 |

Total scientific training: 983,040 transitions and 238,080 SAC updates across 120 learners; 16.29 minutes of operation wall time. Four single-thread CPU workers plus coordinator; no GPU allocation. Engineering checks are accounted separately: the failed first attempt used 2,688 transitions / 224 updates, and the passing attempt used 3,072 / 256. Resource ceilings were 16 GiB owned RSS and 8 GiB outputs.

Independent reconstruction verifies all 120 frozen endpoints, 240 learned controllers and 295 retained source snapshots. Riccati values agree with condensed quadratic solves and backward policy-value calculations. It also checks checkpoint counters, exported actor equivalence, symmetry, paired initial parameters, validation-only selection and exact work ledgers. The audit itself used zero training and completed in 70.41 seconds.

Engineering passed 25 tests. The final audit passed 15 controller, export, refusal, corrupted-score, changed-artifact and float64-replay controls. Two harness defects were repaired with failed evidence retained: the initial engineering test incorrectly demanded feasibility of arbitrary early learned gains; the first audit used float32 action squaring for direct costs instead of the scorer’s explicit float64 arithmetic. Neither repair changes scientific results or tolerances.

## Scope and remaining limits

- This is an optional model-informed SAC companion, not a general black-box RL result. Bounded-action soft values need not be quadratic.
- All 12 cases use one dynamics family, one horizon, the stated initial law and rank-one noise. Broader dynamics, disturbance ranks and deployment conditions are not qualified.
- Three fresh training seeds provide descriptive replication. Conditional rollout standard errors are separate from training-seed variability.
- No global neural optimum, generic SAC convergence or general optimizer superiority is proved.
- This stage holds architecture and learning-rate settings fixed. It performs no new BG-PBT or joint HPO/NAS comparison. The prior BG-PBT evidence remains source-specific.
- The accepted core source fingerprint is unchanged. Separate-machine testing remains waived; no external release is implied.

## Evidence and use

- [Companion guide](README.md)
- [Reviewed dimensional plan](../../docs/program/LQR_DIMENSION_SCALING_2026_10_28.md)
- [Evidence directory](../../docs/program/evidence/2026-10-28/rl-lqr-09/)
- [Master authority](../../CONSOLIDATED_MASTER_AUTHORITY.md)
- [Structured program register](../../docs/program/program.json)
