# Attempt10 repair and continued master execution

Attempt10 remains INCONCLUSIVE under unchanged V03 protocol 2.7. Its original
8,566 outcomes, independent reconstruction and V16 PASS are retained. The
0.9607866 overall score and every module score satisfy their thresholds, but
the critical `Study._accept` survivor and one raw `-9` outcome prevent acceptance.
No human assessment changes that verdict.

## Diagnosed defects and objective repair

The Attempt10 coordinator copied Attempt09's evidence-ID prefix. Its six new
entries collided with preserved Attempt09 entries, leaving revision 1.66
invalid. Revision 1.67 gives the six Attempt10 entries their own IDs, repairs
their exact references and retains the invalid revision in an immutable archive.
All five register/view/protocol/continuation/combined audits pass. The next
coordinator uses its own attempt namespace and validates the candidate register
before replacing the current one. Historical coordinators remain unchanged.

The sole critical survivor changes the default absent live cost from 0 to 1.
Existing endpoint tests used a final cost of 2, hiding the error in `max`.
The public batch/singleton test now exercises zero, fractional and larger costs,
checking both each result and the aggregate. Against the retained generated
source, the unchanged control passes and the exact survivor fails. The existing
Study implementation is correct; this is a demonstrated coverage repair.

The abnormal ASHA initializer mutant replaces `r *= eta` with `r /= eta`.
For positive r and eta > 1 this decreases r, eventually rounds to zero and never
leaves `while r <= r_max`. The retained worker log records PID 2480304, a
514-second wall allowance and raw `-9` after 534.332 seconds. The retained kernel
journal independently identifies that same PID as the global out-of-memory
victim, with 153,530,540 KiB of anonymous resident memory. The historical outcome
remains abnormal; it is neither relabeled as a timeout nor a kill.

The product has a related valid-input defect: with the smallest positive float
and eta = nextafter(1, +infinity), multiplication rounds back to that same float.
Four public-constructor tests fail before repair with nontermination. ASHA,
budgeted ASHA (also used by PASHA), and MO-ASHA now require each computed rung
to increase and append the exact final budget once. Nonadvancing floating-point
inputs raise ValueError. Geometric, truncated, singleton, overflow and subnormal
progressions have exact expected-output tests. A constructor-only alarm prevents
an erroneous loop exhausting memory; it neither alters mutation outcomes nor
changes campaign timeout criteria. Focused verification passes 140 checks;
governance, mutation provenance and equivalence verification passes another
421 checks and 16 subtests.

## Program review and continuation

The combined audit covers all 34 work items, 93 mapped requirements, 19 protocol
owners and six phase guards. Required work, decision resolvers and dependencies
remain explicit. Historical Tier-0 conformance is stale after this source/test
repair; it cannot close the current-source engineering gate. The remaining
sequence stays inside the approved master:

1. Complete `V03-03/ATTEMPT10-REPAIR` with retained before/after and diagnostic
   evidence. Preserve both campaigns and the failed register refresh.
2. Execute `V03-03/ATTEMPT11-PREFLIGHT`: full copied baseline, supported offline
   installation verification and exact runtime/source bindings.
3. Execute `V03-03/FINAL-RECHECK` as a newly registered Attempt11. Retain the
   complete population, same-workspace calibration, four CPU workers, native
   threads limited to one, and six-hour total cap. Protocol 2.7, exclusions and
   all acceptance thresholds remain unchanged.
4. On independently reconstructed V03/V16 PASS, execute the registered V01,
   V02 and V14 conformance sequence, then final-source verification, conditional
   pilot readiness and the whole-program continuation audit. On a non-PASS,
   preserve the result and return to internal repair.

The master is incomplete. A running campaign or internal repair is not a stopping
boundary. No pilot/confirmation allocation or release follows from these repairs.
The separate allocation issue remains: retained high-cost scenarios do not prove
an affordable or necessary resource requirement. After engineering closure, the
phase plan must present that limitation honestly and exhaust eligible independent
work before treating it as an external blocker.
