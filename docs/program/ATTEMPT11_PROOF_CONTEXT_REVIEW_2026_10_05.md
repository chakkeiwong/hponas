# Attempt11 prospective proof-context repair

Attempt11 remains active on source
`ab4629fdde5d3b8ffdef1a6ecbfd7786d47bebfed148b66f835ea866164c892c`.
This review prepares a later repair within `V03-03`; it does not alter that run,
its prospective rules, its result or its retained evidence.

## Demonstrated gap

The scheduler source hash is now
`22a00c3c288fe5759c709c6e0407d49f26dc72913ad1cc9b7083366b51baac8c`, but the
frozen equivalence checker still pins
`58f04be8c3e9591a93bdb4f9daf65d989585f9ed3854c9d9e20c6f75edbfb8ac`.
All other direct and companion source contexts match. The checker correctly
refuses source-bound scheduler proofs after this change. Existing tests only
compare the old reviewed fixture to that old context, so the baseline did not
expose the mismatch with the actual campaign source.

At the interim observation, seven critical scheduler survivors matched the
same exact transformations that had retained proofs in Attempt10: two
full-population slices, two absent-report defaults, the empty comparison
interval, the reversal flag and the repeated latest-resource comparison.
These observations establish a repair need, not final counts or a verdict.
Complete Attempt11 evidence must still be retained and independently evaluated
under its original frozen checker.

## Source and argument review

The complete source diff changes only `ASHAScheduler.__init__`,
`BudgetedASHAScheduler.__init__` and `MOASHAScheduler.__init__`. In all three,
rung construction appends budgets strictly below the final cap, verifies
`next_r > r`, and finally appends the cap. All promotion, reporting and epsilon
methods are structurally unchanged.

For each finite positive input on which the former constructor completed, the
new constructor produces the same strictly increasing rung sequence. An exact
cap is appended once. A multiplication overflowing the finite cap ends the
loop and appends that cap. A multiplication that fails to increase now raises
before another iteration; it previously failed to terminate. PASHA inherits
the same budgeted constructor and preserves increasing rungs.

The previously stated proofs therefore retain their premises on successful
construction:

- A sorted population of length `n` has the same full slice at `[:n]` and
  `[:None]`. Ranking, population count and subsequent use are unchanged.
- Missing report defaults remain local false values; they do not escape.
- At comparison top zero, increasing rungs still make the resource interval
  empty, so epsilon remains unchanged.
- False and None remain indistinguishable under the local reversal flag's
  truth tests before both become True.
- Including the latest resource adds the same comparison already used to set
  its ordering; it cannot introduce a reversal.

No new transformation, allowed domain or numerical threshold is added. The
candidate rebinds the reviewed source context and its test fixture only after
this complete diff review. Its generated-original comparison, exact mutation
matching, companion hashes, runtime checks and nearby-counterexample refusals
remain mandatory.

## Prepared repair and execution sequence

The isolated candidate adds `verify_proof_source_contexts`, called by
`mutation_freeze` before calibration or workers. It checks the actual source
bytes for every direct and companion context, rejects missing or mismatched
files and rejects inconsistent duplicate bindings. Its regression preserves a
matching historical fixture while changing actual source, reproducing the
specific baseline blind spot. A campaign-level regression verifies no
calibration, workers or freeze receipt is produced after refusal.

1. Continue monitoring Attempt11 to complete raw closure, including any other
   critical survivor or abnormal exit.
2. Retain and independently reconstruct its unchanged outcome. If the known
   duplicate-step operational failure occurs, activate the separately tested
   guarded recovery to register `V03-03/ATTEMPT11-REPAIR`.
3. Resolve every demonstrated gap from complete closure, then adopt the
   reviewed candidate. Refresh the master, copied baseline, supported
   installations and prospective freeze on the exact repaired source.
4. Execute the eligible bounded validation and continue the master according
   to objective results. A completed repair is not program completion.

The candidate is prepared in
`.hponas-runtime/candidates/attempt11-proof-context-01`. Its manifest and test
receipts live in
`docs/program/evidence/2026-10-05/attempt11-monitor-01/proof-candidate-01`.
The first candidate test invocation is preserved: 384 passes and one missing
`requirements.txt` in the new regression fixture. The second invocation adds
that required input and passes all 385 tests. The campaign source, scientific rules and live metadata
remain unchanged throughout preparation.
