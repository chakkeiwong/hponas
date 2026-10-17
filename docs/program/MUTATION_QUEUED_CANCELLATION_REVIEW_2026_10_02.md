# Queued work after an unconfirmed cancellation

Revision 1.32 continues the same V03-03 cancellation repair. No protocol,
scientific criterion, numerical threshold, resource cap or required population
changes. Protocol 2.6 already requires refusing reuse after unconfirmed
cancellation; this repair completes that behavior within an existing batch.

The first post-repair full V02 passed with V16 PASS at
`validation/artifacts/V02/20261002T104907_93e90b2e`; all 304 conformance checks
passed. The corresponding full copied baseline passed with 2,137 tests, one
existing skip and 13 slow deselections in 340.244 seconds. Its start, copied
source and final source identities matched. Both results remain retained.

Review then found that the public entry check happened before ThreadPoolExecutor
queued the whole batch. If cancellation failed inside one collector, another
queued collector could start a remote task without rechecking the poisoned
executor. An initial uncontrolled diagnostic did not reproduce this scheduling
window. An ordered-submission diagnostic reproduced it in all five trials.
Both streaming and non-streaming public batch regressions failed before repair.

The existing initialization guard is now checked at each streaming attempt and
at each non-streaming remote submission. Queued work and later retries refuse
entry after cancellation has been marked unconfirmed. Already active work is
not claimed to be retroactively stopped by this check. The regression uses the
real thread pool with controlled enqueue timing and asserts that no second
remote evaluation starts. The 121 affected runtime, cancellation, mutation
phase and equivalence tests passed; Ruff and whitespace checks passed.

The earlier source is now historical. Refresh full V02 and the copied clean
baseline once on the repaired source, reconcile their exact receipts, then
advance attempt 07 under protocol 2.6. No mutation campaign is running during
this repair. The remaining master sequence (full mutation, final finite
conformance, conditional pilot preparation and reconciliation) is unchanged.
