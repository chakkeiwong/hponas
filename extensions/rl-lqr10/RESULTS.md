# Ten-state, thirty-step results

RL-LQR-04: three paired joint SAC architecture/rate tuning procedures.
The following are held-out sample estimates conditional on frozen policies, not exact neural-policy costs.

Analytical optimum: **7.871691875529**. Zero action: **8.714226728938**.
Certified maximum oracle action: 0.599397176463, below the bound 1.

| Search seed | BG-PBT cost | BG-PBT gap (normal 95% interval) | Static cost | Paired difference |
| --- | ---: | --- | ---: | ---: |
| 10301 | 7.900158 | 0.028466 [0.028104, 0.028828] | 7.909589 | -0.009431 |
| 10302 | 7.902047 | 0.030355 [0.029839, 0.030871] | 7.902047 | +0.000000 |
| 10303 | 7.995667 | 0.123975 [0.122082, 0.125868] | 8.051174 | -0.055507 |

Negative paired differences favor BG-PBT. Intervals are approximate test-path uncertainty; they do not include training-seed uncertainty.

Mean paired difference: -0.021646; sign-randomization diagnostic p=0.50. Three pairs do not establish general superiority.

## Selected training lineages

- Seed 10301: actor [47, 9]; critic [38, 55, 35, 24]; actor rate 2.53154794e-05; critic rate 0.000660193553. Recovers 96.62% of the available improvement over no action.
- Seed 10302: actor [40, 60]; critic [21, 47, 58, 12]; actor rate 2.32809948e-05; critic rate 0.00812984668. Recovers 96.40% of the available improvement over no action.
- Seed 10303: actor [61, 18, 23]; critic [33, 28]; actor rate 0.000273685202; critic rate 0.01. Recovers 85.29% of the available improvement over no action.

## Limits and work

- Sampled nonlinear-policy expectations; exact analytical LQR reference only.
- Normal intervals describe finite test-path uncertainty conditional on each frozen policy.
- Three optimizer seeds do not prove general superiority or reliable convergence.
- Selected architecture/rates belong to training lineages, not validated fresh static recipes.
- Equal transitions/component minibatches do not imply equal FLOPs or wall time.

Study work: 466,944 transitions, 115,776 SAC updates, 768 distillation updates.

The run is complete at the declared budget. Reaching a small gap does not establish stable convergence, zero error or global HPO/NAS optimality.

Source and data: docs/program/evidence/2026-10-27/rl-lqr-04/20261027T142542Z-study-22923d3e/study-result.json
