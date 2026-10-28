# RL-LQR-03: selection review and shared-GPU repair

This successor responds to the user's concern about the identical selected
configuration and their explicit authorization to share GPUs with other jobs.
It supersedes the idle-device prerequisite and the claim that only hardware
work remains. The original plan, runs, source snapshots and manual remain
historical evidence. The accepted core is unchanged.

## Findings from the saved search and code

The winner was initial random member 1: actor [33,12], critic [51,19,46]. It
was not the default [32,32] configuration. Both methods shared all four initial
configurations and seeds. The winning population member received neither rate
changes nor architecture transfers. The baseline additionally received 30 SAC
updates, so its small final-cost difference does not demonstrate a population
advantage. Fresh confirmation trained the same configuration with the same seeds
twice; equal results follow from the declared experiment, not an independent
confirmation of the search procedure.

Four new architectures were distilled, but only two received any SAC training.
The first elimination used a sum of policy KL and two unnormalized critic MSEs,
before the proposed SAC rates could act. This ranks imitation, not the tuning
objective. One retained student's cost was 3.259653 immediately after transfer,
then 3.273872 and 3.269162 during SAC. The original winner had already achieved
3.259173 halfway through training, but the selection discarded that checkpoint
and returned its worse final score 3.260191. These are real outcomes, not grounds
to force a novel architecture to win.

The trust radius updated on each member's own improvement in arrival order,
instead of once per population round against an incumbent. Reordering identical
round outcomes could change the next search region. Architecture proposals also
used the incremental-learning surrogate rather than an objective-based
architecture model. These defects weaken the joint-search demonstration.

A huge syntactic space does not imply that a new architecture must win: these
small networks can approximate the same simple linear feedback, and the methods
share their initial sample. The Riccati bound certifies each evaluated policy's
cost gap; it does not certify global architecture/rate optimality.

## Reviewed repair and bounded execution

1. REPAIR-REVIEW records this diagnosis and allocation before new training.
2. REPAIR-ENGINEERING adds a versioned controller. Update its region once per
   round using the best observed objective, independent of member order; on
   collapse choose a historical center with a global GP and reset local history.
   Architecture proposals use best observed objective by joint configuration,
   combining two Bayesian and two random candidates. Preserve continuous rates
   and the existing full conditional architecture domain. Distill each candidate
   for 64 updates, then train every candidate at its proposed rates before
   halving by actual LQR cost. Keep the best evaluated checkpoint across the
   entire search for both methods. Test adverse ordering, objective versus
   imitation ranking, late regression, real candidate training and replay.
3. PROCEDURE-CHECK executes three complete, independently seeded searches
   (9211, 9212, 9213), with a paired static baseline for each. Four members get
   four 2048-transition segments. Two compatible events and one architecture
   event remain. Four new candidates get 1024 SAC transitions each, and the two
   selected by objective get another 1024. Each method gets 38912 transitions;
   the four static fits get 9728 each plus 48 replay updates each. This matches
   38656 component-gradient minibatches per method, not FLOPs or wall time.
   Baseline checkpoints at each 2048 transitions and at termination are eligible
   for selection. Total: 233472 transitions, 57408 SAC updates and 768
   distillation updates, at most 1800 seconds, two CPU workers, 16 GiB owned RSS.
   These are three procedure replications, not duplicated static confirmations.
   Report each difference, mean/range and an exact paired sign-randomization
   diagnostic with its three-pair limitation. No adaptive expansion or required
   winner; no global or universal superiority claim. The earlier result is
   retained as a pilot. No new scientific threshold is sought from the user.
4. HARDWARE uses two physical GPUs with at least 4 GiB free each, selected by
   free memory and utilization without requiring idle devices or empty process
   lists. Limit each worker's Torch allocator to 1 GiB and record peak allocation,
   reservation, physical UUID, other-process occupancy and simultaneous update
   intervals. The existing ceiling remains 2048 transitions, 512 SAC and 64
   distillation updates, 600 seconds. Abort cleanly on admission/allocator/runtime
   failure; do not terminate other workloads or automatically retry training.
   Busy devices invalidate a speedup claim, not correctness/concurrency evidence.
5. HARDWARE-DOCUMENTATION rebuilds the complete manual with diagnosis, repaired
   procedure results, limitations and actual shared-GPU qualification.
6. AUDIT independently reconstructs legacy and successor work, checkpoint
   selection, candidate objective ranking, proposal decisions, all complete
   procedure replications and hardware. Negative controls reject false novel
   winners, omitted candidate work and static confirmations mislabeled as
   procedure evidence. GAP-01/FINAL-AUDIT remains the last master stage.

Engineering retains the original reviewed roster plus the repair tests. Its
ceiling is 32768 transitions, 8192 SAC and 1536 distillation updates, 600 seconds.
Consumed source snapshots remain immutable; operations bind current source and
the predecessor evidence in new manifests. The original successful scientific
operations are never rerun or relabeled. This is a bounded SAC adaptation using
the BG-PBT kernel and generational principles. Its replay warm-start followed
by SAC is not the paper's annealed on-policy PPO distillation, and finite
architecture acquisition is not Casmopolitan's full discrete optimizer. Public
LocalBGPBT remains limited to its previously qualified adapter.

Review: objective, comparison, selection, work accounting, resource sharing,
recovery and final audit are explicit. Success means correct executable tuning
and honest objective evidence; an initial or baseline winner is a valid result.
