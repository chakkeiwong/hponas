# Mutation calibration and remaining repair review

This is V03-03 within the existing master, not a change in project direction.
The master is incomplete. Calibration now passes, so routine phase completion
does not justify stopping. Pilot allocation remains a separate external
blocker; mutation and finite conformance repairs remain eligible.

The actual pinned mutmut 3.8.0 forkserver completed the fixed diagnostic in
443.500 seconds. It generated 8,510 mutants under the complete 24-module
configuration, ran the full statistics suite, passed the eleven selected clean
tests and forced-failure sanity check, and classified the two controls correctly:
the unused stack assignment survived; the deliberately broken stack call was
killed. The other 8,508 outcomes remained unchecked. This establishes the
specific attribution calibration, not whole-population acceptance or general
equivalence of the unused assignment over arbitrary corrupted states.

The executable repair repeats calibration in every fresh campaign workspace.
Exact identities, expected differences and statuses are frozen before execution.
Raw listings, selected-test statistics, logs and diffs are retained within the
audited run. A failed startup or wrong control outcome refuses a full launch.
Calibration counts toward the existing six-hour/four-worker cap, and its two
outcomes remain part of the same frozen complete population. There is no
selection-based acceptance shortcut. The new enforcement/failure-context
receipt contains 128 passing checks; scoped lint and whitespace checks pass.

V02 now retains failed Study results and progress events in its strict-JSON
execution journal. Nonfinite failed values have an explicit diagnostic encoding.
The previously unexplained crash-retry failure remains retained; a later pass
does not establish its cause. Future failures should no longer lose the actual
worker error and retry state.

A bounded diagnostic is rechecking the old critical survivors, previously
uncovered functions and abnormal exits in the successfully calibrated source
snapshot. Its status is diagnostic: later governance source changes are not in
that snapshot, and full acceptance still requires fresh complete execution.

The earlier candidate proof that `max(1, ceil(n/eta))` and
`max(2, ceil(n/eta))` agree whenever `n > eta` is rejected. For the accepted
integer values n=2**53+1 and eta=2**53, actual floating division produces 1.0;
the two bounds differ. This is an arithmetic counterexample without allocating
that enormous population, not an end-to-end failure demonstration. The retained
candidate review remains unchanged and no exclusion follows from it. Exact
promotion arithmetic and other survivors need review before the next freeze.

Remaining sequence: review the diagnostic's raw results; repair actual behavior
or justified missing assertions; handle truly equivalent mutations only with
exact source/diff bindings and checkable arguments; refresh protocol/program
bindings; run the fresh complete calibrated population; reconstruct its gate;
then refresh V01/V02/V14 and the conditional pilot phase on the final source.
All thresholds, required modules and historical failed attempts remain present.
