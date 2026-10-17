# Cancellation repair and prospective mutation freeze

Revision 1.31 continues V03-03 under the existing repair, verify, refresh and
advance policy. It changes no acceptance threshold, required module, worker
limit, wall allowance, scientific claim or pilot allocation.

Attempt 06, `validation/artifacts/V03/20261002T083705_aaa30ce7`, remains
INCONCLUSIVE with V16 PASS: 8,509 mutants, 1,606 killed, 136 survived, three
timeouts and 6,764 unchecked. Six survivors met its frozen equivalence rules;
one critical survivor remained unproved. Its 538.342-second calibration and
passing full clean baseline did not establish acceptance. The coordinator was
interrupted to repair an evidence-reliability defect; its raw results, inputs
and audit remain unchanged.

## Evidence and repairs

The original failed V02 Ray logs show the previous timeout task receiving a
force-cancel request, a new evaluation being assigned to the same worker, and
that worker exiting because of the earlier cancellation. This consumed the
new evaluation's first attempt before its intentional crash on the retry.
Reporting channels had been destroyed while asynchronous cancellation was
still pending. The copied original logs and chronology are retained in
`evidence/2026-10-01/phase-readiness/ray-v02-cancellation-history-01/receipt.json`.
This is distinct from the already repaired shared-cluster fixture scope.

RayExecutor now waits for a terminal task result before releasing reporting
queues or retrying. A 30-second failure to confirm cancellation poisons the
executor and raises; subsequent public use is refused. Failed-attempt cost and
elapsed accounting include this wait. Controlled cancellation tests recorded
three failures before repair and 33 passes afterward. The four live selected
tests passed in 111.37 seconds; the later final accounting adjustment is
covered in the 130-pass affected suite. A fresh full V02 and full clean
baseline remain prerequisites for the next mutation freeze.

Public contract tests also cover the single-trial streaming callback, all
persisted event identities and timestamps, exported TPE snapshot ownership,
and Sobol continuation against independent SciPy sequences at zero, one and
five consumed proposals with both scramble modes. These close observed test
gaps without treating a survivor as a demonstrated production defect.

The fourth prospective lemma, `tpe_replay_copy_v1`, proves the redundant
initial deep copy in concrete TPE replay for ordinary finite JSON checkpoints.
The replay reads its input and retains newly owned proposals and observations;
an inductive argument and exact source-bound generated-function reconstruction
are retained. Custom copy/equality hooks, subclass overrides and concurrent
input mutation are outside the stated domain. Export/observe shallow-copy
mutations remain outside the lemma. No attempt-06 result is reclassified.

The version-2.5 argument is retained at its original hash in the archive before
the TPE lemma. The current argument is a separate evidence entry. Version 2.6
requires the four-test clean Ray order (restart, timeout, crash retry, owned
cluster restart), the cancellation helper as a critical path, and exactly the
four stated lemmas. Calibration remains inside 900 seconds and the six-hour,
four-worker full execution allowance.

## Execution sequence

1. Reconcile this review, all retained attempts, proof versions and protocol
   identities in the master. Run consistency, protocol and continuation checks.
2. Run audited V02 with the existing failure-state capture, then a fresh copied
   full baseline under the exact mutation selection. Diagnose any failures;
   preserve them. Complete `V03-03/CANCELLATION-REPAIR` only on passing evidence.
3. Start attempt 07 in a fresh workspace with protocol 2.6. Freeze executable,
   test, dependency and protocol inputs until it finishes or requires an
   evidence-preserving interruption. Inspect every outcome and continue repairs
   under the same master; an incomplete run cannot close mutation acceptance.
4. Continue the existing post-mutation V01/V02/V14, conditional pilot readiness
   and program reconciliation entries. Reuse current passing evidence only if
   its source/protocol identity still matches. The pilot remains unallocated.

The master and release remain incomplete. This preparation step is internal
work and does not justify stopping or requesting another scientific decision.
