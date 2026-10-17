# Attempt 07 findings and continued repair sequence

Revision 1.33 records demonstrated findings while attempt 07 remains frozen and
running. It does not change its source, tests, protocol 2.6, proof rules or raw
outcomes. All resource caps and scientific acceptance criteria remain unchanged.

The run passed calibration in 580.460 seconds, its full clean baseline and its
forced-failure check. Its first completed module, architecture, has 182 kills
out of 202 mutants and meets the 90% module threshold. This is not a whole-run
verdict. Subsequent unproved critical GP checkpoint survivors already preclude
PASS under the frozen zero-critical-survivor rule. Final counts and the audited
verdict remain pending.

## Confirmed findings

1. GP recovery coverage misses several single-field count/coordinate corruptions,
   accepted endpoint cases and precise refusal diagnostics. A separate candidate
   with 32 checks passes on clean production source and generated-clean source.
   It detects 55 of 57 observed GP checkpoint survivors through the public
   contract. The candidate has not changed any campaign outcome.
2. The remaining two GP checkpoint survivors replace a cleared private model or
   acquisition cache with an empty string. A separate conditional argument notes
   that public fitted proposals unconditionally rebuild both before reading them;
   bootstrap proposals do not read them. The argument is prospective only and
   still requires exact source-bound review and mechanical checking. Private
   cache assertions must not manufacture kills. Attempt 07 retains both survivors.
3. A public-path check of that argument found a production decoding defect. On
   clean source, a valid fitted GP proposal returns rate=0.10000000000000006 for
   a declared upper bound of 0.1. The search-space validator rejects it. Decoding
   normalized endpoint [0,1] reproduces the same problem independently of fitting.
   The clean counterexample is retained; successful mathematical inversion does
   not guarantee a representable floating value inside the original bounds.
4. A separate public default-direction candidate detects the surviving reversal
   of `get_best()`'s default, including replacement observations and recovery.
   It passes production/generated-clean controls and fails the exact generated
   default mutant. It remains outside the frozen suite.

## Why finish the current inventory

The critical survivors mathematically preclude PASS for this freeze. Continuing
the already capped population gathers the remaining defects so the next repair
can address them together. Repeatedly restarting after each small survivor group
would repeatedly pay calibration/baseline costs and defer discovery of later
functions. This is an evidence-collection phase with a known veto, not a claim
that more kills can cancel a critical survivor. Reliability failures still
require evidence-preserving interruption; the six-hour bound still applies.

## Required continuation

1. Finish attempt 07 within its existing cap. Retain its complete or incomplete
   listing, all outcomes, source/tool inputs, proof certificates and V16 receipt.
   Review every module, critical survivor, timeout and abnormal outcome.
2. Complete `V03-03/ATTEMPT07-REPAIR`: integrate justified public regressions;
   repair GP decoding so valid normalized points yield configurations inside
   declared bounds; check linear/log endpoints, interior values and the public
   fitted proposal counterexample. Review all other final findings. Separate
   production defects from coverage gaps and conditional equivalence candidates.
3. Review and mechanically check any prospective proof on the repaired source.
   A GP source change invalidates existing pinned GP proof context; re-review and
   rebind its exact fixture/checker/argument rather than silently changing a hash.
   Any amended protocol is a new version applying only to the next freeze.
4. Pass affected tests, clean mutation baseline and any affected finite checks.
   Reconcile the master, then run `V03-03/FINAL-RECHECK` on a fresh source freeze
   within the same six-hour/four-worker envelope. Any further failure re-enters
   the repair loop; no diagnostic or human judgment can substitute for PASS.
5. Only after final mutation acceptance continue the existing V01/V02/V14 refresh,
   conditional pilot readiness and final reconciliation queue. Pilot allocation
   remains separate and unassigned; these internal repairs need no new user
   scientific decision or direction change.

The master and release remain incomplete. The newly explicit repair and recheck
steps are part of the existing V03-03 obligation, not an added capability.
