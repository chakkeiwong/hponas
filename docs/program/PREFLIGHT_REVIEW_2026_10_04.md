# Corrected program review and repaired-source preflight

Revision 1.61 continues the existing master. It corrects overstatements in
revision 1.60, preserved in the before-preflight-review-01 archive, and proceeds
to V03-03/REPAIRED-SOURCE-PREFLIGHT. The program remains incomplete.

The goal and scope are unchanged: reliable HPO and moderate architecture
coordinates, durable recovery, objective finite conformance and independent
scientific acceptance. General topology/supernet NAS remains excluded. The
whole-program ownership review and combined dependency audit still apply.

## Repairs to the program

* REQ-roadmap-03 and REQ-ch05-01 are required, with Tier-0 conformance assigned
  to SPEC-02/REL-01 and conditional V06 performance/default activation to T1-MF.
  Keeping them unresolved until V06 while linking them to REL-01 recreated a
  release cycle. The policy decision resolves ownership only; no empirical
  result is inferred. A named T1-MF default-disposition stage now enforces the
  later consequence before Tier-1 reconciliation.
* The source-adoption receipt from revision 1.60 associated the final Study
  refactor with tests that preceded it. Preserve that receipt and correct its
  scope: contracts-r3 tests verified the final refactor; the complete copied
  baseline and installation remain mandatory. Focused verification is not
  full-source acceptance.
* The earlier WL-00 evidence primarily covered generic Torch architecture and
  workload wrappers. Direct Brax checks now verify both policy and value kernel
  shapes and numerical activation outputs for two architectures and all three
  supported activations. Protected episode ranges refuse overlap before policy
  loading. V14 acceptance and T1-MF live PPO streaming remain separate gates.
* The revision 1.60 Tier-0 phase binding is historical scope preparation. Its
  source is stale, and V04-T0/V05 identities remain unresolved. It cannot
  certify those protocols or release; the release checker must continue to
  refuse them until their separate objective closure.

## Source repair and evidence

Study recovery now retains acknowledged live cost when a stopped pending trial
is accepted as cancelled without redispatch. The reproduced positive-cost case
previously returned zero. Marking incomplete accounting at execution rather
than loading preserves checkpoint roundtrip fidelity. Explicit terminal flow
removes a redundant initializer without adding any equivalence exclusion.

New bounded public-contract checks cover coordinate inversion and clipping,
conditions and canonical serialization, baseline recovery, result validity,
Study options and executor defaults, legacy adaptation and scheduler-free
reporting. Retained-source diagnostics run unchanged controls first and retain
every selected case. They do not change Attempt09 outcomes. The small-module
diagnostic detects 431 of 444 selected survivors/unchecked cases in 3.68 seconds,
with no timeouts. Remaining cases are still included in the fresh full campaign;
plausible equivalence is not an authorized exclusion.

The schema/network tests passed 57 cases; contracts-r3 passed 218 after the Study
refactor. Failed preliminary test runs are retained: one test incorrectly passed
None outside the numeric Result contract; one legacy test double omitted the
required state interface. Both tests were corrected without broadening product
scope. The original positive-cost recovery failure remains a separate proved
product defect and has its own repair evidence.

## Executable sequence and constraints

1. V03-03/REPAIRED-SOURCE-PREFLIGHT: complete the copied baseline with all
   registered selected tests, then verify the supported installed wheel on
   Python 3.12 and 3.13 with existing dependencies. Retain a failed attempt and
   repair its demonstrated cause before advancing. Baseline and installation
   each have their existing 900-second bound.
2. V03-03/FINAL-RECHECK: verify current source and dependencies, mandatory
   same-workspace calibration, then one full mutation campaign with four
   workers and the unchanged six-hour cap. Retain raw outcomes and independently
   reconstruct V03 and V16. Diagnostics are not campaign kills; timeout and
   unchecked outcomes cannot become kills. An incomplete run reopens repair.
3. VAL-01/POST-MUTATION-CONFORMANCE and REL-01/FINAL-SOURCE-VALIDATION: refresh
   finite V01/V02/V14 and final engineering receipts only after accepted mutation
   evidence. A source change requires affected revalidation before release.
4. STAT-03P through PILOT-01/CAP-01/PPO-01: finish the cost/missingness review,
   exact independent-pilot design and allocation, then registered sizing and
   separately allocated confirmation. Per-entry caps reduce reservation overhead;
   they cannot invent optimizer effects or authorize spending. V05's all-grid
   missingness veto remains. No pilot allocation exists.
5. REL-01 and the later master phases retain their separate scientific and
   administrative prerequisites. A terminal unfavorable result is preserved
   under its frozen rule, with capability consequences recorded prospectively.

The whole program has 93 requirements, 34 work items and 19 protocol owners.
The new default-disposition stage extends the existing ordered stage graph.
Scientific results use objective evidence; user authorization cannot turn a
failure or inconclusive result into a pass. External allocation does not block
independent internal work. At every boundary retain, audit, repair, refresh and
continue; a completed review or running campaign is not a reason to stop.
