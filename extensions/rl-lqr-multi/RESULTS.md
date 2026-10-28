# Ten-state multi-action tuning results

RL-LQR-05: action dimensions 2, 3, 4, 5; ten physical states; horizon thirty.
Held-out cost estimates conditional on frozen policies. Analytical references are independently verified.

| Actions | Exact optimum | Zero-action cost | Max oracle coordinate |
| --- | ---: | ---: | ---: |
| 2 | 7.281976239 | 8.714226729 | 0.595901063 |
| 3 | 6.692270921 | 8.714226729 | 0.595788058 |
| 4 | 6.102620834 | 8.714226729 | 0.595354906 |
| 5 | 5.513247623 | 8.714226729 | 0.594128361 |

| Actions | Seed | BG-PBT cost | Gap [normal 95% interval] | Improvement recovered | Static cost | Default cost |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| 2 | 10501 | 7.425161 | 0.143185 [0.142275, 0.144095] | 90.00% | 7.425161 | 51.339679 |
| 2 | 10502 | 7.502580 | 0.220603 [0.218350, 0.222856] | 84.60% | 7.641416 | 16.076238 |
| 2 | 10503 | 7.388790 | 0.106814 [0.106027, 0.107601] | 92.54% | 7.367886 | 19.931931 |
| 3 | 10501 | 7.256505 | 0.564234 [0.560854, 0.567614] | 72.09% | 7.266911 | 15.998104 |
| 3 | 10502 | 8.084012 | 1.391741 [1.386591, 1.396890] | 31.17% | 7.921079 | 33.346292 |
| 3 | 10503 | 6.925308 | 0.233038 [0.230472, 0.235603] | 88.47% | 6.981745 | 33.265886 |
| 4 | 10501 | 6.343343 | 0.240722 [0.239735, 0.241709] | 90.78% | 7.126111 | 83.027984 |
| 4 | 10502 | 8.897146 | 2.794525 [2.776034, 2.813017] | -7.00% | 10.408047 | 44.721574 |
| 4 | 10503 | 6.322349 | 0.219728 [0.218695, 0.220761] | 91.59% | 6.635735 | 46.881081 |
| 5 | 10501 | 6.104204 | 0.590956 [0.588774, 0.593138] | 81.54% | 8.848434 | 54.548875 |
| 5 | 10502 | 7.238611 | 1.725364 [1.715813, 1.734915] | 46.10% | 13.913813 | 16.837443 |
| 5 | 10503 | 6.206429 | 0.693181 [0.689099, 0.697263] | 78.34% | 6.011710 | 21.843122 |

## Aggregation across three optimizer seeds

| Actions | Mean BG-PBT | Mean static | Mean default | Mean recovered | BG-PBT wins vs static |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 | 7.438844 | 7.478155 | 29.115949 | 89.05% | 1/3 |
| 3 | 7.421942 | 7.389912 | 27.536761 | 63.91% | 2/3 |
| 4 | 7.187613 | 8.056631 | 58.210213 | 58.45% | 3/3 |
| 5 | 6.516414 | 9.591319 | 31.076480 | 68.66% | 2/3 |

Arithmetic means describe these three seeds only. A win count or small test-path interval does not establish general method superiority.
Default uses a smaller total tuning budget; static search is the matched-work comparator.

## Selected lineages and paired comparisons

- Actions 2, seed 10501: actor [45, 8, 56, 15]; critics [32, 41, 62]; actor LR 0.00543244504; critic LR 0.00276303534. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-2/seed-10501/population-r3-m3.
  Paired BG-PBT minus baseline: +0.000000, normal95 [+0.000000, +0.000000].
  Paired BG-PBT minus default: -43.914518, normal95 [-44.013837, -43.815199].
- Actions 2, seed 10502: actor [9, 58, 33, 36]; critics [23, 39]; actor LR 6.12131662e-05; critic LR 0.00482994478. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-2/seed-10502/population-r3-m2.
  Paired BG-PBT minus baseline: -0.138836, normal95 [-0.140382, -0.137291].
  Paired BG-PBT minus default: -8.573658, normal95 [-8.593740, -8.553577].
- Actions 2, seed 10503: actor [30, 53, 42, 47]; critics [50, 36]; actor LR 6.76856652e-05; critic LR 0.000921187616. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-2/seed-10503/population-r3-m0.
  Paired BG-PBT minus baseline: +0.020904, normal95 [+0.020024, +0.021783].
  Paired BG-PBT minus default: -12.543141, normal95 [-12.560659, -12.525622].
- Actions 3, seed 10501: actor [45, 8, 56, 15]; critics [32, 41, 62]; actor LR 0.000966040515; critic LR 0.000491344886. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-3/seed-10501/population-r3-m2.
  Paired BG-PBT minus baseline: -0.010406, normal95 [-0.014404, -0.006408].
  Paired BG-PBT minus default: -8.741599, normal95 [-8.766892, -8.716306].
- Actions 3, seed 10502: actor [8, 20]; critics [18, 17, 63]; actor LR 8.65119539e-05; critic LR 0.000263455315. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-3/seed-10502/population-r3-m2.
  Paired BG-PBT minus baseline: +0.162932, normal95 [+0.155503, +0.170361].
  Paired BG-PBT minus default: -25.262280, normal95 [-25.289819, -25.234741].
- Actions 3, seed 10503: actor [63, 48, 23]; critics [45, 38, 50, 62]; actor LR 0.000295197832; critic LR 0.00440408513. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-3/seed-10503/population-r3-m0.
  Paired BG-PBT minus baseline: -0.056437, normal95 [-0.060406, -0.052468].
  Paired BG-PBT minus default: -26.340578, normal95 [-26.354727, -26.326428].
- Actions 4, seed 10501: actor [55, 61, 50]; critics [37, 30, 8]; actor LR 2.00432861e-05; critic LR 0.00435743491. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-4/seed-10501/population-r3-m2.
  Paired BG-PBT minus baseline: -0.782768, normal95 [-0.785829, -0.779706].
  Paired BG-PBT minus default: -76.684641, normal95 [-76.749643, -76.619640].
- Actions 4, seed 10502: actor [29, 20, 53, 9]; critics [47, 10, 62, 9]; actor LR 1.93524087e-05; critic LR 7.70471344e-05. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-4/seed-10502/population-r3-m2.
  Paired BG-PBT minus baseline: -1.510901, normal95 [-1.534655, -1.487147].
  Paired BG-PBT minus default: -35.824428, normal95 [-35.855107, -35.793748].
- Actions 4, seed 10503: actor [55, 53, 46]; critics [19, 28, 59]; actor LR 1.30145879e-05; critic LR 0.0072397245. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-4/seed-10503/population-r3-m3.
  Paired BG-PBT minus baseline: -0.313387, normal95 [-0.316601, -0.310172].
  Paired BG-PBT minus default: -40.558733, normal95 [-40.662501, -40.454964].
- Actions 5, seed 10501: actor [55, 61, 50]; critics [37, 30, 8]; actor LR 1.64635515e-05; critic LR 0.00457849798. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-5/seed-10501/population-r3-m2.
  Paired BG-PBT minus baseline: -2.744231, normal95 [-2.755507, -2.732954].
  Paired BG-PBT minus default: -48.444671, normal95 [-48.485528, -48.403815].
- Actions 5, seed 10502: actor [18, 55]; critics [57, 46, 28, 62]; actor LR 1.11141857e-05; critic LR 5.25355188e-05. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-5/seed-10502/population-r3-m1.
  Paired BG-PBT minus baseline: -6.675202, normal95 [-6.699566, -6.650837].
  Paired BG-PBT minus default: -9.598832, normal95 [-9.625923, -9.571740].
- Actions 5, seed 10503: actor [30, 53, 42, 47]; critics [50, 36]; actor LR 1.20364025e-05; critic LR 0.00518021865. Selected checkpoint: /home/ubuntu/workspace/hponas/docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/actions-5/seed-10503/population-r3-m1.
  Paired BG-PBT minus baseline: +0.194718, normal95 [+0.193347, +0.196089].
  Paired BG-PBT minus default: -15.636694, normal95 [-15.672641, -15.600746].

## Work and scientific limits

- Sampled nonlinear-policy expectations; exact attainable analytical LQR reference only.
- Normal intervals describe test-path uncertainty conditional on each frozen policy, not optimizer randomness.
- Three optimizer seeds per dimension do not prove general superiority or reliable convergence.
- Selected architecture/rates belong to training lineages, not validated fresh static recipes.
- Equal transitions/component minibatches do not imply equal FLOPs or wall time.
- Default comparator reuses its static lineage and best validation checkpoint without additional training.
- Adjacent input columns and rank-one process noise are a fixed model family, not all multi-input systems.

Actual training: 1,867,776 transitions, 463,104 SAC updates, 3,072 distillation updates.

Cost gaps are nonzero at the declared budget. This is not a convergence certificate, a global architecture optimum, or proof of universal BG-PBT superiority.

Evidence: docs/program/evidence/2026-10-27/rl-lqr-05/20261027T152612Z-study-b3ae2c5c/study-result.json

