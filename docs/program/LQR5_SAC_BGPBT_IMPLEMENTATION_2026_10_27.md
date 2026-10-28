# RL-LQR-03: executable five-state SAC BG-PBT companion

The user authorized thorough review and execution of the implementation sequence
identified by RL-LQR-02. This successor closes that sequence; the earlier
no-training readiness assessment and poor scalar learning results remain intact.
The accepted core is unchanged. New optional code is in
`extensions/rl-lqr5-bgpbt`, using the verified five-state environment and literal
network catalog. No sibling repository is imported or modified.

## Reviewed design

Use RLlib 2.58's real `SACTorchLearner`, constructed with `build_learner`, with
an explicit local environment sampler and uniform transition replay. The SAC
loss, four Adam optimizers and Polyak targets are upstream RLlib code. This is
a documented companion sampling harness, not an assertion that stock RLlib's
Algorithm or the finite-MDP `LocalBGPBT` now supports these transfers. Uniform
one-step replay, batch 128, 256 random warmup transitions, one SAC update per four
new transitions, and temperature rate .0003 are fixed controls. The objective
remains deterministic unregularized discounted cost on all 8,192 paths; entropy
regularization is a training mechanism. Oracle gains never enter training.

Checkpoint the complete learner (including target tensors and all Adam states),
temperature, target-update clock, replay and its RNG, environment state/time/RNG,
and Torch/Python/NumPy RNGs. Restore both rate schedulers as well as optimizer
rates. Compatible exploitation copies this state before changing rates and
forking the child's future random streams. Uninterrupted/resumed equivalence is
tested with actual updates. Task intents precede dispatch: committed tasks are
read back without training; an unresolved intent is charged as uncertain work
and refuses automatic retry. Explicit repair may resume only from a verified
checkpoint as a newly charged attempt. Atomic result publication follows an
atomic checkpoint; a crash between them cannot silently trigger duplicate work.

Search actor and critic depths independently in {2,3,4}, each active width in
{8,...,64}, and two independent continuous log rates in [1e-5,1e-2]. Encode the
two depths categorically, eight width slots numerically with a canonical zero
for inactive slots, and two normalized log rates. Time and initial score provide
context. Use the existing BG-PBT temporal mixed Matérn GP (at most 512 rows).
Within a generation propose two-rate trust-region updates conditioned on the
donor architecture and cost. Adapt trust radius from observed improvements and
restart globally on collapse. Between generations sample fresh full-domain
architectures/rates and rank their bounded proposal batch by GP UCB. Store all
points, outcomes, fitted hyperparameters, optimizer status, candidates and
acquisition values. Finite proposal optimization is not a global optimum proof.

Changed shapes use an immutable teacher and only its recorded training replay.
Distill the pre-squash Gaussian by analytical KL (the common invertible tanh
preserves KL), and separately match both soft-Q functions on recorded actions.
Reset incompatible Adam states, copy temperature value with fresh temperature
Adam, set targets exactly to the resulting online critics, and preserve replay
only for the identical environment/role contract. Charge every candidate and
every distillation minibatch, including discarded candidates. Select students by
training-replay distillation loss, never by oracle actions or confirmation seeds.

## Stages and bounded allocation

1. REVIEW: bind this design, predecessor state, resource envelope and requirements.
2. ENGINEERING: adapter, conditional explorer, transfer, transactional recovery;
   positive and negative tests plus two-worker CPU overlap. At most 16,384
   sampler transitions and 2,048 SAC / 1,024 distillation updates per test attempt,
   600 seconds, two workers plus coordinator, 16 GiB owned RSS, 2 GiB output.
3. CALIBRATION: fixed [32,32] actor/critics, rates (.001,.001), seeds 101 and 102,
   8,192 transitions each, costs at 0/2,048/4,096/8,192. Freeze main per-member
   budget at 8,192 if median cost decreases from 4,096 to 8,192, otherwise 4,096.
   This is a compute-budget rule, not a learning-success threshold. Preserve all
   failures; nonfinite training is a repair condition, not a deleted observation.
4. SEARCH: four members, four equal transition segments each; seed 211. Two
   compatible exploit events and one age-triggered generation event. Four
   architecture candidates receive 16 distillation steps; retain two, with 48
   additional steps each, and replace the two worst members. Maximum 32,768
   transitions, 8,192 SAC updates and 160 distillation updates. A four-fit random
   static-search baseline has identical transition allocation; add 120 SAC
   replay updates across its fits to match the 480 actor/critic distillation
   gradient components (one SAC step updates four components). This matches
   transition and component-minibatch counts, not FLOPs or wall time. Report both.
5. CONFIRMATION: before any search reserve seeds 801,802,803. Freeze the final
   selected static architecture and rates for each method; retrain both from
   scratch at the frozen budget on all three paired seeds (maximum 49,152
   transitions, 12,288 SAC updates). This tests selected static configurations,
   explicitly not transfer-lineage replay. Report every exact cost and Riccati
   gap, paired differences and variation; three seeds cannot establish universal
   reliability or a global HPO/NAS optimum. Freeze the full search lineage too.
6. HARDWARE: separately bound two-worker simultaneous GPU SAC updates and a
   cross-device checkpoint restore (at most 2,048 transitions, 512 SAC updates,
   600 seconds). Admit only two idle GPUs (no compute processes, utilization at
   most 10%); never interrupt other users' work. CPU phases and documentation
   can proceed independently. Unavailable GPUs are a recorded infrastructure
   blocker, not a waiver or permission to mark the master complete.
7. DOCUMENTATION: add a successor LaTeX chapter, user guide and exact operation
   commands; document API, learning outcome, limitations and all failed attempts.
8. AUDIT: independently reconstruct scores from exported actors, reference
   identity, proposal selections, transfer/checkpoint identities, complete work
   ledgers, fresh static confirmation and parallel evidence. Tampered scores,
   omitted work, unsupported optimum and incomplete hardware must be rejected.
9. GAP-01/FINAL-AUDIT remains last and reconciles original qualification and all
   extension stages. No completion while any required behavior lacks evidence.

Each scientific operation has a source-bound manifest, a once-only successful
allocation, 1,800-second deadline, at most two training workers plus coordinator,
16 GiB owned RSS, 4 GiB outputs and an 8 GiB free-disk floor. Engineering repair
attempts keep previous receipts. No network, installations or external messages.
The GPU operation uses the same ceiling with two explicitly admitted devices.
Versioned manifests bind runner, source, runtime lock and predecessor evidence;
changing scientific source invalidates descendant evidence rather than silently
relabeling it. The reviewed whole scientific allocation is at most 133,120
transitions including calibration, both searches, confirmation and hardware;
engineering repair attempts are reported separately. No broad campaign.

## Review findings and disposition

The previous 64-update experiment did not establish learning. This design
increases measured optimizer work, calibrates before selection, and reserves
fresh training seeds. Complete-law scoring removes rollout evaluation noise,
but cannot remove training variation. Shape changes require distillation, not
tensor copying. RLlib learner checkpoints omit standalone temperature and target
clock, so these are explicitly carried. A local harness makes environment and
replay continuation testable without repeated Ray cluster startup. Worker GPU
visibility must be installed before Torch import, using `ResourceExecutor`.

This plan is executable with the installed runtime. GPU occupancy is the only
currently observed infrastructure constraint. Phase repair/refresh continues
through all independent work. Learning quality is reported objectively through
the attainable Riccati bound; an engineering pass never substitutes for it.
