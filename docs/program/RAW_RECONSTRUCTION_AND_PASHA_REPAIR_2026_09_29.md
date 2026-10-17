# V02 raw reconstruction and PASHA promotion correction

This is execution inside the master program, **STAT-03/F / VAL-01** and
corrective **SPEC-03**, under existing repair authorization. It changes no
scientific outcome, threshold, error/power target or resource allocation.

## Findings and ordered repair

1. V02 previously trusted matching producer summaries for crash outcomes and
   did not establish concurrent execution from worker observations. Independent
   raw reconstruction is implemented: direct NumPy reference configurations,
   objective arithmetic, original interrupted checkpoint, worker journals,
   exported results, suggestion/observation history, actual process exit and worker overlap.
   The bounded full candidate passed all eight scenarios and 10,000 generated
   cases, retaining an INCONCLUSIVE scientific verdict. Its raw artifacts and
   source freeze are under `evidence/2026-09-29/val-01/v02-full-raw-r1`.
2. Reviewing V01 scheduler coverage found that PASHA inherited the explicit
   legacy budget scheduler's bootstrap/top-k promotion policy. The pinned
   published PASHA inherits quantile-based ASHA promotion. The preserved
   counterexample shows singleton promotion, too many two-observation
   promotions, and failure to reconsider a paused trial after late arrivals.
   Prior SPEC-01's 144 soft-ranking cases tested the progressive-cap criterion,
   not this policy. Its earlier broad “faithful PASHA verified” statement is
   withdrawn. GP/CMA-ES evidence and the tested cap criterion remain historical
   deliverables; **SPEC-03 is mandatory before validator/campaign closure**.
3. SPEC-03 now implements PASHA's reference promotion rule, retains paused and
   already promoted populations, prefers the highest eligible rung, preserves
   the separate incremental compute cap, and versions checkpoints so the old
   policy cannot silently resume under new semantics. Independent reference
   traces cover ties, late results, progressive caps and recovery.
   Full-sequence testing also exposed an upstream tolerance ambiguity: the
   pinned source tracks ordered `(a, b)` pairs while iterating unordered sets,
   so the same pair can be counted twice at different epochs when iteration
   order changes. Test the verbatim reference's dispatch decisions separately
   and expose this discrepancy; also compare the whole state trajectory using
   an explicitly declared sorted-set reference adapter which counts each
   unordered pair once. This adapter is not the unmodified vendor. At the final
   cap, retain the last nonterminal comparison rungs for tolerance calculation,
   matching the reference's rung representation. These are engineering checks;
   V01's exact reference envelope remains unresolved.
4. Continue V01 independent finite-table scheduler traces and the scientific
   equivalence review under STAT-03/F / VAL-01. Finite agreeing traces cannot
   establish equality in distribution for all random seeds. Provenance,
   prospective rank sizing and measured resources remain separate blockers.

The pre-repair snapshots are hash-preserved in
`archive/program-2026-09-29/val-01-before-raw-reconstruction/manifest.json` and
`archive/program-2026-09-29/spec-03-before-pasha-promotion/manifest.json`.
`evidence/2026-09-29/spec-03/reproduce_pasha_counterexample.py` can execute either
the archived or current scheduler source against the pinned independent source.

## Evidence boundaries

The initial sandbox Ray attempt could not open its local GCS service; partial
raw evidence is retained under `v02-raw-ray-r1`. The permitted rerun
`v02-raw-ray-r2` passed four-process overlap in both prescribed completion orders
and real OS-exit recovery. The full run `v02-full-raw-r1` then passed in 42.98
seconds. This is bounded CPU engineering work; no PPO/GPU workload, acceptance
campaign or release was executed. Reconstruction assumes honest instrumentation
on the recorded local host and covers the declared cases, not every possible
crash/schedule or hostile-host authentication. Subsequent source edits make
these runs historical snapshots until revalidated.

V02's initial affected suite passed 265 tests in 57.75 seconds, with two existing
Torch warnings; `raw-reconstruction-tests.xml` is retained. The final combined
suite passed **491 tests in 56.84 seconds**, with the same two warnings, recorded
in `spec-03/combined-tests-r2.xml`. The full V02 candidate was re-executed on the
final source: `val-01/v02-full-raw-r3/reconstruction.json` records all eight
scenarios and 10,000 cases, unchanged source, real crash recovery and actual
four-process overlap in both completion orders, in **40.96 seconds**. It retains
INCONCLUSIVE as the scientific verdict.

## Completed correction and finite-table review

`counterexample-before.json` and `counterexample-after.json` show all three
promotion defects corrected against the actual pinned PASHA source. Promotion
dispatch is now one trial per call, with a two-observation minimum and linear
1/eta quantile, inclusive ties and highest-rung priority. Paused candidates are
reconsidered after late arrivals; repeated reports cannot rewrite a committed
ranking or spend the same promotion twice. The optional total incremental
fidelity budget remains a separate extension. `pasha-progressive-v1` checkpoints
are rejected before mutation; the new policy is `pasha-progressive-quantile-v2`.
The explicit legacy budget scheduler is retained for its own checkpoints.

Initial full-sequence test failures are preserved: `pasha-initial-tests.xml`
contains six test-harness argument errors; `pasha-sequence-tests.xml` contains
six real tolerance/reference discrepancies. `pasha-corrected-tests.xml` has
34 passes. Six dense 40-root fixtures match the verbatim reference's dispatch
and cap decisions; full tolerance trajectories match the disclosed sorted-set
adapter, including reconstruction after every report. A separate exact example
shows that changing only pair iteration order changes the verbatim epsilon
from 10 to 9.2, whereas the deterministic unordered-pair calculation gives 10.
We do not claim this adapter is the unmodified vendor. The final-cap calculation
also retains the last nonterminal comparison pair, as the reference does.

Final boundary review retained three additional counterexamples in
`boundary-counterexamples-before.json`: ASHA and PASHA promoted both opposite
extreme finite losses after NumPy interpolation overflowed, and PASHA opened
its cap on tied survivor scores by sorting trial IDs instead of arrival order.
The shared cutoff now uses the pinned convex weighted quantile formula, which
avoids subtracting opposite extreme losses. PASHA preserves tied-result arrival
order. Both arrival permutations and extreme finite values are compared against
the pinned source; `boundary-corrected-tests.xml` records 63 passes. The prior
483-pass combined receipt and source-bound runs are historical snapshots,
preserved with the interim authority in
`archive/program-2026-09-29/spec-03-before-boundary-correction/manifest.json`.
The final 491-pass suite and refreshed table/V02 runs above include these fixes.

V01's wrapper inventory now checks both PASHA promotion and the existing 144
soft-ranking cases. V03's critical-function inventory now includes PASHA
promotion, report handling, recovery and the shared cutoff; no critical function is exempted.

`spec-03/table-review-r2/engineering-freeze.json` fixes all four already exposed
external tables, seed 0, optimizer seed 23, configuration geometry and counts
before execution. Six independent searcher loops and three independent
scheduler loops produce **36 comparisons in 8.04 seconds**. All observed
comparisons agree; **27 complete and all nine HalfCheetah traces halt on missing
source cells**. No cell, seed or environment is replaced to obtain agreement.
Scheduler verification rebuilds the reference trajectory from the original
table without invoking the tested scheduler, and rejects consistently corrupted
producer/reference copies. These records establish bounded engineering behavior,
not live-PPO performance, resource consumption or scientific acceptance.

## Objective V01 conclusion and remaining master work

The registered equality-in-distribution claim is **unproved**. Under a specified
coupling U, pathwise equality `T_wrapper(U) = T_reference(U)` for every admissible
input/random stream implies equality in law: for every measurable event A, the
two indicators of membership in A are equal, so their expectations are equal.
A sufficient program proof is an invariant relating initial states and every
reachable transition, report, random draw and observable output. Finite matching
traces verify only the inputs actually executed and do not establish that
invariant. Neither KS nonrejection nor a human acceptance can fill the gap.

Even with zero disagreements in 30 independent randomly sampled coupled runs,
the one-sided 95% upper bound on the mismatch probability is
`1 - 0.05**(1/30) = 0.09503385285530414`, not zero. Our fixed engineering recipes
are not iid draws supporting that bound. It is an illustration, not a new V01
tolerance or acceptance rule. The disclosed PASHA adapter also requires the
reference envelope to be resolved objectively before claiming vendor parity.

**SPEC-03's scoped corrective deliverable is complete. STAT-03/F is active again;
VAL-01 and the master remain incomplete.** Continue within the existing program:

1. The [scoped history/lineage review](EXPOSURE_HISTORY_REVIEW_2026_09_29.md) now
   covers 148 local reachable commits and 633 text blobs. Complete its operational
   evidence/trust contract, independently anchored
   freeze/reveal chronology and execution isolation. A name, signature, local
   timestamp, disjoint seed list or matching summary cannot establish these facts.
2. Complete V01's reachable-transition/reference argument and V02's final
   scheduler/population scope. The recorded finite traces do not waive either.
3. Under STAT-03/E, justify a prospective positive planning alternative and a
   valid rank sizing/stopping rule; do not infer actual power from conditional
   sensitivity or transfer unrelated external-table performance to live PPO.
4. Complete the measured resource proposal and objective phase checks before
   separate allocation, PILOT-01, CAP-01, frozen acceptance and REL-01.

No human scientific ruling is requested. These are evidence and implementation
dependencies inside the master. Later-tier obligations remain, and no campaign
spending, release or all-seed equivalence is inferred from this repair.
