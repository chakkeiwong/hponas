# Calibration identity and pending decision-path coverage

This continues `V03-03/ATTEMPT07-REPAIR` in the existing master program.
Attempt 07 remains frozen on protocol 2.6 and source
`b0eb52ea82984824d3694233f42d0b6a8a2efddfe40849f67debb565f5d90b14`.
The implementation changes below are isolated preparation. No original
outcome, acceptance threshold, pilot allocation or release state changes.

## Calibration evidence repair

The existing verifier checked a set of four test names. A retained
counterexample showed it accepted reversed execution order and a matching
test name attributed to the wrong module. The candidate now compares the
ordered `(classname, name)` sequence against all four prescribed test IDs.
Reordering, wrong-module substitution and duplication are refused. The clean
control passes, and 341 validator, proof, raw-outcome and ordering tests pass.
Both before/after implementations and counterexample receipts are retained.
The actual attempt-07 calibration XML has the prescribed module identities
and order; this repair does not reinterpret its original verdict.

The versioned baseline driver separately binds source identity, every static
non-Python test input, the equivalence argument and installed dependency
versions before and after execution. It retains input bytes and checks both
the staged and copied candidates plus unchanged main source. Earlier v1
baseline receipts remain preserved and are not represented as including
these additional fields.

## Streaming and ASHA checks

Bounded direct checks of pending Ray streaming mutations exposed missing
assertions for a failed trial's NaN objective and for collecting a worker that
finishes before its deadline after an empty reporting poll. The candidate
now covers both while preserving the existing nonblocking and no-deadline
polling contract. Its latest diagnostic detects 93 of 96 selected pending or
surviving transformations. Two have existing exact prospective arguments;
the remaining cancellation transformation is detected by the unchanged
controller-failure test in a separate process (clean PASS, mutated failure in
5.975 seconds). All 47 focused streaming/control tests and all 72 host Ray
contract checks pass. The latter includes the separately checked unit file
that remains outside the unchanged full mutation selection.

The independent ASHA reference file detects 177 of 241 examined pending
decision-path transformations, leaving 62 undetected and two diagnostic
timeouts. Additional public checks cover loss ordering independent of IDs,
paused/active/terminal checkpoint state, exact refusal diagnostics, legacy
dispatch, current-step median means, disabled/off-grid pruning, and completed
endpoint-only trials without invented streamed histories. These detect 224
of the same 241 transformations. The union of the two exact test files detects
all 241, with clean controls. The two direct-check timeouts are not converted
into detections: they are independently detected by the added checks. All
112 affected ASHA/reference/report/promotion tests pass. Production scheduler
code, numerical rules and the twenty-rule proof catalog are unchanged.

These are bounded preparation diagnostics, not full-population outcomes or
scientific acceptance. Actual generated inputs, candidate bytes and individual
results remain bound in their receipts. The original campaign stays untouched.

## Candidate and verification state

Snapshot 07 retains 47 changed files and their exact patch. The candidate
source identity is
`53d6a15157c3e3dee5945400446b4d0bb27f8fd7bde59ce25d571c2d82ad4e2b`.
Every original/candidate target hash has been checked before adoption.

The snapshot-05 host baseline passed 2,799 tests in 395.010 seconds, and the
snapshot-06 host baseline passed 2,800 in 398.106 seconds. Each has the existing
naming-policy skip and thirteen slow deselections, with stable source, data,
argument and dependency inputs. A sandbox baseline failed only while starting
Ray; the retained gRPC error identifies `socket` errno 1, Operation not
permitted. The affected checks passed with host sockets. The same sandbox
limitation in the separate expanded Ray test invocation is retained alongside
its successful host rerun. Infrastructure refusal is not an algorithm verdict.

The snapshot-07 full copied baseline passed 2,824 tests, with the same one
skip and thirteen slow deselections, in 399.745 seconds under the 900-second
bound. Source, all seventeen static test inputs, the proof argument and all
253 installed distribution versions remained stable across the staged, copied
and final checks. Main source remained the original attempt-07 source. This
is the current integrated preparation baseline; adoption checks and actual
same-workspace mutation calibration remain mandatory.

Snapshot 25 recorded 6,541 of 8,533 original mutants. Its 974 survivors
reconcile to 639 prepared test detections, 47 checked prospective arguments
and 288 noncritical residuals. No observed critical survivor in that incomplete
snapshot lacks preparation. Residuals and all unchecked identities remain
inside the fresh full population; these counts are not a predicted PASS.

## Continue through execution closure

The original four-rule argument, protocol 2.6, checker and affected production
inputs are archived under `archive/program-2026-10-03/before-protocol-27-adoption`.
Historical E-R131 proof evidence must point to that unchanged argument before
the active file is replaced. No prospective protocol has been adopted yet.

When the original capped execution closes, retain its audited result, complete
listing, raw metadata, debug/statistics logs, generated sources/spans and exact
original source snapshot. The prepared retention driver refuses to run before
the audited files exist or if original source identity has drifted. Then
reconcile final findings, adopt only verified candidate bytes, verify the
effective final inputs and execute the fresh same-workspace calibration and
full recheck. Continue through V01/V02/V14, conditional pilot readiness and
master reconciliation. This is the existing repair/refresh/advance sequence;
ordinary phase boundaries are not stopping points.
