# Scalar-state and redundant-action diagnostic results

RL-LQR-06: scalar1 (1state/1action), scalar3 (1state/3actions), padded3 (1relevant+9irrelevant observed states/3actions); horizon30.
Held-out cost estimates conditional on frozen policies. Analytical references are independently verified.

| Case | Exact optimum | Zero-action cost | Max oracle coordinate |
| --- | ---: | ---: | ---: |
| scalar1 | 0.286662585 | 1.620099849 | 0.420569545 |
| scalar3 | 0.286662585 | 1.620099849 | 0.242815940 |
| padded3 | 0.286662585 | 1.620099849 | 0.242815940 |

| Case | Seed | BG-PBT cost | Gap [normal 95% interval] | Improvement recovered | Static cost | Default cost |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| scalar1 | 10601 | 0.288935 | 0.002272 [0.002266, 0.002278] | 99.83% | 0.294233 | 0.294233 |
| scalar1 | 10602 | 0.287499 | 0.000837 [0.000830, 0.000843] | 99.94% | 0.287499 | 0.388789 |
| scalar1 | 10603 | 0.294135 | 0.007472 [0.007448, 0.007496] | 99.44% | 0.294135 | 0.294135 |
| scalar3 | 10601 | 0.309437 | 0.022774 [0.022722, 0.022826] | 98.29% | 0.323845 | 0.636033 |
| scalar3 | 10602 | 0.313048 | 0.026385 [0.026364, 0.026407] | 98.02% | 0.307044 | 1.668546 |
| scalar3 | 10603 | 0.961628 | 0.674965 [0.673924, 0.676005] | 49.38% | 1.160346 | 1.504126 |
| padded3 | 10601 | 1.811878 | 1.525215 [1.524525, 1.525906] | -14.38% | 0.623060 | 2.042551 |
| padded3 | 10602 | 0.341552 | 0.054890 [0.054569, 0.055210] | 95.88% | 0.316460 | 1.693919 |
| padded3 | 10603 | 0.633956 | 0.347293 [0.346992, 0.347594] | 73.96% | 0.476770 | 0.721643 |

## Aggregation across three optimizer seeds

| Case | Mean BG-PBT | Mean static | Mean default | Mean recovered | BG-PBT wins vs static |
| --- | ---: | ---: | ---: | ---: | ---: |
| scalar1 | 0.290190 | 0.291956 | 0.325719 | 99.74% | 1/3 |
| scalar3 | 0.528037 | 0.597078 | 1.269568 | 81.90% | 2/3 |
| padded3 | 0.929129 | 0.472097 | 1.486038 | 51.82% | 0/3 |

Arithmetic means describe these three seeds only. A win count or small test-path interval does not establish general method superiority.
Default uses a smaller total tuning budget; static search is the matched-work comparator.

## Selected lineages and paired comparisons

- Case scalar1, seed 10601: actor [11, 31, 61]; critics [25, 60, 41]; actor LR 1.03226914e-05; critic LR 0.00743054188. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar1/seed-10601/generation-c0-rung0.
  Paired BG-PBT minus baseline: -0.005298, normal95 [-0.005312, -0.005285].
  Paired BG-PBT minus default: -0.005298, normal95 [-0.005312, -0.005285].
- Case scalar1, seed 10602: actor [46, 59, 59, 61]; critics [26, 63, 53, 21]; actor LR 5.87051254e-05; critic LR 0.00117383869. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar1/seed-10602/population-r1-m3.
  Paired BG-PBT minus baseline: +0.000000, normal95 [+0.000000, +0.000000].
  Paired BG-PBT minus default: -0.101290, normal95 [-0.101497, -0.101082].
- Case scalar1, seed 10603: actor [32, 32]; critics [32, 32]; actor LR 0.001; critic LR 0.001. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar1/seed-10603/population-r3-m0.
  Paired BG-PBT minus baseline: +0.000000, normal95 [+0.000000, +0.000000].
  Paired BG-PBT minus default: +0.000000, normal95 [+0.000000, +0.000000].
- Case scalar3, seed 10601: actor [64, 9, 60, 41]; critics [31, 24, 36, 49]; actor LR 0.000904582455; critic LR 0.00286750444. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar3/seed-10601/population-r2-m3.
  Paired BG-PBT minus baseline: -0.014408, normal95 [-0.014465, -0.014352].
  Paired BG-PBT minus default: -0.326596, normal95 [-0.326929, -0.326263].
- Case scalar3, seed 10602: actor [20, 8, 34, 18]; critics [20, 13, 34, 38]; actor LR 0.000168101795; critic LR 0.000914846749. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar3/seed-10602/population-r2-m1.
  Paired BG-PBT minus baseline: +0.006004, normal95 [+0.005964, +0.006044].
  Paired BG-PBT minus default: -1.355499, normal95 [-1.355615, -1.355382].
- Case scalar3, seed 10603: actor [10, 29, 31, 17]; critics [53, 64, 33]; actor LR 1.77993505e-05; critic LR 0.0027466191. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-scalar3/seed-10603/population-r1-m3.
  Paired BG-PBT minus baseline: -0.198718, normal95 [-0.198841, -0.198595].
  Paired BG-PBT minus default: -0.542498, normal95 [-0.543456, -0.541540].
- Case padded3, seed 10601: actor [57, 64, 64, 20]; critics [20, 41, 30]; actor LR 0.000508394649; critic LR 0.000591076373. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-padded3/seed-10601/population-r3-m1.
  Paired BG-PBT minus baseline: +1.188818, normal95 [+1.184817, +1.192818].
  Paired BG-PBT minus default: -0.230673, normal95 [-0.233335, -0.228011].
- Case padded3, seed 10602: actor [26, 13]; critics [48, 24, 14, 34]; actor LR 0.000341232175; critic LR 0.00100845323. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-padded3/seed-10602/population-r3-m2.
  Paired BG-PBT minus baseline: +0.025092, normal95 [+0.024926, +0.025258].
  Paired BG-PBT minus default: -1.352367, normal95 [-1.355511, -1.349223].
- Case padded3, seed 10603: actor [10, 29, 31, 17]; critics [53, 64, 33]; actor LR 0.000713122875; critic LR 0.00287778818. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/case-padded3/seed-10603/population-r3-m3.
  Paired BG-PBT minus baseline: +0.157186, normal95 [+0.156236, +0.158136].
  Paired BG-PBT minus default: -0.087687, normal95 [-0.088440, -0.086934].

## Effective control versus redundant action

| Case | Seed | Effective-control gap | Nullspace effort gap | Total gap |
| --- | --- | ---: | ---: | ---: |
| scalar1 | 10601 | 0.002272266 | 0.000000000 | 0.002272266 |
| scalar1 | 10602 | 0.000836685 | 0.000000000 | 0.000836685 |
| scalar1 | 10603 | 0.007471950 | 0.000000000 | 0.007471950 |
| scalar3 | 10601 | 0.009671905 | 0.013102271 | 0.022774176 |
| scalar3 | 10602 | 0.011921337 | 0.014463887 | 0.026385225 |
| scalar3 | 10603 | 0.543520333 | 0.131444601 | 0.674964934 |
| padded3 | 10601 | 0.053600872 | 1.471614390 | 1.525215262 |
| padded3 | 10602 | 0.008485823 | 0.046403883 | 0.054889706 |
| padded3 | 10603 | 0.040851777 | 0.306441590 | 0.347293366 |

## Matched-case contrasts

Positive differences mean more BG-PBT regret in the first case. These are three paired optimizer-seed observations, not general causal estimates.
- Seed 10601: scalar3 minus scalar1: +0.020501910.
- Seed 10601: padded3 minus scalar3: +1.502441086.
- Seed 10602: scalar3 minus scalar1: +0.025548539.
- Seed 10602: padded3 minus scalar3: +0.028504482.
- Seed 10603: scalar3 minus scalar1: +0.667492984.
- Seed 10603: padded3 minus scalar3: -0.327671568.

Scalar3 failures would show that ten state dimensions are not necessary for a residual gap. Padded3 versus scalar3 tests irrelevant inputs, not the original coupled ten-state dynamics. Effective/nullspace terms describe lost cost, not its training cause.

## Work and scientific limits

- Sampled nonlinear-policy expectations; exact attainable analytical LQR reference only.
- Normal intervals describe test-path uncertainty conditional on each frozen policy, not optimizer randomness.
- Three optimizer seeds per case do not prove general superiority or reliable convergence.
- Selected architecture/rates belong to training lineages, not validated fresh static recipes.
- Equal transitions/component minibatches do not imply equal FLOPs or wall time.
- Default comparator reuses its static lineage and best validation checkpoint without additional training.
- Normalized actuation shares an optimum; scalar1/scalar3 have different feasible effective action ranges and entropy targets.

Actual training: 1,400,832 transitions, 347,328 SAC updates, 2,304 distillation updates.

Cost gaps are nonzero at the declared budget. This is not a convergence certificate, a global architecture optimum, or proof of universal BG-PBT superiority.

Evidence: docs/program/evidence/2026-10-28/rl-lqr-06/20261027T161254Z-study-1bde3ed3/study-result.json

