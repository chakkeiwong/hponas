# Staged baseline, test-input binding and replay preparation

This continues `V03-03/ATTEMPT07-REPAIR`. Attempt 07 still runs on the unchanged
live source and protocol 2.6. Its outcomes and four proof rules are not amended.
The new snapshot, `attempt07-integrated-preparation-02/manifest.json` under the
phase-readiness evidence directory, retains exact candidate files and a patch.

## Verified preparation

The first integrated copied baseline finished in 364.276 seconds with 2,648
passing tests, one existing naming-policy skip, thirteen slow deselections and
no failures. Stage, copied and end source identities matched; the live campaign
source remained unchanged. That receipt binds the earlier integrated candidate,
not later edits. It is a clean baseline, not mutation acceptance.

Review found that the shared source digest intentionally omits non-Python test
data. A changed proof-case JSON file could therefore alter effective checks
without changing that digest. The prospective V03 freeze now separately binds
all non-Python test inputs, verifies the generated test tree during calibration
and at completion, and retains those exact bytes. Altered, missing, extra,
duplicate and falsely rebound inputs cannot certify completion. The master also
marks such evidence STALE even when Python source and protocol hashes match.
The historical source-digest algorithm and earlier outcomes remain intact.

The affected phase and input-binding checks pass (79 tests). Governance and
continuation pass (71 tests). A separate copy of the actual instrumented library
passes all 308 phase/proof/raw-validator checks, so proof fixtures do not depend
on importing an uninstrumented implementation from the live checkout.

The current Study recovery candidate was rerun against every observed recovery
survivor: all 129 were detected with a passing generated-clean control. Replay
preparation now covers exact refusals, event ordering, progress identity,
completion status mapping, scheduler capability differences, resource-cap
boundaries and cancellation before an evaluation produces an observation.
Its latest bounded diagnostic detected 109 of 115 observed module survivors;
52 clean checks pass. The two remaining critical candidates have exact
prospective arguments for an unused batch default and an initially false
promotion queue. Four remaining noncritical survivors stay in the denominator.

The isolated prospective checker/register/argument now contain seventeen rules.
The latest proof diagnostic verifies 37 exact new transformations and rejects
140 negative cases. The source-bound queue argument accepts only the initial
empty-list-to-None assignment: every use before replacement is a truth test or
a guarded pop, and all list iteration follows replacement by list(). Other
queue operations are not covered.

The reconciliation against snapshot 18 finds 516 observed survivors detected by
tests whose exact bytes are staged, 42 individually checked prospective proof
candidates, and 281 remaining noncritical survivors. No observed critical
survivor in that snapshot lacks preparation. The snapshot is incomplete and
read while the original run proceeds; none of these counts is a new kill score,
an exclusion from attempt 07, or an acceptance verdict.

## Continue the existing sequence

Continue the capped inventory and review later findings. Before adoption retain
its final raw metadata, statistics, debug log and audited result; archive the
active four-rule argument and repoint its historical evidence reference. Apply
only the verified final repair set, repeat the final-source checks/baseline,
then run the already queued full fresh recheck. Continue through conformance,
conditional pilot-readiness and master reconciliation. Pilot allocation and
release remain separate administrative boundaries; ordinary preparation and
phase completion are not reasons to stop.
