# RL-LQR-03: trained-checkpoint attribution repair

The procedure review found an exact-cost tie between a trained donor and its
zero-update compatible copy. Lexicographic task selection chose `copy-r2`,
whose changed learning rates had not yet acted on the saved weights. The
policy cost is unchanged, but presenting those rates as the trained winner
misattributes the evidence. This is a reporting defect, not a reason to repeat
the completed training allocation.

The successor selection requires actual SAC work in the candidate task. Preserve
the original schema-2 reports and all checkpoints. Independently reconstruct the
lowest-cost trained candidate; if the old winner was a zero-update copy, require
identical cost and exported actor tensors before correcting its provenance.
Any change in objective value is a repair failure requiring investigation, not
silent reselection. Write new schema-3 reports bound to the original reports.
Retain the full training lineage: final rates are not asserted to describe
training a static configuration from scratch.

Register SELECTION-RECONCILIATION after PROCEDURE-CHECK. Its reviewed operation
runs focused zero-training regressions, checks all three original procedures,
publishes corrected source-bound reports and rejects an untrained copy falsely
labeled as a trained selection. It has zero transitions, zero SAC/distillation
updates, 600 seconds, three CPU cores and 16 GiB owned RSS. HARDWARE-DOCUMENTATION
and AUDIT depend on this correction; GPU execution remains independent.

This phase-boundary repair is part of RL-LQR-03 and does not change the scientific
objective, seed roster, work budgets, cost results or hypothesis after exposure.
