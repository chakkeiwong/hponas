# V03-02 repair and verification review

This closes the bounded coverage/repair work item, not V03 acceptance or the
master program. V03-03 requires a final frozen population, settled operator
policy and individual survivor dispositions. None of the diagnostic counts below
is combined with another population or promoted to a release PASS.

## Reproduced defects and fixes

- Study checkpoint loading replaced live trial/control state before validating
  the recovery ledger. Invalid checkpoints now fail before those assignments.
  Budget, concurrency, maximize and suggestion counts receive the same type and
  consistency checks as construction. This does not guarantee rollback if an
  arbitrary plugin's `set_state` fails after ledger validation.
- LocalExecutor accepted boolean worker counts; it now rejects them.
- The legacy Ray executor's destructor raised AttributeError after dependency
  initialization failed. Its cleanup registries now exist before that failure.
- TST-01's concurrent snapshot reader reproduced a write-lock problem caused by
  schema DDL on the read path. Store creates snapshot/objective tables at open;
  snapshot and Pareto reads issue no schema writes.
- The V03 critical-path matcher ignored the top-level shared `evaluate_trial`
  function. A 99%-kill synthetic inventory with one evaluation survivor falsely
  passed. The matcher now recognizes both module functions and class methods.

## Verification

The full suite, explicitly selecting `tests` and excluding only the separately
tracked optional `test_prior_recovery_pibo.py`, completed with **1,205 passed,
5 skipped**. Evidence-integrity and governance tests passed **43** checks. Fatal
lint checks and `git diff --check` passed. The optional prior file retains its
earlier **3 passed, 2 failed** result; it was not rerun or claimed repaired.

New checks exercise observable state/recovery, resource cleanup, measured costs,
ordering, corruption and concurrency rather than merely matching implementation
expressions. Initial test-fixture mistakes (wrong Knob kind and nonexistent
EventLog append API) are preserved separately from reproduced product failures.

| Diagnostic selection | Killed / total | Survived | Timeout | Uncovered | Interpretation |
|---|---:|---:|---:|---:|---|
| Checkpoint baseline, old loader | 90 / 207 | 117 | 0 | 0 | Reproduces retained survivor count. |
| Repaired checkpoint loader | 210 / 236 | 26 | 0 | 0 | Remaining diagnostic text mutations, individually reviewed. Population grew with validation. |
| Ray controller (V03-01) | 223 / 240 | 17 | 0 | 0 | Retained independent diagnostic; no exclusions. |
| Legacy adapter | 50 / 54 | 4 | 0 | 0 | Remaining diagnostic text mutations. |
| Shared/local executors | 251 / 268 | 17 | 0 | 0 | Message/NaN-string survivors; no abnormal outcomes. |
| Replay | 257 / 287 | 30 | 0 | 0 | Messages plus two individually reviewed equivalence candidates; raw score remains below 90%. |
| Schedulers | 734 / 794 | 54 | 6 | 0 | Six loop mutants time out; all critical promotion survivors individually reviewed. |
| Legacy searchers/executors | 437 / 478 | 41 | 0 | 0 | Subsequent targeted default-mode check kills two of these survivors in a new two-mutant diagnostic. |
| Store after schema repair | 459 / 503 | 44 | 0 | 0 | Remaining SQL/message mutations and two equivalence candidates; no abnormal outcomes. |

Four subsequent scheduler checks killed the three exact-tolerance boundary
mutants and one adjacent-dominance mutant. Equality at a rare floating-point
boundary is **not** a defensible equivalence argument. These targeted outcomes
are preserved separately; the original 794-mutant report is unchanged.

The paired executor runtime probe used six previously abnormal mutants. The
existing `fork` mode killed all six; `forkserver` produced one kill, four
survivors and one abnormal exit (raw worker exit -9, categorized “segfault” by
mutmut). No main runtime configuration was changed. A larger current executor
diagnostic completed without abnormal outcomes. This does not prove the cause
of every historical -11 exit; V03-03 must reproduce stable execution over the
whole frozen suite. Setup failures from sandbox Ray startup and absent Git
context are preserved and never counted as mutation kills.

## Remaining acceptance work

The [individual critical review](evidence/2026-09-28/v03-02/critical-survivor-review.json)
records 65 critical survivors with exact diffs and reasoning, and refers to the
existing Ray review. No equivalent exclusions are applied. Error-message bytes
are observable, so they are not silently declared equivalent. The current
protocol says string mutations are disabled, but mutmut 3.8 generates them;
the DRAFT register also caps the population at 200 while the current execution
profile requires all expanded modules. STAT-01 must make this conflict explicit
before the acceptance profile is frozen.

All original evidence is retained under
`docs/program/evidence/2026-09-28/v03-02/`, including executed source/test snapshots,
status metadata, raw logs, failed tests, corrected runs and bounded-run scripts.
Source changes make the earlier V01/V02/V14 and PPO smoke receipts stale. They
will be refreshed after specification and packaging work, rather than repeatedly
running campaigns against an implementation still changing.
