# Reviewed full mutation execution after calibration repairs

This continues V03-03. The master is incomplete and remains in Tier 0 acceptance
and remediation. Every earlier interrupted campaign, false-kill diagnosis,
failed finite refresh and diagnostic receipt remains retained.

The initial supported forkserver calibration passed its exact controls in
443.500 seconds. A subsequent 900-second diagnostic recorded 94 killed,
31 surviving and ten unchecked mutants; it is incomplete. It killed all 42
previously uncovered mutants and all 49 previously surviving critical
architecture mutants, plus the checkpoint-validation and PASHA boundary mutants.
It produced no recorded segfault. Clean isolation exposed additional previously
abnormal survivors; they were not counted as kills.

One more false-kill mechanism is reproduced independently: running the shared
Ray cluster test before the owned-cluster test makes the latter fail on clean
source. The ownership assertion was in the same module as a module-scoped
cluster fixture. Moving that test to a separate module preserves all six
original assertions and gives the shared cluster a teardown boundary. The same
two-test ordering changed from one failure/one pass to two passes (96.12 seconds).
Every fresh V03 calibration now checks that order, exact command and unskipped
JUnit cases as well as the original mutant controls, within the 900-second cap.

New direct runtime checks cover rejected legacy/reference ASHA schemas and
precise refusal diagnostics, late progress cancellation, foreign report identity
and assigned fidelity. They assert preserved state/accounting. The floating
ceiling counterexample is fixed by exact integer ratio arithmetic and checked
against an independent Fraction oracle for integral/floating eta and boundary
counts through 2**63-1. The affected scheduler/lifecycle receipt has 131 passes.
The new promotion helper joins critical paths; no existing critical path leaves.

Version 2.5 prospectively permits only the three explicitly scoped proofs in
MUTATION_EQUIVALENCE_LEMMAS_2026_10_02.md. Exact source hashes and generated
original/mutated functions are mandatory. The checker reproduced five proofs
from actual diagnostic mutants and rejects stale source and unsupported
rewrites. Historical attempts remain unchanged. The earlier zero-exclusion-only
next-run policy is superseded by these concrete proofs under the original
five-percent allowance. This is not human evaluation of success. Scores,
critical-path vetoes, timeout limits and required modules are unchanged.

Every fresh campaign now binds calibration, complete raw listing, full log,
generated proof inputs, tool/config/protocol bytes and source identities in its
audited repository artifact directory. Calibration counts inside the original
six-hour/four-worker ceiling. A failed calibration refuses the full invocation.
No executable source will be changed during this frozen campaign. Current
V01/V02/V14 and conditional pilot readiness will be refreshed on the final
source after mutation outcomes and remaining repairs are resolved.

V02 also captures actual failed Study results and progress events, including
explicit nonfinite diagnostic values. Its prior unexplained crash-retry failure
is retained; the separate test-order failure is not asserted to be its cause.
Pilot allocation remains an external spending prerequisite. It does not prevent
the independent mutation and finite-conformance work from advancing.

Attempt 05 retained 8,509 generated mutants and correctly refused full execution after its 370.8-second statistics preflight failed. All outcomes remain unchecked, so V03 is INCONCLUSIVE with V16 PASS. Four newly added proof-checker tests read instrumented module source as if it were the reviewed original. The exact instrumented reproduction had four failures/eight passes. Hash-bound source fixtures now isolate the checker tests from instrumentation; the same instrumented-context diagnostic has twelve passes. Production verification still reconstructs generated code against actual campaign source. No criterion or population was narrowed, and attempt 05 remains preserved.
