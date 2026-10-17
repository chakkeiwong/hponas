# Attempt 07 closure and final repair reconciliation

Date: 2026-10-03 (Asia/Shanghai). Existing work: `V03-03/FULL-EXECUTION`
and `V03-03/ATTEMPT07-REPAIR`. This advances the master program's existing
repair sequence; it does not change the scientific goal or authorize a pilot.

## Original execution is closed and retained

The protocol-2.6 run `validation/artifacts/V03/20261002T120052_5a784d7e`
reached its six-hour execution cap. Evidence finalization completed after the
cap; total outer duration was 21,803.310 seconds. Source identity before,
copied, after and independently retained is
`b0eb52ea82984824d3694233f42d0b6a8a2efddfe40849f67debb565f5d90b14`.

The complete generated population contains 8,533 identities: 5,612 raw exit
1, 987 raw exit 0, 20 raw -24, 16 raw 255 and 1,898 unchecked. The stored
result is **INCONCLUSIVE**, with **V16 PASS** for its original evidence audit.
Execution completeness is false. Raw 255 is not retrospectively promoted to a
timeout or detection. The original protocol, four proof rules, outcomes and
verdict remain unchanged.

`evidence/2026-10-01/phase-readiness/attempt07-final-retained/receipt.json`
binds the original results, metadata, audit, execution freeze and logs, full
listing, generated source/metadata/spans, source snapshot and static test data.
The source snapshot independently reproduces the frozen source digest. This
closes `FULL-EXECUTION` under its existing complete-or-capped criterion; it
does not close `FINAL-RECHECK` or the V03 work item.

## Final findings and repairs

Final snapshot 26 includes all 987 observed survivors. Reconciliation 26
identified two final critical cancellation survivors without bound prepared
detection evidence. Direct checks show that the staged nonblocking-wait guard
already detects the first. The second changes the cancellation timeout error
text and passes the prior substring assertion. Exact public error assertions
now detect it. Generated-clean controls pass; both actual generated mutants
fail assertions without a diagnostic timeout. Original run outcomes are intact.

Reconciliation 27 binds the current tests and prospective proof checker:

| Disposition | Observed survivors |
|---|---:|
| Prepared tests directly detect | 645 |
| Exact prospective proof checks pass | 47 |
| Noncritical residuals requiring fresh score evaluation | 295 |
| Critical survivors lacking preparation | 0 |

Every survivor retains an individual identity and disposition. These diagnostic
counts are not a replacement mutation score. The 295 residuals remain in the
fresh population and denominator unless an exact frozen rule proves otherwise;
module score failures still require repair. All 1,898 unchecked identities
require fresh execution. Diagnostic timeouts elsewhere are not relabeled kills.

The final collection audit also reproduced eager Knob/SearchSpace construction
causing collection exit 4 in two test modules. Moving construction into test
bodies preserves all seven original node IDs: mutated collection then exits 0,
clean execution exits 0 and mutated execution exits 1. The focused suite passes
52 checks. A static scan of 157 modules finds no remaining direct eager calls to
imported library symbols; transitive side effects are explicitly outside its scope.

Snapshot 08's complete copied baseline passes **2,824 tests**, with one existing
naming-policy skip and thirteen slow deselections, in **360.910 seconds**. Code,
static test inputs, proof text and installed dependency versions are stable.
The two tightened cancellation assertions produce snapshot 09, still exactly
49 changed paths. Its digest is
`affe8fc9b7a2f553c4b5553d0b7c876e14d544f0f578ba1d22c6d70ef4a33943`.
Seventeen focused cancellation/streaming tests pass. Its complete copied
baseline is running under the existing 900-second preparation cap.

## Required continuation

1. Finish snapshot 09's copied baseline and verify exact source/effective inputs.
2. Verify every original target hash and retained candidate byte; archive all
   originals and adopt only the 49 reviewed paths. A stale baseline or changed
   target refuses adoption. Main executable source remains unchanged until then.
3. Bind the adopted protocol 2.7, register, proof argument and generated program
   views. Run consistency and affected governance checks.
4. Advance `V03-03/FINAL-RECHECK`: mandatory same-workspace calibration, then a
   fresh complete mutation run under the existing six-hour/four-worker envelope.
5. Repair any remaining veto and, after acceptance, continue the already queued
   V01/V02/V14 refresh, conditional pilot readiness and program reconciliation.

The master is incomplete. No phase-boundary stop or new scientific acceptance
decision is needed. Actual pilot allocation remains unassigned and no pilot is
launched by this continuation.
