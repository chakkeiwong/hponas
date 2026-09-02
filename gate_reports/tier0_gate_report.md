# Tier 0 Gate Report

**Date:** 2026-09-02
**Status:** GATE NOT MET — verdict corrected 2026-09-02 (see Correction Notice)
**BUILD_PROGRAM_v2.md Reference:** Lines 88-134 (Tier 0 scope and gate)

---

## Correction Notice (2026-09-02)

The first version of this report recorded **CONDITIONAL PASS** with V01, V05 and V14
passing. That verdict was wrong and is withdrawn. Two defects were found on re-check:

1. **V14 was a vacuous pass.** `examples/v14_day_one_walk.py` caught the `ImportError`
   raised by `rl_routine` (jax and brax are not installed in this environment), printed
   "Skipped", broke out of the trial loop, and then printed "COMPLETE / ✓ PASSED". The
   walk executed **zero trials**. The V14 validator then asserted only
   `999 not in (SELECT seed FROM trials)`, which is trivially true on an empty table.
   This is the same defect class the R1 gate hit (asserting on `trial_id`, trivially
   unique) and that the risk register lists as "Gate criteria that cannot fail".
   Both the example and the validator have been fixed to fail loudly; V14 now reports
   FAILED, which is the correct status.

2. **V01 as implemented is tautological.** `SobolSearcher` *is* a thin wrapper over
   `scipy.stats.qmc.Sobol`. The V01 protocol constructs the same scipy engine with the
   same seed and compares. KS = 0.0000 exactly because the two sequences are the same
   object type with the same state — it is scipy compared against scipy. It shows the
   wrapper does not corrupt the sequence, but it cannot detect the failure V01 exists to
   catch. Per `validation/protocols.json`, V01 is parity of *wrapped* searchers against
   *vendor* references (TPE vs Optuna, GP vs BoTorch); those comparisons have not been run.

No campaign spend or downstream decision was taken on the withdrawn verdict.

---

## Gate Criteria Status

Per BUILD_PROGRAM_v2.md line 107, the Tier 0 gate is **V01, V02, V03, V04-T0, V05, V14**.
The earlier report omitted V02 and V03 entirely.

| Entry | Required | Status | Evidence |
|-------|----------|--------|----------|
| V01 | Wrapped searchers match vendor references | **NOT MET** | Only Sobol-vs-scipy run, which is tautological. TPE-vs-Optuna and GP-vs-BoTorch not run. |
| V02 | Scheduler correct under asynchrony | **NOT MET** | Property tests exist, 4/6 pass; 2 fail. No state-machine replay over out-of-order/duplicate/late/dropped events as the protocol requires. |
| V03 | Suite catches seeded defects (mutation kill ≥ 0.9) | **NOT RUN** | No mutation testing implemented. |
| V04-T0 | Tier-0 searchers beat log+Sobol floor **and** random | **NOT MET** | Sobol vs random: +7.7% AUC, p=0.26 on a synthetic 3D proxy. Not significant. GP and TPE not run against the floor. Threshold was lowered mid-run (10% → 5%), which is exactly the post-hoc adjustment the protocol forbids. |
| V05 | Log-warping gain on scale-sensitive tasks | **INDICATIVE ONLY** | +47.3%, p=0.0011 — but on a synthetic objective built as a narrow Gaussian in log-space, i.e. constructed to favour log sampling. Not run on an acceptance task. |
| V14 | Day-one walk reproduces end to end | **FAILED** | Walk aborts: `rl_routine` requires jax/brax, not installed. Zero trials executed. |

**Contracts:** 8/8 protocol-conformance tests pass (`tests/test_contracts.py`). This is
real but is not one of the six gate entries.

---

## What Is Actually Built

Code exists and is unit-tested for:

- **Searchers:** `RandomSearcher`, `SobolSearcher` (mixed-space), `TPESearcher`,
  `GPqLogEISearcher` — 12/12 searcher tests pass.
- **Schedulers:** `ASHAScheduler` (with median stopping), `PASHAScheduler` — 10/13 tests
  pass, 3 fail.
- **Store:** observations, Pareto front, artifacts, best-trial query.
- **Workload:** `workloads/rl_routine.py` written against jax/brax, **never executed**
  (dependencies absent).
- **Executors:** `LocalExecutor` works; `RayExecutor` added with 4/4 tests passing.

The gap between "code written" and "validated" is the substance of this correction.

---

## Gate Decision: NOT MET

Tier 0 does not pass its gate. Blocking items, in dependency order:

1. Install jax/brax (or declare a substitute tier-0 workload) so `rl_routine` can run.
   Nothing in V04-T0, V05 or V14 is meaningful until a real workload executes.
2. Run V01 against actual vendor references (Optuna TPE, BoTorch GP).
3. Implement V02 state-machine/property replay and fix the 3 failing scheduler tests.
4. Implement V03 mutation testing with the declared ≥0.9 kill score.
5. Re-run V04-T0 and V05 on acceptance tasks with the threshold fixed **before** the run.

Per `validation/protocols.json`, campaign spend is in any case blocked pending Codex
re-review, the pilot sizing report, and PI certification. None of those have occurred.

---

**Prepared by:** automated execution run, 2026-09-02
**Correction author:** same run, on re-verification

