# Attempt 07 runner-exception diagnosis and required repair

This review extends the existing V03-03/ATTEMPT07-REPAIR obligation. Attempt 07
continues as a capped defect inventory on unchanged protocol 2.6 and source
`b0eb52ea82984824d3694233f42d0b6a8a2efddfe40849f67debb565f5d90b14`.
No historical result, live outcome or current acceptance rule is rewritten.

## Observed mechanism

Sixteen constructor/configuration mutants produced worker debug `exit=-1` and
coordinator exit 255 in about four seconds, despite wall allowances exceeding
100 seconds. The pinned mutmut 3.8.0 forkserver catches runner exceptions,
assigns -1 and calls `os._exit(-1)`, which the parent receives as 255. Its status
table labels 255 as `timeout`. Thus the listing does not distinguish an actual
wall timeout from a runner exception.

The isolated copied-tree diagnostic retained in
`evidence/2026-10-01/phase-readiness/mutation-collection-exit-diagnostic-01/`
reproduced pytest exit 4 for fourteen of these mutants. All four selected clean
constructor/configuration controls collected successfully. The two remaining
cases were not run because the diagnostic respected its 180-second cap. Each
reproduced failure arises while importing `tests/test_repair_regressions.py`:
its parametrization constructs scheduler objects before test execution. Mutating
the constructor prevents the selected test from being collected; pytest reports
no collector, and mutmut raises `BadTestExecutionCommandsException`.

This diagnosis supports continued collection of the remaining inventory. It is
not a global forkserver crash or evidence that every other test result is lost.
The sixteen outcomes remain abnormal and unresolved for acceptance purposes.
Even the frozen listing's eventual FAIL cannot erase this evidence limitation;
its raw verdict must be retained with the separate diagnosis. Existing critical
survivors already prohibit PASS. Any new global reliability failure still
requires an evidence-preserving interruption.

## Required prospective repairs

1. Replace collection-time scheduler instances with a parametrized factory or
   case name, constructing the same scheduler inside the test. Preserve the
   original behavioral assertions. Check selected clean and mutated tests to
   establish that collection succeeds and mutations fail during test execution.
2. Retain and independently bind the complete raw `.meta` exit-code population,
   test-selection/timing statistics and worker debug log alongside the tool's
   listing. Verify exact one-to-one mutant identities across both representations.
3. Prospectively classify runner exceptions and pytest internal errors as
   unresolved. Do not count them as kills or subtract them as observed wall
   timeouts. Unknown codes, missing records, changed metadata, extra identities
   or inconsistent listing/status pairs must fail closed. Freeze any resulting
   protocol/schema change before the next campaign; preserve protocol 2.6.
4. Review the separate genuine wall expirations, including startup-heavy Ray
   selections whose measured test-call time omitted shared cluster startup.
   Calibrate an allowance from bounded clean selected executions before changing
   timeout configuration. The six-hour/four-worker total envelope remains fixed.
5. Integrate the previously prepared GP/Study/default-direction candidates and
   GP inverse-decoding repair, then review every remaining critical survivor and
   below-threshold module from the final inventory. Exact equivalence arguments
   require source-bound checking and explicit domains; diagnostics alone cannot
   establish an exclusion.

## Additional prepared coverage

The second public PASHA candidate detects 27 of 33 observed PASHA survivors,
including refusal atomicity, terminal trials, saved-state ownership, resumable
promotion state, an affordable tied trial after an unaffordable one, final-rung
cap preservation and strict tie handling. The tie examples independently expose
different public epsilon values. Six survivors remain for exact review.

The second CMA-ES candidate detects 21 of 35 observed module survivors, including
all six observation-path survivors, exact default seed/version metadata and
direction refusal. Its two suggestion-path shallow-copy survivors still require
review of the flat scalar configuration domain. The clean candidates pass 40
checks; generated-clean controls also pass. These candidates remain outside the
frozen suite and do not change attempt-07 scores.

Continue: complete capped inventory; perform the existing repair step; verify
affected contracts and raw-evidence enforcement; prospectively freeze and run
the existing final recheck; refresh finite conformance, conditional pilot
readiness and the master. No new direction, pilot allocation or release is
authorized by this review. The master remains incomplete.
