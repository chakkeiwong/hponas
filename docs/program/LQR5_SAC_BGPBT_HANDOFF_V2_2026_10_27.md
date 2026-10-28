# RL-LQR-03 phase-boundary review and executable resumption, revision 2

Engineering, calibration, search, fresh static confirmation, independent CPU
reconstruction and documentation have completed. This is a bounded companion,
not a change to the finite-MDP core. The original plan and every consumed source
snapshot remain immutable. This addendum repairs the final dependency ordering
without changing scientific controls, search results, confirmation or budgets.

The two-GPU stage is blocked by actual host occupancy. Its first attempt failed
to access NVIDIA devices inside the sandbox. The reviewed runner was then
approved for host execution; its second attempt found no qualifying pair and
started zero GPU training. No other workload was interrupted. CPU results:

* 13 engineering tests, including full four-member population transfer and
  generation, exact CPU continuation, concurrent CPU workers and controller
  replay with no extra training.
* Two calibration curves chose 8192 transitions under the prospective rule.
* Four-member BG-PBT and the matched-work static baseline each used 32768
  transitions and 32224 component-gradient minibatches. Both selected actor
  [33,12], critic [51,19,46], rates 0.00009408476690611556 and
  0.009674325292107868. The best evolved policy cost was 3.26019051519261.
* Reserved fresh seeds 801/802/803 produced costs 3.261398291296962,
  3.2579831460879007 and 3.264331394691683 for both methods. Mean
  3.261237610692182 is about 0.220% above the attainable optimum
  3.2540811593967556. These are measured finite-task suboptimality gaps;
  neither global NAS optimality nor BG-PBT superiority is established.
* The separate CPU reconstruction checked 42 saved tasks, actual exported-actor
  scores against independent condensed matrices, checkpoints, proposals,
  selection, transfer and work. Four false-evidence controls were rejected.
  The full 162-page manual built with resolved references.

All attempts, including failed engineering attempts, charged 144736 sampler
transitions, 33992 SAC updates and 528 distillation updates. The scientific
calibration/search/confirmation subset used 131072 transitions, 31864 SAC
updates and 160 distillation updates. No scientific run remains active.
The current evidence index binds each completed phase.

## Reviewed remaining dependency chain

`HARDWARE -> HARDWARE-DOCUMENTATION -> AUDIT -> GAP-01/FINAL-AUDIT`.
The hardware documentation successor also depends on the completed CPU manual.
The final audit depends on all prior stages. It must not accept the current CPU
manual's historical GPU-blocker statement as current after hardware succeeds.
Therefore the successor rebuilds the full manual with the qualified GPU result,
using zero new training. This is a repair/refresh within the existing master
delivery obligation, not a new scientific direction or allocation.

To resume, inspect host GPU availability read-only. When two GPUs have no
compute processes and utilization at most10%, reactivate RL-LQR-03/HARDWARE,
bind a fresh version of its bounded manifest to the current reviewed runner,
input index and unchanged scientific source, and invoke the exact hardware
command in `docs/PROGRAM_OPERATIONS.md`. Do not rerun calibration, search or
confirmation. GPU allocation remains at most2048 transitions/512 SAC updates,
600 seconds, two GPUs, three CPUs and16 GiB owned RSS. The final review adds an
explicit 64-step distillation allowance to the same hardware gate: after initial
concurrent training, Bayesian rate and architecture proposals create one compatible
copy and one changed-shape student from the best GPU teacher. Both descendants
must train simultaneously on different GPUs; at least one restores across GPU
assignments. This qualifies the population transfer paths on devices, not merely
two independent SAC fits. The retained CPU continuation check follows. This
bounded engineering addition does not repeat scientific search or confirmation.
Preserve failure receipts.
After success bind the GPU result in the evidence index and complete HARDWARE.

Prepare the zero-training HARDWARE-DOCUMENTATION manifest and execute its exact
command. Bind the new manual while preserving the earlier162-page CPU manual.
Then execute the independent extension audit and terminal master reconciliation
on source-bound zero-training manifests. Their existing implementations reject
missing hardware, altered scores/work/selection and incomplete master stages.
No user scientific threshold or new learning allocation is needed for resumption.

Review disposition: all currently executable independent work is complete.
The master remains open solely for the hardware dependency and its downstream
publication/audit steps. GPU inference/training code is implemented but not yet
qualified by this extension's actual two-device run. No hardware waiver is made.
